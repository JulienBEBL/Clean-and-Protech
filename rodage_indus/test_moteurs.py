"""
test_moteurs.py — Identification et test du câblage physique des moteurs.

Active POMPE puis VIC, fait quelques pas dans chaque sens.
Permet de confirmer auditivement / visuellement quel moteur répond
sur quel port avant de lancer le rodage.

Lancement depuis Geany (bouton Run) :
    Répertoire de travail = rodage_indus/
    python3 test_moteurs.py

Ajuster N_STEPS_POMPE, N_STEPS_VIC et SPEED_SPS si besoin.
"""

from __future__ import annotations

import logging
import sys
import time
import traceback

# Constantes hardware exposées par stepper (module-level, lecture seule)
import stepper as _s
from stepper import RodageDriver

# ── Paramètres du test ────────────────────────────────────────────────────────

N_STEPS_POMPE: int   = 400    # pas test POMPE (~1 tour à 400 pas/tr)
N_STEPS_VIC:   int   =  30    # pas test VIC   (pos 1 → pos 2 = 30 pas)
SPEED_POMPE:   float = 400.0  # sps — lent pour identification visuelle
SPEED_VIC:     float =  20.0  # sps — vitesse nominale VIC
PAUSE_S:       float =   1.0  # pause entre aller et retour


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
    """Attend une frappe Entrée ; passe silencieusement si stdin est fermé (Geany)."""
    print(prompt, flush=True)
    try:
        input()
    except EOFError:
        time.sleep(1.0)


# ── Séquence de test pour un moteur ──────────────────────────────────────────

def _test_un_moteur(
    log: logging.Logger,
    drv: RodageDriver,
    nom: str,
    bcm: int,
    ena_pin: int,
    dir_pin: int,
    n_steps: int,
    speed_sps: float,
) -> None:
    """
    Fait n_steps dans le sens ouverture, pause, puis n_steps fermeture.
    Active / désactive l'ENA autour du mouvement.
    """
    half_us = drv._half_us(speed_sps)

    log.info(f"  [{nom}] → OUVERTURE  ({n_steps} pas @ {speed_sps:.0f} sps)")
    drv._set_dir(dir_pin, ouverture=True)
    drv._set_ena(ena_pin, _s._ENA_ON)
    time.sleep(_s._ENA_SETTLE_MS / 1000.0)
    drv._pulse_n(bcm, n_steps, half_us)
    log.info(f"  [{nom}]   {n_steps} pas ouverture OK")

    time.sleep(PAUSE_S)

    log.info(f"  [{nom}] → FERMETURE  ({n_steps} pas @ {speed_sps:.0f} sps)")
    drv._set_dir(dir_pin, ouverture=False)
    drv._pulse_n(bcm, n_steps, half_us)
    drv._set_ena(ena_pin, _s._ENA_OFF)
    log.info(f"  [{nom}]   {n_steps} pas fermeture OK")
    log.info(f"  [{nom}]   TEST TERMINE\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log = _setup_logging()

    log.info("=" * 54)
    log.info("  TEST MOTEURS — Clean & Protech (SERENA)")
    log.info(f"  POMPE : ID=8  GPIO BCM={_s._POMPE_BCM}"
             f"  ENA=B{_s._POMPE_ENA_PIN}  DIR=A{_s._POMPE_DIR_PIN}")
    log.info(f"  VIC   : ID=3  GPIO BCM={_s._VIC_BCM}"
             f"  ENA=B{_s._VIC_ENA_PIN}  DIR=A{_s._VIC_DIR_PIN}")
    log.info("=" * 54)

    _pause_entree(">>> [Entrée] pour démarrer le test POMPE, ou fermez pour annuler")

    with RodageDriver() as drv:
        try:

            # ── TEST POMPE ────────────────────────────────────────────────────
            log.info(f"\n── TEST 1 : POMPE  (ID=8, GPIO BCM {_s._POMPE_BCM}) ──")
            _test_un_moteur(
                log, drv,
                nom="POMPE",
                bcm=_s._POMPE_BCM,
                ena_pin=_s._POMPE_ENA_PIN,
                dir_pin=_s._POMPE_DIR_PIN,
                n_steps=N_STEPS_POMPE,
                speed_sps=SPEED_POMPE,
            )

            _pause_entree(">>> [Entrée] pour démarrer le test VIC")

            # ── TEST VIC ──────────────────────────────────────────────────────
            log.info(f"── TEST 2 : VIC    (ID=3, GPIO BCM {_s._VIC_BCM}) ──")

            log.info(f"  [VIC]   → butée position 1 (110 pas fermeture)")
            drv.vic_home(110)
            log.info(f"  [VIC]     position 1 OK  (0 pas abs)")
            time.sleep(PAUSE_S)

            _test_un_moteur(
                log, drv,
                nom="VIC",
                bcm=_s._VIC_BCM,
                ena_pin=_s._VIC_ENA_PIN,
                dir_pin=_s._VIC_DIR_PIN,
                n_steps=N_STEPS_VIC,
                speed_sps=SPEED_VIC,
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
