"""
test_relay_pompe.py — Test du relais POMPE — V5.

Trois phases progressives :

    Phase 1 — ON/OFF manuel
        L'utilisateur controle manuellement le demarrage et l'arret de la pompe.
        Permet de verifier la reaction du variateur (demarrage moteur, bruit).

    Phase 2 — ON temporise
        La pompe demarre puis s'arrete automatiquement apres une duree fixee.
        Tester 5s / 10s / 30s pour valider le cycle de demarrage-arret.

    Phase 3 — ON continu
        La pompe tourne jusqu'a Ctrl+C.
        Permet une inspection prolongee (debit, temperature, vibrations).

Materiels impliques :
    GPIO 19 → relais POMPE → cable ON du variateur de vitesse
    Pompe ON  : GPIO HIGH → relais ON  → variateur reoit commande ON → pompe tourne
    Pompe OFF : GPIO LOW  → relais OFF → commande ON inactive → pompe arret

ATTENTION : ne pas faire tourner la pompe a sec plus de quelques secondes.
Ctrl+C interrompt proprement chaque phase et coupe la pompe.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
import libs.gpio_handle as gpio_handle
from libs.i2c_bus import I2CBus
from libs.lcd2004 import LCD2004
from libs.relays import Relays

_COLS = config.LCD_COLS  # 20


# ============================================================
# Helpers LCD
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _lcd_status(lcd: LCD2004, phase: str, etat: bool, info: str = "") -> None:
    """Rafraichit les 4 lignes du LCD avec l'etat courant du relais POMPE."""
    etat_str = "MARCHE  (ON) " if etat else "ARRET   (OFF)"
    lcd.write_centered(1, "TEST RELAIS POMPE")
    lcd.write(2, _pad(f"POMPE : {etat_str}"))
    lcd.write(3, _pad(phase))
    lcd.write(4, _pad(info))


def _sep(title: str) -> None:
    print(f"\n{'=' * 54}")
    print(f"  {title}")
    print(f"{'=' * 54}")


# ============================================================
# Phase 1 — ON/OFF manuel
# ============================================================

def phase1_manuel(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 1 — ON/OFF MANUEL  (3 cycles)")
    print("  Appuyer sur Entree pour demarrer / arreter la pompe.")
    print("  Verifier le demarrage du variateur et la rotation de la pompe.")
    print("  ATTENTION : ne pas faire tourner la pompe a sec.")

    for i in range(1, 4):
        print(f"\n  --- Cycle {i}/3 ---")

        # ON
        print("  >>> Entree pour demarrer la pompe (ON)...", end="", flush=True)
        input()
        relays.set_pompe_on()
        _lcd_status(lcd, f"Phase 1 — cycle {i}/3", True, "Pompe en marche")
        print("  POMPE ON  — verifier rotation + debit")

        # OFF
        print("  >>> Entree pour arreter la pompe (OFF)...", end="", flush=True)
        input()
        relays.set_pompe_off()
        _lcd_status(lcd, f"Phase 1 — cycle {i}/3", False, "Pompe arretee")
        print("  POMPE OFF")

        if i < 3:
            print("  >>> Entree pour le cycle suivant...", end="", flush=True)
            input()

    print("\n  Phase 1 terminee.")


# ============================================================
# Phase 2 — ON temporise
# ============================================================

def _run_timed_pompe(lcd: LCD2004, relays: Relays, duration: float) -> None:
    """Demarre la pompe, affiche un compte a rebours, puis arrete."""
    relays.set_pompe_on()
    t0 = time.monotonic()

    try:
        while True:
            elapsed   = time.monotonic() - t0
            remaining = max(0.0, duration - elapsed)
            info      = f"Reste : {remaining:.1f}s"
            _lcd_status(lcd, f"Phase 2 — {duration:.0f}s", True, info)
            print(f"  POMPE ON — arret dans {remaining:.1f}s     \r", end="", flush=True)

            if elapsed >= duration:
                break
            time.sleep(0.1)

    except KeyboardInterrupt:
        pass

    relays.set_pompe_off()
    print()
    _lcd_status(lcd, f"Phase 2 — {duration:.0f}s", False, f"Arret apres {duration:.0f}s")
    print(f"  POMPE OFF apres {duration:.0f}s")
    time.sleep(2.0)


def phase2_timed(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 2 — ON TEMPORISE  (5s / 10s / 30s)")
    print("  La pompe demarre et s'arrete automatiquement.")
    print("  Valide le cycle demarrage-arret avec durees progressives.")
    print("  ATTENTION : ne pas faire tourner la pompe a sec.")

    for duration in (5.0, 10.0, 30.0):
        print(f"\n  Test {duration:.0f}s :")
        print(f"  >>> Entree pour lancer ON {duration:.0f}s...", end="", flush=True)
        input()
        _lcd_status(lcd, f"Phase 2 — {duration:.0f}s", True)
        _run_timed_pompe(lcd, relays, duration)

    print("\n  Phase 2 terminee.")


# ============================================================
# Phase 3 — ON continu (Ctrl+C pour arreter)
# ============================================================

def phase3_continu(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 3 — ON CONTINU  (Ctrl+C pour arreter)")
    print("  La pompe tourne jusqu'a Ctrl+C.")
    print("  Inspection prolongee : debit, temperature, vibrations.")
    print("  ATTENTION : ne pas faire tourner la pompe a sec.")
    print()
    print("  >>> Entree pour demarrer...", end="", flush=True)
    input()

    relays.set_pompe_on()
    t0 = time.monotonic()

    try:
        while True:
            elapsed = time.monotonic() - t0
            m = int(elapsed) // 60
            s = int(elapsed) % 60
            info = f"Duree : {m:02d}:{s:02d}"
            _lcd_status(lcd, "Phase 3 — continu", True, info)
            print(f"  POMPE ON — duree {m:02d}:{s:02d}     \r", end="", flush=True)
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    relays.set_pompe_off()
    elapsed = time.monotonic() - t0
    m = int(elapsed) // 60
    s = int(elapsed) % 60
    print(f"\n  POMPE OFF — duree totale {m:02d}:{s:02d}")
    _lcd_status(lcd, "Phase 3 — continu", False, f"Duree {m:02d}:{s:02d}")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST RELAIS POMPE — Clean & Protech V5")
    print("=" * 54)
    print(f"  Relais POMPE : GPIO {config.RELAY_POMPE_GPIO} (actif haut)")
    print(f"  Logique      : GPIO HIGH → variateur ON → pompe tourne")
    print(f"  ATTENTION    : ne pas faire tourner la pompe a sec !")
    print("  Ctrl+C pour quitter proprement\n")

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()

        relays = Relays()
        relays.open()

        try:
            phase1_manuel(lcd, relays)
            phase2_timed(lcd, relays)
            phase3_continu(lcd, relays)

        except KeyboardInterrupt:
            print("\n\n  Arret global (Ctrl+C)")

        finally:
            relays.set_pompe_off()
            relays.close()
            lcd.clear()
            lcd.write_centered(1, "TEST RELAIS POMPE")
            lcd.write_centered(2, "Termine")
            lcd.write_centered(3, "Pompe arretee")

    gpio_handle.close()
    print("=== FIN TEST RELAIS POMPE ===")


if __name__ == "__main__":
    main()
