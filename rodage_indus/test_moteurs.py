"""
test_moteurs.py — Identification et test du câblage physique des 4 vannes.

Teste chaque vanne une par une : quelques pas fermeture, pause, puis ouverture.
Permet de confirmer auditivement / visuellement que chaque driver répond
sur le bon port avant de lancer le rodage.

Lancement depuis Geany (bouton Run) :
    Répertoire de travail = rodage_indus/
    python3 test_moteurs.py

Ajuster N_STEPS et SPEED_SPS si besoin.
"""

from __future__ import annotations

import logging
import sys
import time
import traceback

import stepper as _s
from stepper import RodageDriver, VALVES

# ── Paramètres du test ────────────────────────────────────────────────────────

N_STEPS:   int   = 400    # pas par sens (~1 tour à 400 pas/tr)
SPEED_SPS: float = 400.0  # sps — lent pour identification visuelle/auditive
PAUSE_S:   float =   1.0  # pause entre sens fermeture et ouverture


# ── Logging console ───────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    fmt = logging.Formatter(fmt="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    ch  = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log = logging.getLogger("test_moteurs")
    log.setLevel(logging.DEBUG)
    log.addHandler(ch)
    log.propagate = False
    return log


def _pause_entree(prompt: str) -> None:
    print(prompt, flush=True)
    try:
        input()
    except EOFError:
        time.sleep(1.0)


# ── Test d'une vanne ──────────────────────────────────────────────────────────

def _test_valve(
    log: logging.Logger,
    drv: RodageDriver,
    valve: _s.ValveDef,
) -> None:
    """
    Fait N_STEPS en fermeture, pause, puis N_STEPS en ouverture.
    Active / désactive l'ENA autour du mouvement.
    """
    half_us = drv._half_us(SPEED_SPS)

    log.info(f"  [{valve.name}] → FERMETURE  ({N_STEPS} pas @ {SPEED_SPS:.0f} sps)")
    drv._set_dir(valve.dir_pin, ouverture=False)
    drv._set_ena(valve.ena_pin, _s._ENA_ON)
    time.sleep(_s._ENA_SETTLE_MS / 1000.0)
    drv._pulse_n(valve.bcm, N_STEPS, half_us)
    log.info(f"  [{valve.name}]   {N_STEPS} pas fermeture OK")

    time.sleep(PAUSE_S)

    log.info(f"  [{valve.name}] → OUVERTURE  ({N_STEPS} pas @ {SPEED_SPS:.0f} sps)")
    drv._set_dir(valve.dir_pin, ouverture=True)
    drv._pulse_n(valve.bcm, N_STEPS, half_us)
    drv._set_ena(valve.ena_pin, _s._ENA_OFF)
    log.info(f"  [{valve.name}]   {N_STEPS} pas ouverture OK")
    log.info(f"  [{valve.name}]   TEST TERMINE\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log = _setup_logging()

    log.info("=" * 54)
    log.info("  TEST MOTEURS — Clean & Protech (SERENA)")
    log.info(f"  Pas / sens : {N_STEPS}  @  {SPEED_SPS:.0f} sps")
    for v in VALVES:
        log.info(
            f"  {v.name:<14} driver_id={v.driver_id}"
            f"  BCM={v.bcm}  ENA=B{v.ena_pin}  DIR=A{v.dir_pin}"
        )
    log.info("=" * 54)

    _pause_entree(">>> [Entrée] pour démarrer le test, ou fermez pour annuler")

    with RodageDriver() as drv:
        try:
            for i, valve in enumerate(VALVES):
                log.info(
                    f"\n── TEST {i + 1}/{len(VALVES)} :"
                    f" {valve.name}  (driver ID {valve.driver_id},"
                    f" GPIO BCM {valve.bcm}) ──"
                )
                _test_valve(log, drv, valve)

                if i < len(VALVES) - 1:
                    _pause_entree(
                        f">>> [Entrée] pour tester {VALVES[i + 1].name}"
                        f" (driver ID {VALVES[i + 1].driver_id})"
                    )

        except KeyboardInterrupt:
            log.info("\nCtrl+C — test interrompu")
        except Exception:
            log.error("EXCEPTION — traceback complet :")
            log.error(traceback.format_exc())
        finally:
            drv.disable_all()
            log.info("[SECURITE] Drivers désactivés")
            log.info("Fin du test moteurs")


if __name__ == "__main__":
    main()
