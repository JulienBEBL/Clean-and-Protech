"""
rodage.py — Rodage industriel Clean & Protech V4 (SERENA).

Séquence par cycle (séquentielle — une vanne à la fois) :
    Pour chaque vanne [POMPE, RETOUR, CUVE_TRAVAIL, EAU_PROPRE] :
        1. Fermeture complète → pause PAUSE_CLOSE_S
        2. Ouverture complète → pause PAUSE_OPEN_S

1 cycle = les 4 vannes ont chacune fait fermeture + ouverture.

Lancement depuis Geany (bouton Run) :
    Répertoire de travail = rodage_indus/
    python3 rodage.py
"""

from __future__ import annotations

import logging
import sys
import time
import traceback

from config import TOTAL_CYCLES, PAUSE_OPEN_S, PAUSE_CLOSE_S
from stepper import RodageDriver, VALVES


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
    log.info(f"  Vannes    : {[v.name for v in VALVES]}")
    log.info(f"  Cycles    : {TOTAL_CYCLES}")
    log.info(f"  Pauses    : close={PAUSE_CLOSE_S}s  open={PAUSE_OPEN_S}s")
    log.info(f"  Drivers   : 400 pas/tour  |  ENA actif bas")
    log.info(f"  Câblage   : " + "  ".join(
        f"{v.name}=drv{v.driver_id}" for v in VALVES
    ))
    log.info("=" * 54)

    with RodageDriver() as drv:

        completed: int = 0   # nombre de cycles terminés avec succès

        try:
            # ── Initialisation — fermeture de toutes les vannes ───────────────
            log.info("[INIT] Fermeture initiale de toutes les vannes")
            for valve in VALVES:
                log.info(f"  [INIT] {valve.name} → fermeture")
                drv.move_valve(valve, "fermeture")
                log.info(f"  [INIT] {valve.name} — fermée")
            log.info("[INIT] Toutes les vannes fermées — démarrage cycles\n")

            # ── Boucle principale ─────────────────────────────────────────────
            for cycle in range(1, TOTAL_CYCLES + 1):
                log.info(f"── CYCLE {cycle}/{TOTAL_CYCLES} ──")

                for valve in VALVES:
                    # 1. Fermeture
                    log.info(f"  [{valve.name}] → FERMETURE")
                    drv.move_valve(valve, "fermeture")
                    log.info(f"  [{valve.name}]   FERMEE  — pause {PAUSE_CLOSE_S}s")
                    time.sleep(PAUSE_CLOSE_S)

                    # 2. Ouverture
                    log.info(f"  [{valve.name}] → OUVERTURE")
                    drv.move_valve(valve, "ouverture")
                    log.info(f"  [{valve.name}]   OUVERTE — pause {PAUSE_OPEN_S}s")
                    time.sleep(PAUSE_OPEN_S)

                completed = cycle
                log.info(
                    f"[Cycle {cycle}/{TOTAL_CYCLES}]"
                    f"  POMPE RETOUR CUVE_TRAVAIL EAU_PROPRE : OPEN\n"
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
            log.info("[SECURITE] Ouverture de toutes les vannes")
            for valve in VALVES:
                try:
                    drv.move_valve(valve, "ouverture")
                    log.info(f"[SECURITE] {valve.name} — ouverte")
                except Exception as exc:
                    log.error(f"[SECURITE] {valve.name} : {exc}")

            drv.disable_all()
            log.info("[SECURITE] Drivers désactivés")
            log.info(
                f"Arrêt  —  cycle {completed}/{TOTAL_CYCLES}"
                f"  |  Toutes vannes : OPEN"
            )


if __name__ == "__main__":
    main()
