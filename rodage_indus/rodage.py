"""
rodage.py — Rodage industriel Clean & Protech V4 (SERENA).

Séquence par cycle :
    1. Vanne classique (POMPE) : ouverture complète → pause → fermeture complète → pause
    2. V4V (VIC) : avance vers la position suivante (ordre 1→2→3→4→5→1→...)

Lancement depuis Geany (bouton Run) :
    Répertoire de travail = rodage_indus/
    python3 rodage.py
"""

from __future__ import annotations

import logging
import sys
import time
import traceback

from config import (
    TOTAL_CYCLES,
    PAUSE_OPEN_S,
    PAUSE_CLOSE_S,
    VANNE_CLASSIQUE,
    VIC_INIT_STEPS,
    VIC_CYCLE_POSITIONS,
    VIC_PAUSE_S,
)
from stepper import RodageDriver, VIC_POSITIONS


# ── Logging console uniquement ────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    fmt = logging.Formatter(fmt="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    ch  = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log = logging.getLogger("rodage")
    log.setLevel(logging.DEBUG)
    log.addHandler(ch)
    log.propagate = False
    return log


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log = _setup_logging()

    log.info("=" * 54)
    log.info("  RODAGE INDUSTRIEL — Clean & Protech (SERENA)")
    log.info(f"  Vanne     : {VANNE_CLASSIQUE}")
    log.info(f"  V4V cycle : {VIC_CYCLE_POSITIONS}  pause={VIC_PAUSE_S}s")
    log.info(f"  Cycles    : {TOTAL_CYCLES}")
    log.info(f"  Pauses    : open={PAUSE_OPEN_S}s  close={PAUSE_CLOSE_S}s")
    log.info(f"  Drivers   : 400 pas/tour  |  ENA actif bas")
    log.info("=" * 54)

    with RodageDriver() as drv:

        vic_steps: int = 0    # position absolue VIC en pas (0 = position 1)
        completed: int = 0    # nombre de cycles terminés avec succès

        try:
            # ── Initialisation ────────────────────────────────────────────────
            log.info(f"[INIT] VIC → butée position 1"
                     f"  (course majorée {VIC_INIT_STEPS} pas)")
            vic_steps = drv.vic_home(VIC_INIT_STEPS)
            log.info("[INIT] VIC  — position 1 OK  (0 pas)")

            log.info(f"[INIT] Vanne {VANNE_CLASSIQUE} → fermeture initiale")
            drv.move_vanne("fermeture")
            log.info(f"[INIT] Vanne {VANNE_CLASSIQUE} — fermée")

            log.info("Démarrage des cycles\n")

            # ── Boucle principale ─────────────────────────────────────────────
            for cycle in range(1, TOTAL_CYCLES + 1):
                log.info(f"── CYCLE {cycle}/{TOTAL_CYCLES} ──")

                # 1. Vanne classique : ouverture → pause → fermeture → pause
                log.info(f"  [VANNE] → OUVERTURE")
                drv.move_vanne("ouverture")
                log.info(f"  [VANNE]   OUVERTE  — pause {PAUSE_OPEN_S}s")
                time.sleep(PAUSE_OPEN_S)

                log.info(f"  [VANNE] → FERMETURE")
                drv.move_vanne("fermeture")
                log.info(f"  [VANNE]   FERMEE   — pause {PAUSE_CLOSE_S}s")
                time.sleep(PAUSE_CLOSE_S)

                # 2. V4V : aller-retour complet 1→2→3→4→5→4→3→2→1
                log.info(f"  [V4V] aller-retour {VIC_CYCLE_POSITIONS}")
                n_pos = len(VIC_CYCLE_POSITIONS)
                for j, target_pos in enumerate(VIC_CYCLE_POSITIONS):
                    if VIC_POSITIONS[target_pos] == vic_steps:
                        continue   # déjà en position (pos.1 initiale)
                    vic_prev  = vic_steps
                    vic_steps = drv.move_vic_to(vic_steps, target_pos)
                    log.info(
                        f"  [V4V]   pos.{target_pos} atteinte"
                        f"  (delta {vic_steps - vic_prev:+d} pas)"
                    )
                    if j < n_pos - 1:
                        time.sleep(VIC_PAUSE_S)

                completed = cycle
                log.info(
                    f"[Cycle {cycle}/{TOTAL_CYCLES}]"
                    f"  Vanne: CLOSE | V4V: pos.1\n"
                )

            # ── Fin normale ───────────────────────────────────────────────────
            log.info("=" * 54)
            log.info(f"  RODAGE TERMINE — {completed} cycles effectués")
            log.info("=" * 54)

        except KeyboardInterrupt:
            log.info("\nCtrl+C — arrêt demandé")

        except Exception:
            log.error("EXCEPTION — traceback complet :")
            log.error(traceback.format_exc())

        finally:
            # ── Séquence de sécurité (toujours exécutée) ─────────────────────
            log.info("[SECURITE] Vanne → ouverture")
            try:
                drv.move_vanne("ouverture")
                log.info("[SECURITE] Vanne — ouverte")
            except Exception as exc:
                log.error(f"[SECURITE] Vanne : {exc}")

            log.info(f"[SECURITE] V4V → position 1"
                     f"  (course majorée {VIC_INIT_STEPS} pas)")
            try:
                vic_steps = drv.vic_home(VIC_INIT_STEPS)
                log.info("[SECURITE] V4V  — position 1")
            except Exception as exc:
                log.error(f"[SECURITE] V4V : {exc}")

            drv.disable_all()
            log.info("[SECURITE] Drivers désactivés")
            log.info(
                f"Arrêt  —  cycle {completed}/{TOTAL_CYCLES}"
                f"  |  Vanne: OPEN  |  V4V: pos.1"
            )


if __name__ == "__main__":
    main()
