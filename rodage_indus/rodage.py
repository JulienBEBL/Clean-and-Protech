"""
rodage.py — Rodage industriel Clean & Protech V4 (SERENA).

Séquence par cycle :
    1. V4V  : pos 1→2→3→4→5→4→3→2→1
    2. Vanne : ouverture → pause → fermeture → pause

Lancement :
    cd /home/bebl/Desktop/Clean-and-Protech/rodage_indus
    python3 rodage.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

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


# ── Logging console ───────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    fmt = logging.Formatter(fmt="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    ch  = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger = logging.getLogger("rodage")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(ch)
    logger.propagate = False
    return logger


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log = _setup_logging()

    log.info("=" * 50)
    log.info("  RODAGE INDUSTRIEL")
    log.info(f"  Vanne    : {rcfg.VANNE_CLASSIQUE}")
    log.info(f"  V4V      : {rcfg.VIC_CYCLE_POSITIONS}")
    log.info(f"  Cycles   : {rcfg.TOTAL_CYCLES}")
    log.info(f"  Pauses   : open={rcfg.PAUSE_OPEN_S}s  close={rcfg.PAUSE_CLOSE_S}s")
    log.info("=" * 50)

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        with MotorController(io) as motors:

            vic_steps = 0   # position absolue V4V en pas

            # ── Initialisation ────────────────────────────────────────────────
            log.info("[INIT] V4V → butée position 1"
                     f" ({rcfg.VIC_INIT_STEPS} pas fermeture)")
            motors.move_steps("VIC", rcfg.VIC_INIT_STEPS,
                               "fermeture", v4cfg.VIC_SPEED_SPS)
            vic_steps = 0
            log.info("[INIT] V4V — position 1 OK")

            log.info(f"[INIT] Vanne {rcfg.VANNE_CLASSIQUE} → fermeture")
            move_vanne_classique(motors, "fermeture", rcfg.VANNE_CLASSIQUE)
            log.info(f"[INIT] Vanne {rcfg.VANNE_CLASSIQUE} — fermée")

            log.info("Démarrage des cycles\n")

            try:
                for cycle in range(1, rcfg.TOTAL_CYCLES + 1):
                    restant = rcfg.TOTAL_CYCLES - cycle
                    log.info(f"── CYCLE {cycle}/{rcfg.TOTAL_CYCLES}"
                             f"  ({restant} restant(s)) ──")

                    # ── V4V ──────────────────────────────────────────────────
                    for pos in rcfg.VIC_CYCLE_POSITIONS:
                        log.info(f"  [V4V] → position {pos}"
                                 f"  ({v4cfg.VIC_POSITIONS[pos]} pas)")
                        vic_steps = move_vic_to_position(motors, vic_steps, pos)
                        log.info(f"  [V4V]   position {pos} atteinte")

                    # ── Vanne classique ───────────────────────────────────────
                    log.info(f"  [VANNE] → OUVERTURE")
                    move_vanne_classique(motors, "ouverture", rcfg.VANNE_CLASSIQUE)
                    log.info(f"  [VANNE]   OUVERTE — pause {rcfg.PAUSE_OPEN_S}s")
                    time.sleep(rcfg.PAUSE_OPEN_S)

                    log.info(f"  [VANNE] → FERMETURE")
                    move_vanne_classique(motors, "fermeture", rcfg.VANNE_CLASSIQUE)
                    log.info(f"  [VANNE]   FERMEE  — pause {rcfg.PAUSE_CLOSE_S}s")
                    time.sleep(rcfg.PAUSE_CLOSE_S)

                    log.info(f"✓ Cycle {cycle}/{rcfg.TOTAL_CYCLES} terminé\n")

                log.info("=" * 50)
                log.info(f"  RODAGE TERMINE — {rcfg.TOTAL_CYCLES} cycles")
                log.info("=" * 50)

            except KeyboardInterrupt:
                log.info("\nCtrl+C — arrêt demandé")

            finally:
                # ── Sécurité ─────────────────────────────────────────────────
                log.info("[SECURITE] Vanne → ouverture")
                try:
                    move_vanne_classique(motors, "ouverture", rcfg.VANNE_CLASSIQUE)
                    log.info("[SECURITE] Vanne — ouverte")
                except Exception as e:
                    log.error(f"[SECURITE] Vanne : {e}")

                log.info(f"[SECURITE] V4V → position 1"
                         f" ({rcfg.VIC_INIT_STEPS} pas fermeture)")
                try:
                    motors.move_steps("VIC", rcfg.VIC_INIT_STEPS,
                                      "fermeture", v4cfg.VIC_SPEED_SPS)
                    log.info("[SECURITE] V4V — position 1 OK")
                except Exception as e:
                    log.error(f"[SECURITE] V4V : {e}")

                io.disable_all_drivers()
                log.info("[SECURITE] Drivers désactivés")

    gpio_handle.close()
    log.info("Fin du script")


if __name__ == "__main__":
    main()
