"""
rodage.py — Script de rodage industriel Clean & Protech V4 (SERENA).

Deux moteurs cyclent en alternance dans une boucle unique :

    Vanne classique (POMPE) : ouverture → pause → fermeture → pause
    V4V (VIC)               : pos 1→2→3→4→5→4→3→2→1

Un cycle global = 1 aller-retour vanne + 1 tour complet V4V.
Les deux boucles avancent à tour de rôle (pas de threads — GIL Python
empêche toute vraie simultanéité sur les boucles de pulses).

Arrêt propre sur Ctrl+C :
    - Vanne classique → position ouverte
    - V4V → position 1 (butée 0 pas)
    - Drivers désactivés

Lancement :
    cd /home/bebl/Desktop/Clean-and-Protech/rodage_indus
    python3 rodage.py
"""

from __future__ import annotations

import logging
import sys
import time
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

if str(_RODAGE_DIR) not in sys.path:
    sys.path.insert(0, str(_RODAGE_DIR))

import rodage_config as rcfg
from stepper import move_vanne_classique, move_vic_to_position


# ============================================================
# Logging — console uniquement
# ============================================================

def _setup_logging() -> logging.Logger:
    fmt = logging.Formatter(fmt="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    ch  = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)

    logger = logging.getLogger("rodage_indus")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(ch)
    logger.propagate = False
    return logger


# ============================================================
# Initialisation des deux moteurs
# ============================================================

def _init_moteurs(motors: MotorController, log: logging.Logger) -> int:
    """
    Met les deux moteurs en position de départ.

    V4V  : VIC_INIT_STEPS pas en fermeture → butée mécanique position 1 (0 pas).
           Course physique max = 100 pas, marge +10 % = 110 pas.
    Vanne : fermeture standard avec rampe.

    Retourne vic_steps (0) après init.
    """
    # ── V4V ─────────────────────────────────────────────────────────────────
    log.info(
        f"[INIT] V4V — fermeture {rcfg.VIC_INIT_STEPS} pas"
        f" @ {v4cfg.VIC_SPEED_SPS} sps → butée position 1"
    )
    t0 = time.monotonic()
    motors.move_steps("VIC", rcfg.VIC_INIT_STEPS, "fermeture", v4cfg.VIC_SPEED_SPS)
    log.info(f"[INIT] V4V — position 1 OK  ({time.monotonic() - t0:.1f}s)")

    # ── Vanne classique ──────────────────────────────────────────────────────
    log.info(f"[INIT] Vanne {rcfg.VANNE_CLASSIQUE} — fermeture standard")
    t0 = time.monotonic()
    move_vanne_classique(motors, "fermeture", rcfg.VANNE_CLASSIQUE)
    log.info(f"[INIT] Vanne {rcfg.VANNE_CLASSIQUE} — fermée  ({time.monotonic() - t0:.1f}s)")

    return 0   # vic_steps = 0 (position 1)


# ============================================================
# Mise en sécurité
# ============================================================

def _securite(motors: MotorController, log: logging.Logger, vic_steps: int) -> None:
    """
    Position sûre avant extinction :
      - Vanne classique → ouverte
      - V4V → position 1 (butée, VIC_INIT_STEPS pas fermeture)
      - Tous les drivers → désactivés
    """
    log.info("[SECURITE] Mise en position sûre...")

    try:
        log.info(f"[SECURITE] Vanne {rcfg.VANNE_CLASSIQUE} → OUVERTURE")
        move_vanne_classique(motors, "ouverture", rcfg.VANNE_CLASSIQUE)
        log.info(f"[SECURITE] Vanne {rcfg.VANNE_CLASSIQUE} — OUVERTE")
    except Exception as e:
        log.error(f"[SECURITE] Vanne {rcfg.VANNE_CLASSIQUE} : {e}")

    try:
        log.info(
            f"[SECURITE] V4V → position 1"
            f"  ({rcfg.VIC_INIT_STEPS} pas fermeture depuis ~{vic_steps} pas)"
        )
        motors.move_steps("VIC", rcfg.VIC_INIT_STEPS, "fermeture", v4cfg.VIC_SPEED_SPS)
        log.info("[SECURITE] V4V — position 1 OK")
    except Exception as e:
        log.error(f"[SECURITE] V4V : {e}")

    try:
        motors.disable_all_drivers()
        log.info("[SECURITE] Drivers désactivés")
    except Exception as e:
        log.error(f"[SECURITE] disable drivers : {e}")


# ============================================================
# Boucle principale
# ============================================================

def main() -> None:
    log = _setup_logging()

    log.info("=" * 55)
    log.info("  RODAGE INDUSTRIEL — démarrage")
    log.info(f"  Vanne classique  : {rcfg.VANNE_CLASSIQUE}")
    log.info(f"  Pause ouverte    : {rcfg.PAUSE_OPEN_S}s")
    log.info(f"  Pause fermée     : {rcfg.PAUSE_CLOSE_S}s")
    log.info(f"  Positions V4V    : {rcfg.VIC_CYCLE_POSITIONS}")
    log.info(f"  Cycles total     : {rcfg.TOTAL_CYCLES}")
    log.info("=" * 55)

    gpio_handle.init()

    vic_steps = 0   # position courante V4V (mis à jour à chaque mouvement)

    try:
        with I2CBus() as bus:
            io = IOBoard(bus)
            io.init()
            io.set_all_leds(0)

            with MotorController(io) as motors:

                # ── Init ────────────────────────────────────────────────────
                vic_steps = _init_moteurs(motors, log)
                log.info("Init terminée — démarrage des cycles")

                # État courant de chaque boucle
                vanne_pos     = "CLOSE"   # la vanne est fermée après init
                vic_pos_idx   = 0         # index dans VIC_CYCLE_POSITIONS
                vic_pos_label = rcfg.VIC_CYCLE_POSITIONS[0]

                vanne_cycles = 0
                vic_cycles   = 0
                global_cycles = 0

                try:
                    while global_cycles < rcfg.TOTAL_CYCLES:

                        restant = rcfg.TOTAL_CYCLES - global_cycles

                        # ════════════════════════════════════════════════════
                        # Étape vanne classique
                        # ════════════════════════════════════════════════════
                        if vanne_pos == "CLOSE":
                            log.info(
                                f"[VANNE {rcfg.VANNE_CLASSIQUE}]"
                                f"  → OUVERTURE"
                                f"  (cycle {global_cycles + 1}/{rcfg.TOTAL_CYCLES}"
                                f", restant {restant})"
                            )
                            move_vanne_classique(motors, "ouverture", rcfg.VANNE_CLASSIQUE)
                            vanne_pos = "OPEN"
                            log.info(
                                f"[VANNE {rcfg.VANNE_CLASSIQUE}]"
                                f"  OUVERTE — pause {rcfg.PAUSE_OPEN_S}s"
                            )
                            time.sleep(rcfg.PAUSE_OPEN_S)

                        else:  # OPEN
                            log.info(
                                f"[VANNE {rcfg.VANNE_CLASSIQUE}]"
                                f"  → FERMETURE"
                                f"  (cycle {global_cycles + 1}/{rcfg.TOTAL_CYCLES}"
                                f", restant {restant})"
                            )
                            move_vanne_classique(motors, "fermeture", rcfg.VANNE_CLASSIQUE)
                            vanne_pos = "CLOSE"
                            log.info(
                                f"[VANNE {rcfg.VANNE_CLASSIQUE}]"
                                f"  FERMEE — pause {rcfg.PAUSE_CLOSE_S}s"
                            )
                            time.sleep(rcfg.PAUSE_CLOSE_S)

                            # Un aller-retour complet = 1 cycle vanne
                            vanne_cycles += 1
                            log.info(
                                f"[VANNE {rcfg.VANNE_CLASSIQUE}]"
                                f"  ✓ cycle vanne {vanne_cycles}"
                            )

                        # ════════════════════════════════════════════════════
                        # Étape V4V — 1 position à la fois, entrelacée
                        # ════════════════════════════════════════════════════
                        next_idx      = (vic_pos_idx + 1) % len(rcfg.VIC_CYCLE_POSITIONS)
                        next_pos      = rcfg.VIC_CYCLE_POSITIONS[next_idx]

                        log.info(
                            f"[V4V]  pos {vic_pos_label} → pos {next_pos}"
                            f"  ({next_idx + 1}/{len(rcfg.VIC_CYCLE_POSITIONS)}"
                            f" dans le tour)"
                            f"  (cycle {global_cycles + 1}/{rcfg.TOTAL_CYCLES}"
                            f", restant {restant})"
                        )
                        vic_steps = move_vic_to_position(motors, vic_steps, next_pos)
                        vic_pos_idx   = next_idx
                        vic_pos_label = next_pos
                        log.info(f"[V4V]  pos {next_pos} atteinte ({vic_steps} pas)")

                        # Un tour complet = retour à la position de départ (index 0)
                        if vic_pos_idx == 0:
                            vic_cycles += 1
                            log.info(f"[V4V]  ✓ cycle V4V {vic_cycles}")

                        # ════════════════════════════════════════════════════
                        # Cycle global = min des deux compteurs
                        # ════════════════════════════════════════════════════
                        new_global = min(vanne_cycles, vic_cycles)
                        if new_global > global_cycles:
                            global_cycles = new_global
                            log.info(
                                f"{'═' * 45}"
                                f"\n{'':10}✓ CYCLE GLOBAL {global_cycles}/{rcfg.TOTAL_CYCLES}"
                                f"  —  {rcfg.TOTAL_CYCLES - global_cycles} restant(s)"
                                f"\n{'═' * 45}"
                            )

                except KeyboardInterrupt:
                    log.info(
                        f"\nInterruption Ctrl+C"
                        f" — cycle {global_cycles}/{rcfg.TOTAL_CYCLES}"
                    )

                finally:
                    _securite(motors, log, vic_steps)

                if global_cycles >= rcfg.TOTAL_CYCLES:
                    log.info(
                        f"Rodage terminé — {rcfg.TOTAL_CYCLES} cycles complétés"
                    )
                else:
                    log.info(
                        f"Rodage arrêté — {global_cycles}/{rcfg.TOTAL_CYCLES}"
                        " cycles complétés"
                    )

    except Exception as e:
        log.error(f"Erreur fatale : {e}", exc_info=True)
        raise

    finally:
        gpio_handle.close()
        log.info("GPIO libéré — fin")


if __name__ == "__main__":
    main()
