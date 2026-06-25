"""
test_vannes_us.py — Test complet des 4 vannes US Solid — mode programme — V5.

Simule la configuration de vannes de chacun des 5 programmes :
    PRG1  PREM.VIDANGE  : POT_A_BOUE
    PRG2  VIDANGE CUVE  : CUVE_TRAVAIL + EGOUTS
    PRG3  SECHAGE       : aucune vanne
    PRG4  REMPLISSAGE   : EAU_PROPRE + POT_A_BOUE
    PRG5  DESEMBOUAGE   : POT_A_BOUE + CUVE_TRAVAIL

Regles appliquees (identiques a programs.py) :
    - Ouverture 1 vanne a la fois : relay ON  -> attente VALVE_OPEN_CAPACITOR_CHARGE_S
    - Fermeture 1 vanne a la fois : relay OFF -> attente VALVE_CLOSE_TRAVEL_S

Pour chaque programme :
    1. Presse Entree pour demarrer
    2. Ouverture de chaque vanne requise (sequentielle)
    3. Phase observation (OBS_S secondes)
    4. Fermeture de chaque vanne ouverte (sequentielle)

GPIO impliques :
    GPIO  7 -> relais V1 -> vanne POT_A_BOUE   (US Solid 24VDC NO)
    GPIO  8 -> relais V2 -> vanne EGOUTS        (US Solid 24VDC NO)
    GPIO 25 -> relais V3 -> vanne CUVE_TRAVAIL  (US Solid 24VDC NO)
    GPIO 24 -> relais V4 -> vanne EAU_PROPRE    (US Solid 24VDC NO)

Ctrl+C ferme toutes les vannes et quitte proprement.
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

# ============================================================
# Constantes
# ============================================================

_COLS = config.LCD_COLS  # 20

OBS_S: float = 5.0  # duree observation toutes vannes ouvertes

_SHORT: dict[str, str] = {
    "POT_A_BOUE":   "PAB",
    "EGOUTS":       "EGO",
    "CUVE_TRAVAIL": "CUV",
    "EAU_PROPRE":   "EAU",
}

_GPIO: dict[str, int] = {
    "POT_A_BOUE":   config.RELAY_POT_A_BOUE_GPIO,
    "EGOUTS":       config.RELAY_EGOUTS_GPIO,
    "CUVE_TRAVAIL": config.RELAY_CUVE_TRAVAIL_GPIO,
    "EAU_PROPRE":   config.RELAY_EAU_PROPRE_GPIO,
}

# (id, nom, vannes a ouvrir dans l'ordre)
_PROGRAMS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "PREM.VIDANGE", ("POT_A_BOUE",)),
    (2, "VIDANGE CUVE",  ("CUVE_TRAVAIL", "EGOUTS")),
    (3, "SECHAGE",       ()),
    (4, "REMPLISSAGE",   ("EAU_PROPRE", "POT_A_BOUE")),
    (5, "DESEMBOUAGE",   ("POT_A_BOUE", "CUVE_TRAVAIL")),
)


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _sep(title: str) -> None:
    print(f"\n{'=' * 54}")
    print(f"  {title}")
    print(f"{'=' * 54}")


def _countdown_valve(
    lcd: LCD2004,
    prg_title: str,
    valve_name: str,
    action: str,
    duration: float,
) -> None:
    """Compte a rebours pendant une ouverture ou fermeture de vanne."""
    t0 = time.monotonic()
    while True:
        elapsed   = time.monotonic() - t0
        remaining = max(0.0, duration - elapsed)
        lcd.write_centered(1, prg_title)
        lcd.write(2, _pad(valve_name))
        lcd.write(3, _pad(action))
        lcd.write(4, _pad(f"Attente : {remaining:5.1f}s"))
        print(f"    {action:<22} {remaining:5.1f}s\r", end="", flush=True)
        if elapsed >= duration:
            break
        time.sleep(0.1)
    print()


def _countdown_obs(
    lcd: LCD2004,
    prg_id: int,
    prg_name: str,
    open_set: set[str],
    duration: float,
) -> None:
    """Compte a rebours d'observation — affiche l'etat des 4 vannes sur LCD."""
    pab = f"PAB:{'ON ' if 'POT_A_BOUE'   in open_set else 'OFF'}"
    ego = f"EGO:{'ON ' if 'EGOUTS'       in open_set else 'OFF'}"
    cuv = f"CUV:{'ON ' if 'CUVE_TRAVAIL' in open_set else 'OFF'}"
    eau = f"EAU:{'ON ' if 'EAU_PROPRE'   in open_set else 'OFF'}"
    t0 = time.monotonic()
    while True:
        elapsed   = time.monotonic() - t0
        remaining = max(0.0, duration - elapsed)
        lcd.write_centered(1, f"PRG{prg_id} {prg_name}")
        lcd.write(2, _pad(f"{pab}  {ego}"))
        lcd.write(3, _pad(f"{cuv}  {eau}"))
        lcd.write(4, _pad(f"Actif   {remaining:.1f}s"))
        print(f"    Observation...          {remaining:.1f}s\r", end="", flush=True)
        if elapsed >= duration:
            break
        time.sleep(0.1)
    print()


# ============================================================
# Test d'un programme
# ============================================================

def _test_program(
    lcd: LCD2004,
    relays: Relays,
    prg_id: int,
    prg_name: str,
    open_valves: tuple[str, ...],
) -> None:
    open_s  = config.VALVE_OPEN_CAPACITOR_CHARGE_S
    close_s = config.VALVE_CLOSE_TRAVEL_S
    title   = f"PRG{prg_id} {prg_name}"

    _sep(f"PRG{prg_id} — {prg_name}")

    if open_valves:
        for name in open_valves:
            print(f"  {name:<14}  GPIO {_GPIO[name]}")
        print(f"\n  Ouverture  : 1 par 1, {open_s:.0f}s apres chaque relay ON")
        print(f"  Fermeture  : 1 par 1, {close_s:.0f}s apres chaque relay OFF")
        print(f"  Observation: {OBS_S:.0f}s")
    else:
        print("  Aucune vanne requise pour ce programme")

    print()
    print(f"  >>> Entree pour lancer PRG{prg_id}...", end="", flush=True)
    input()

    open_set: set[str] = set()

    # ---- Ouverture sequentielle ----
    for name in open_valves:
        print(f"\n  {name}  relay ON — ouverture + charge condensateur ({open_s:.0f}s)...")
        relays.open_valve(name)
        open_set.add(name)
        _countdown_valve(lcd, title, name, "Relay ON  ouverture", open_s)
        print(f"  {name}  ouverte")

    # ---- Observation ----
    print()
    _countdown_obs(lcd, prg_id, prg_name, open_set, OBS_S)

    # ---- Fermeture sequentielle ----
    for name in open_valves:
        print(f"\n  {name}  relay OFF — course fermeture ({close_s:.0f}s)...")
        relays.close_valve(name)
        open_set.discard(name)
        _countdown_valve(lcd, title, name, "Relay OFF fermeture", close_s)
        print(f"  {name}  en butee fermee")

    print(f"\n  PRG{prg_id} termine — toutes vannes fermees")


# ============================================================
# Main
# ============================================================

def main() -> None:
    open_s  = config.VALVE_OPEN_CAPACITOR_CHARGE_S
    close_s = config.VALVE_CLOSE_TRAVEL_S

    print("=" * 54)
    print("  TEST VANNES US SOLID — mode programme — V5")
    print("=" * 54)
    print()
    print("  Vannes testees :")
    for name, gpio in _GPIO.items():
        short = _SHORT[name]
        print(f"    {short}  {name:<14}  GPIO {gpio}")
    print()
    print(f"  Ouverture  : VALVE_OPEN_CAPACITOR_CHARGE_S = {open_s:.0f}s")
    print(f"  Fermeture  : VALVE_CLOSE_TRAVEL_S          = {close_s:.0f}s")
    print()
    print("  Sequences :")
    for prg_id, prg_name, valves in _PROGRAMS:
        v_str = " + ".join(_SHORT[v] for v in valves) if valves else "aucune"
        print(f"    PRG{prg_id}  {prg_name:<14}  {v_str}")
    print()
    print("  Ctrl+C pour quitter proprement")
    print()

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST VANNES MODE")
        lcd.write_centered(2, "PROGRAMME")
        lcd.write_centered(3, f"ouv:{open_s:.0f}s  ferm:{close_s:.0f}s")
        lcd.write_centered(4, "Pret")

        relays = Relays()
        relays.open()

        try:
            for prg_id, prg_name, open_valves in _PROGRAMS:
                _test_program(lcd, relays, prg_id, prg_name, open_valves)

            print()
            _sep("TEST TERMINE")
            print("  Toutes les sequences executees avec succes.")
            lcd.clear()
            lcd.write_centered(1, "TEST TERMINE")
            lcd.write_centered(2, "Toutes sequences")
            lcd.write_centered(3, "OK")

        except KeyboardInterrupt:
            print("\n\n  Arret (Ctrl+C) — fermeture toutes vannes")

        finally:
            relays.close_all_valves()
            relays.close()
            lcd.clear()
            lcd.write_centered(1, "TEST VANNES")
            lcd.write_centered(2, "Arret propre")
            lcd.write_centered(3, "Toutes fermees")

    gpio_handle.close()
    print("=== FIN TEST VANNES US SOLID MODE PROGRAMME ===")


if __name__ == "__main__":
    main()
