"""
test_ev_air.py — Test de l'electrovanne d'injection d'air (relais AIR) — V5.

Quatre phases progressives :

    Phase 1 — ON/OFF manuel
        L'utilisateur controle manuellement l'ouverture et la fermeture.
        Permet de verifier la reaction physique de l'EV (bruit, flux d'air).

    Phase 2 — Mode temporise (set_air_on + tick())
        L'EV s'ouvre puis se ferme automatiquement apres une duree fixee.
        Valide le mecanisme tick() utilise dans tous les programmes.

    Phase 3 — Cycle PRG1 (ON 4s / OFF 3s)
        Reproduit le cycle air du programme 1 (premiere vidange).
        Tourne jusqu'a Ctrl+C.

    Phase 4 — Cycle PRG3 (ON 8s / OFF 2s)
        Reproduit le cycle air du programme 3 (sechage).
        Tourne jusqu'a Ctrl+C.

Materiels impliques :
    GPIO 26 → relais AIR → EV air (contact NO, 24VDC)

Ctrl+C interrompt proprement chaque phase et ferme l'EV.
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


def _lcd_status(lcd: LCD2004, phase: str, detail: str, etat: bool, info: str = "") -> None:
    """Rafraichit les 4 lignes du LCD avec l'etat courant de l'EV."""
    etat_str = "OUVERTE (ON) " if etat else "FERMEE  (OFF)"
    lcd.write_centered(1, "TEST EV AIR")
    lcd.write(2, _pad(f"EV : {etat_str}"))
    lcd.write(3, _pad(phase))
    lcd.write(4, _pad(info if info else detail))


def _sep(title: str) -> None:
    print(f"\n{'=' * 54}")
    print(f"  {title}")
    print(f"{'=' * 54}")


# ============================================================
# Phase 1 — ON/OFF manuel
# ============================================================

def phase1_manuel(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 1 — ON/OFF MANUEL  (3 cycles)")
    print("  Appuyer sur Entree pour ouvrir / fermer l'EV.")
    print("  Ecouter le claquement de la vanne et verifier le flux d'air.")

    for i in range(1, 4):
        print(f"\n  --- Cycle {i}/3 ---")

        # ON
        print("  >>> Entree pour ouvrir l'EV (ON)...", end="", flush=True)
        input()
        relays.set_air_on()
        _lcd_status(lcd, f"Phase 1 — cycle {i}/3", "Manuel ON/OFF", True, "EV ouverte")
        print("  EV OUVERTE  — verifier flux d'air")

        # OFF
        print("  >>> Entree pour fermer l'EV (OFF)...", end="", flush=True)
        input()
        relays.set_air_off()
        _lcd_status(lcd, f"Phase 1 — cycle {i}/3", "Manuel ON/OFF", False, "EV fermee")
        print("  EV FERMEE")

        if i < 3:
            print("  >>> Entree pour le cycle suivant...", end="", flush=True)
            input()

    print("\n  Phase 1 terminee.")


# ============================================================
# Phase 2 — Mode temporise (set_air_on + tick())
# ============================================================

def _run_timed(lcd: LCD2004, relays: Relays, duration: float) -> None:
    """
    Ouvre l'EV pour `duration` secondes via set_air_on(time_s=).
    Appelle tick() a 10 Hz jusqu'a extinction automatique.
    """
    relays.set_air_on(time_s=duration)
    t0 = time.monotonic()

    while relays.air_is_on:
        relays.tick()
        elapsed   = time.monotonic() - t0
        remaining = max(0.0, duration - elapsed)
        info      = f"Reste : {remaining:.1f}s"
        _lcd_status(lcd, "Phase 2 — temporise", f"ON {duration:.0f}s auto", True, info)
        print(f"  EV OUVERTE — extinction dans {remaining:.1f}s     \r", end="", flush=True)
        time.sleep(0.1)

    print()
    _lcd_status(lcd, "Phase 2 — temporise", f"ON {duration:.0f}s auto", False, "Extinction auto OK")
    print(f"  EV FERMEE automatiquement apres {duration:.0f}s  OK")
    time.sleep(1.5)


def phase2_timed(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 2 — MODE TEMPORISE (set_air_on + tick())")
    print("  L'EV s'ouvre puis se ferme seule a l'expiration du timer.")
    print("  Valide le mecanisme utilise dans tous les programmes.")

    for duration in (3.0, 5.0, 10.0):
        print(f"\n  Test {duration:.0f}s :")
        print(f"  >>> Entree pour lancer ON {duration:.0f}s...", end="", flush=True)
        input()
        _lcd_status(lcd, "Phase 2 — temporise", f"ON {duration:.0f}s auto", True)
        _run_timed(lcd, relays, duration)

    print("\n  Phase 2 terminee.")


# ============================================================
# Phase 3 — Cycle PRG1 (ON 4s / OFF 3s)
# ============================================================

def phase3_cycle_prg1(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 3 — CYCLE PRG1  (ON 4s / OFF 3s)")
    print("  Reproduit le cycle air du programme 1 (premiere vidange).")
    print("  Ctrl+C pour arreter et passer a la phase 4.")
    print()
    print("  >>> Entree pour demarrer...", end="", flush=True)
    input()

    on_s  = config.PRG1_AIR_ON_S
    off_s = config.PRG1_AIR_OFF_S
    cycle = 1
    air_on = True
    relays.set_air_on()
    deadline = time.monotonic() + on_s

    try:
        while True:
            now       = time.monotonic()
            remaining = max(0.0, deadline - now)

            if now >= deadline:
                if air_on:
                    relays.set_air_off()
                    air_on   = False
                    deadline = now + off_s
                    print(f"\n  Cycle {cycle} — EV FERMEE")
                else:
                    cycle += 1
                    relays.set_air_on()
                    air_on   = True
                    deadline = now + on_s
                    print(f"\n  Cycle {cycle} — EV OUVERTE")

            phase_str = f"ON {on_s:.0f}s/OFF {off_s:.0f}s"
            etat_str  = "OUVERTE" if air_on else "FERMEE "
            info      = f"Cycle {cycle}  reste {remaining:.1f}s"
            _lcd_status(lcd, "Phase 3 — PRG1", phase_str, air_on, info)
            print(f"  EV {etat_str}  cycle {cycle}  reste {remaining:.1f}s     \r",
                  end="", flush=True)
            time.sleep(0.1)

    except KeyboardInterrupt:
        relays.set_air_off()
        _lcd_status(lcd, "Phase 3 — PRG1", "Arret", False, "EV fermee")
        print(f"\n  Arret apres {cycle} cycle(s).")


# ============================================================
# Phase 4 — Cycle PRG3 (ON 8s / OFF 2s)
# ============================================================

def phase4_cycle_prg3(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 4 — CYCLE PRG3  (ON 8s / OFF 2s)")
    print("  Reproduit le cycle air du programme 3 (sechage).")
    print("  Ctrl+C pour arreter.")
    print()
    print("  >>> Entree pour demarrer...", end="", flush=True)
    input()

    on_s  = config.PRG3_AIR_ON_S
    off_s = config.PRG3_AIR_OFF_S
    cycle = 1
    air_on = True
    relays.set_air_on()
    deadline = time.monotonic() + on_s

    try:
        while True:
            now       = time.monotonic()
            remaining = max(0.0, deadline - now)

            if now >= deadline:
                if air_on:
                    relays.set_air_off()
                    air_on   = False
                    deadline = now + off_s
                    print(f"\n  Cycle {cycle} — EV FERMEE")
                else:
                    cycle += 1
                    relays.set_air_on()
                    air_on   = True
                    deadline = now + on_s
                    print(f"\n  Cycle {cycle} — EV OUVERTE")

            phase_str = f"ON {on_s:.0f}s/OFF {off_s:.0f}s"
            etat_str  = "OUVERTE" if air_on else "FERMEE "
            info      = f"Cycle {cycle}  reste {remaining:.1f}s"
            _lcd_status(lcd, "Phase 4 — PRG3", phase_str, air_on, info)
            print(f"  EV {etat_str}  cycle {cycle}  reste {remaining:.1f}s     \r",
                  end="", flush=True)
            time.sleep(0.1)

    except KeyboardInterrupt:
        relays.set_air_off()
        _lcd_status(lcd, "Phase 4 — PRG3", "Arret", False, "EV fermee")
        print(f"\n  Arret apres {cycle} cycle(s).")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST ELECTROVANNE AIR — Clean & Protech V5")
    print("=" * 54)
    print(f"  Relais AIR : GPIO {config.RELAY_AIR_GPIO} (actif haut, contact NO)")
    print(f"  EV         : 24VDC, normalement fermee")
    print(f"  Cycles     : PRG1={config.PRG1_AIR_ON_S:.0f}s/{config.PRG1_AIR_OFF_S:.0f}s  "
          f"PRG3={config.PRG3_AIR_ON_S:.0f}s/{config.PRG3_AIR_OFF_S:.0f}s")
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
            phase3_cycle_prg1(lcd, relays)
            phase4_cycle_prg3(lcd, relays)

        except KeyboardInterrupt:
            print("\n\n  Arret global (Ctrl+C)")

        finally:
            relays.set_air_off()
            relays.close()
            lcd.clear()
            lcd.write_centered(1, "TEST EV AIR")
            lcd.write_centered(2, "Termine")
            lcd.write_centered(3, "EV fermee")

    gpio_handle.close()
    print("=== FIN TEST EV AIR ===")


if __name__ == "__main__":
    main()
