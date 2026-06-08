"""
rodage.py — Script de rodage industriel Clean & Protech V4 (SERENA).

Deux moteurs tournent en parallèle (threading) jusqu'à TOTAL_CYCLES cycles :

    Vanne classique : ouverture → pause → fermeture → pause → ...
    V4V (VIC)       : pos 1 → 2 → 3 → 4 → 5 → 1 → ...

Un cycle est complété quand les deux boucles ont chacune terminé
un aller-retour / tour complet.

Arrêt propre sur Ctrl+C :
    - Vanne classique → position ouverte
    - VIC → position 1 (0 pas)
    - Drivers désactivés
    - Log de la position d'arrêt et du cycle en cours

Lancement :
    cd /home/bebl/Desktop/Clean-and-Protech/rodage_indus
    python3 rodage.py
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Chemin vers V4 ────────────────────────────────────────────────────────────
_RODAGE_DIR = Path(__file__).resolve().parent
_V4_ROOT    = _RODAGE_DIR.parent / "V4"
if str(_V4_ROOT) not in sys.path:
    sys.path.insert(0, str(_V4_ROOT))

import config as v4cfg
import libs.gpio_handle as gpio_handle
from libs.i2c_bus import I2CBus
from libs.io_board import IOBoard
from libs.moteur import MotorController

# Import config rodage (même dossier)
if str(_RODAGE_DIR) not in sys.path:
    sys.path.insert(0, str(_RODAGE_DIR))

import config as rcfg
from stepper import move_vanne_classique, move_vic_to_position


# ============================================================
# Logging — fichier horodaté dans logs/
# ============================================================

def _setup_logging() -> logging.Logger:
    logs_dir = _RODAGE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)

    stamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = logs_dir / f"rodage_{stamp}.log"

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger = logging.getLogger("rodage_indus")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    logger.propagate = False
    return logger


# ============================================================
# État partagé entre les deux threads
# ============================================================

class SharedState:
    """
    Compteur de cycles et flag d'arrêt partagés entre les deux threads moteur.
    Toutes les lectures/écritures passent par le verrou.
    """

    def __init__(self, total: int) -> None:
        self._lock          = threading.Lock()
        self._stop_event    = threading.Event()
        self._total         = total

        # Chaque thread incrémente son compteur local quand il finit un demi-cycle.
        # Un cycle global est validé quand les deux threads ont fini le même numéro.
        self._vanne_cycles  = 0   # cycles complets vanne classique
        self._vic_cycles    = 0   # cycles complets VIC

        # Cycle global = min(vanne, vic) — le plus lent définit la cadence
        self._global_cycles = 0

    # ── Arrêt ────────────────────────────────────────────────────────────────

    def request_stop(self) -> None:
        self._stop_event.set()

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    # ── Cycles ───────────────────────────────────────────────────────────────

    def complete_vanne_cycle(self) -> int:
        """Appelé par le thread vanne en fin de cycle. Retourne le nouveau compteur."""
        with self._lock:
            self._vanne_cycles += 1
            self._update_global()
            return self._vanne_cycles

    def complete_vic_cycle(self) -> int:
        """Appelé par le thread VIC en fin de cycle. Retourne le nouveau compteur."""
        with self._lock:
            self._vic_cycles += 1
            self._update_global()
            return self._vic_cycles

    def _update_global(self) -> None:
        new = min(self._vanne_cycles, self._vic_cycles)
        if new > self._global_cycles:
            self._global_cycles = new
            # Si les deux threads ont atteint le total, on signale l'arrêt
            if self._global_cycles >= self._total:
                self._stop_event.set()

    def global_cycles(self) -> int:
        with self._lock:
            return self._global_cycles

    def total(self) -> int:
        return self._total

    def max_reached(self) -> bool:
        """Vrai quand le cycle actuel dépasse TOTAL_CYCLES."""
        with self._lock:
            return (
                self._vanne_cycles >= self._total
                and self._vic_cycles >= self._total
            )


# ============================================================
# Thread — Vanne classique
# ============================================================

def _thread_vanne(
    motors: MotorController,
    state:  SharedState,
    log:    logging.Logger,
) -> None:
    """
    Boucle infinie : ouverture → pause → fermeture → pause → cycle++
    S'arrête quand state.should_stop() est vrai.
    """
    name = rcfg.VANNE_CLASSIQUE
    log.info(f"[VANNE] démarrage — {name}")

    try:
        while not state.should_stop():
            # Ouverture
            log.info(f"[VANNE] {name} → OUVERTURE")
            move_vanne_classique(motors, "ouverture", name)
            log.info(f"[VANNE] {name} — position OPEN — pause {rcfg.PAUSE_OPEN_S}s")

            # Pause en position ouverte (interruptible)
            _interruptible_sleep(rcfg.PAUSE_OPEN_S, state)
            if state.should_stop():
                break

            # Fermeture
            log.info(f"[VANNE] {name} → FERMETURE")
            move_vanne_classique(motors, "fermeture", name)
            log.info(f"[VANNE] {name} — position CLOSE — pause {rcfg.PAUSE_CLOSE_S}s")

            # Pause en position fermée (interruptible)
            _interruptible_sleep(rcfg.PAUSE_CLOSE_S, state)
            if state.should_stop():
                break

            n = state.complete_vanne_cycle()
            log.info(f"[VANNE] cycle {n}/{state.total()} terminé")

    except Exception as e:
        log.error(f"[VANNE] exception : {e}", exc_info=True)
        state.request_stop()


# ============================================================
# Thread — V4V (VIC)
# ============================================================

def _thread_vic(
    motors:      MotorController,
    state:       SharedState,
    log:         logging.Logger,
    vic_steps_0: int,
) -> None:
    """
    Boucle infinie : parcourt VIC_CYCLE_POSITIONS dans l'ordre, puis recommence.
    S'arrête quand state.should_stop() est vrai.
    """
    positions   = rcfg.VIC_CYCLE_POSITIONS      # ex. [1, 2, 3, 4, 5]
    current_pos = positions[0]                   # position de départ supposée
    current_steps = vic_steps_0
    log.info(f"[VIC] démarrage — positions cycle {positions}")

    try:
        while not state.should_stop():
            for pos in positions:
                if state.should_stop():
                    break
                log.info(f"[VIC] pos {current_pos} → pos {pos}")
                current_steps = move_vic_to_position(motors, current_steps, pos)
                log.info(f"[VIC] pos {pos} atteinte ({current_steps} pas)")
                current_pos = pos

            if state.should_stop():
                break

            n = state.complete_vic_cycle()
            log.info(f"[VIC] cycle {n}/{state.total()} terminé")

    except Exception as e:
        log.error(f"[VIC] exception : {e}", exc_info=True)
        state.request_stop()


# ============================================================
# Helpers
# ============================================================

def _interruptible_sleep(duration_s: float, state: SharedState) -> None:
    """Dort par tranches de 0.1s pour rester réactif à l'arrêt."""
    end = time.monotonic() + duration_s
    while time.monotonic() < end and not state.should_stop():
        time.sleep(min(0.1, end - time.monotonic()))


def _safe_position_vanne(
    motors: MotorController,
    log:    logging.Logger,
    name:   str,
) -> None:
    """Met la vanne classique en position ouverte (sécurité arrêt)."""
    try:
        log.info(f"[SECURITE] {name} → OUVERTURE (position sûre)")
        move_vanne_classique(motors, "ouverture", name)
        log.info(f"[SECURITE] {name} — OPEN")
    except Exception as e:
        log.error(f"[SECURITE] erreur ouverture {name} : {e}")


def _safe_position_vic(
    motors:        MotorController,
    log:           logging.Logger,
    current_steps: int,
) -> None:
    """Ramène la VIC à la position 1 (0 pas) — sécurité arrêt."""
    try:
        log.info(f"[SECURITE] VIC → position 1 (0 pas) depuis {current_steps} pas")
        move_vic_to_position(motors, current_steps, rcfg.VIC_CYCLE_POSITIONS[0])
        log.info("[SECURITE] VIC — position 1 atteinte")
    except Exception as e:
        log.error(f"[SECURITE] erreur VIC : {e}")


# ============================================================
# Main
# ============================================================

def main() -> None:
    log = _setup_logging()

    log.info("=" * 50)
    log.info("  RODAGE INDUSTRIEL — démarrage")
    log.info(f"  Vanne classique  : {rcfg.VANNE_CLASSIQUE}")
    log.info(f"  Pause ouverte    : {rcfg.PAUSE_OPEN_S}s")
    log.info(f"  Pause fermée     : {rcfg.PAUSE_CLOSE_S}s")
    log.info(f"  Positions VIC    : {rcfg.VIC_CYCLE_POSITIONS}")
    log.info(f"  Cycles total     : {rcfg.TOTAL_CYCLES}")
    log.info("=" * 50)

    gpio_handle.init()

    try:
        with I2CBus() as bus:
            io = IOBoard(bus)
            io.init()
            io.set_all_leds(0)

            with MotorController(io) as motors:

                state = SharedState(rcfg.TOTAL_CYCLES)

                # ── Homing avant de démarrer ─────────────────────────────────
                log.info("Homing — démarrage")
                t0 = time.monotonic()
                motors.homing()
                log.info(f"Homing — terminé en {time.monotonic() - t0:.1f}s")

                # Après homing : VIC est à la position 3 (50 pas, neutre).
                # On la ramène à la position 1 (0 pas) — point de départ du cycle.
                vic_start_steps = v4cfg.VIC_POSITIONS[3]   # 50 — état post-homing
                log.info("VIC → position 1 (0 pas) — initialisation cycle")
                vic_start_steps = move_vic_to_position(motors, vic_start_steps, rcfg.VIC_CYCLE_POSITIONS[0])
                log.info(f"VIC — position 1 atteinte ({vic_start_steps} pas)")

                # Vanne classique : homing l'a laissée ouverte (course ouverture
                # standard après la dernière fermeture). Rien à faire.
                log.info(f"Vanne {rcfg.VANNE_CLASSIQUE} — supposée ouverte après homing")

                log.info("Lancement des deux threads moteur")

                t_vanne = threading.Thread(
                    target=_thread_vanne,
                    args=(motors, state, log),
                    name="thread-vanne",
                    daemon=True,
                )
                t_vic = threading.Thread(
                    target=_thread_vic,
                    args=(motors, state, log, vic_start_steps),
                    name="thread-vic",
                    daemon=True,
                )

                t_vanne.start()
                t_vic.start()

                try:
                    # Boucle de supervision — réveils 0.5s pour surveiller l'arrêt
                    while t_vanne.is_alive() or t_vic.is_alive():
                        t_vanne.join(timeout=0.5)
                        t_vic.join(timeout=0.5)

                except KeyboardInterrupt:
                    log.info(
                        f"Interruption Ctrl+C — cycle en cours {state.global_cycles()}"
                        f"/{state.total()}"
                    )
                    state.request_stop()

                finally:
                    # Attendre la fin propre des threads (max 30s)
                    t_vanne.join(timeout=30)
                    t_vic.join(timeout=30)

                    # ── Séquence de mise en sécurité ────────────────────────
                    log.info("Mise en sécurité — début")
                    _safe_position_vanne(motors, log, rcfg.VANNE_CLASSIQUE)
                    _safe_position_vic(motors, log, v4cfg.VIC_POSITIONS[rcfg.VIC_CYCLE_POSITIONS[0]])
                    io.disable_all_drivers()
                    log.info(
                        f"Mise en sécurité — OK"
                        f" | cycles terminés : {state.global_cycles()}/{state.total()}"
                        f" | vanne {rcfg.VANNE_CLASSIQUE} : OPEN"
                        f" | VIC : position {rcfg.VIC_CYCLE_POSITIONS[0]}"
                        f" ({v4cfg.VIC_POSITIONS[rcfg.VIC_CYCLE_POSITIONS[0]]} pas)"
                    )

                if state.max_reached():
                    log.info(
                        f"Rodage terminé normalement — {rcfg.TOTAL_CYCLES} cycles complétés"
                    )
                else:
                    log.info(
                        f"Rodage arrêté — {state.global_cycles()}/{rcfg.TOTAL_CYCLES}"
                        " cycles complétés"
                    )

    except Exception as e:
        # Logger peut ne pas exister si l'exception se produit avant _setup_logging
        log.error(f"Erreur fatale : {e}", exc_info=True)
        raise

    finally:
        gpio_handle.close()
        log.info("GPIO libéré — fin du script")


if __name__ == "__main__":
    main()
