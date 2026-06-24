"""
test_vannes_us.py — Test des 4 vannes US Solid 24VDC — V5.

Logique charge condensateurs (identique a main.py / programs.py) :
    Phase 0  : toutes les vannes alimentees pendant VALVE_STARTUP_CAPACITOR_CHARGE_S (10s)
               -> charge initiale complete avant tout cycle.
    Phases 1/2/3 : apres chaque ouverture, attente VALVE_OPEN_CAPACITOR_CHARGE_S (5s)
               avant l'action suivante (observation, fermeture...).

Trois phases de test :

    Phase 1 — Une par une
        Chaque vanne s'ouvre individuellement.
        Attente VALVE_OPEN_CAPACITOR_CHARGE_S, puis observation 5s, puis fermeture.
        Entree pour lancer chaque vanne.

    Phase 2 — Toutes ensemble
        Les 4 vannes s'ouvrent simultanement.
        Attente VALVE_OPEN_CAPACITOR_CHARGE_S, observation 5s, fermeture.

    Phase 3 — Simulation programmes (5s actives par programme)
        Reproduit la configuration de vannes de chaque programme :
            PRG1 : POT_A_BOUE
            PRG2 : CUVE_TRAVAIL + EGOUTS
            PRG3 : aucune (toutes fermees)
            PRG4 : EAU_PROPRE + POT_A_BOUE
            PRG5 : POT_A_BOUE + CUVE_TRAVAIL
        Pour chaque PRG : ouverture -> VALVE_OPEN_CAPACITOR_CHARGE_S -> 5s actif -> fermeture.

Materiels impliques :
    GPIO  7 → relais V1 → vanne POT_A_BOUE   (US Solid 24VDC NO)
    GPIO  8 → relais V2 → vanne EGOUTS        (US Solid 24VDC NO)
    GPIO 25 → relais V3 → vanne CUVE_TRAVAIL  (US Solid 24VDC NO)
    GPIO 24 → relais V4 → vanne EAU_PROPRE    (US Solid 24VDC NO)

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

_COLS = config.LCD_COLS  # 20

_ALL_VALVES: tuple[str, ...] = ("POT_A_BOUE", "EGOUTS", "CUVE_TRAVAIL", "EAU_PROPRE")

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

# Configurations vannes des 5 programmes
_PRG_VALVES: dict[int, tuple[str, ...]] = {
    1: ("POT_A_BOUE",),
    2: ("CUVE_TRAVAIL", "EGOUTS"),
    3: (),
    4: ("EAU_PROPRE", "POT_A_BOUE"),
    5: ("POT_A_BOUE", "CUVE_TRAVAIL"),
}
_PRG_NAMES: dict[int, str] = {
    1: "PREM.VIDANGE",
    2: "VIDANGE CUVE",
    3: "SECHAGE",
    4: "REMPLISSAGE",
    5: "DESEMBOUAGE",
}


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _valve_line(open_valves: tuple[str, ...]) -> str:
    """Ligne compacte montrant l'etat des 4 vannes (ON/OFF)."""
    parts = [f"{_SHORT[v]}:{'ON ' if v in open_valves else 'OFF'}" for v in _ALL_VALVES]
    return " ".join(parts)


def _lcd_valves(
    lcd: LCD2004,
    title: str,
    open_valves: tuple[str, ...],
    status: str,
    info: str = "",
) -> None:
    lcd.write_centered(1, title)
    # L2 : PAB:ON  EGO:OFF
    # L3 : CUV:OFF EAU:ON
    pab = f"PAB:{'ON ' if 'POT_A_BOUE'   in open_valves else 'OFF'}"
    ego = f"EGO:{'ON ' if 'EGOUTS'       in open_valves else 'OFF'}"
    cuv = f"CUV:{'ON ' if 'CUVE_TRAVAIL' in open_valves else 'OFF'}"
    eau = f"EAU:{'ON ' if 'EAU_PROPRE'   in open_valves else 'OFF'}"
    lcd.write(2, _pad(f"{pab}  {ego}"))
    lcd.write(3, _pad(f"{cuv}  {eau}"))
    lcd.write(4, _pad(info if info else status))


def _countdown(
    lcd: LCD2004,
    title: str,
    open_valves: tuple[str, ...],
    status: str,
    duration: float,
) -> None:
    """Affiche un compte a rebours bloquant sur LCD et terminal."""
    t0 = time.monotonic()
    while True:
        elapsed   = time.monotonic() - t0
        remaining = max(0.0, duration - elapsed)
        info      = f"{status}  {remaining:.1f}s"
        _lcd_valves(lcd, "TEST VANNES US", open_valves, status, info)
        print(f"  {info}     \r", end="", flush=True)
        if elapsed >= duration:
            break
        time.sleep(0.1)
    print()


def _sep(title: str) -> None:
    print(f"\n{'=' * 54}")
    print(f"  {title}")
    print(f"{'=' * 54}")


# ============================================================
# Phase 0 — Charge initiale condensateurs (identique a main.py)
# ============================================================

def phase0_init_charge(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 0 — CHARGE INITIALE CONDENSATEURS")
    dur = config.VALVE_STARTUP_CAPACITOR_CHARGE_S
    print(f"  Toutes les vannes alimentees pendant {dur:.0f}s.")
    print(f"  Charge complete des condensateurs internes.")
    print()

    lcd.clear()
    relays.open_all_valves()
    open_all = _ALL_VALVES
    _countdown(lcd, "INIT CONDENSATEURS", open_all,
               f"Charge {dur:.0f}s", dur)
    relays.close_all_valves()
    travel_s = config.VALVE_CLOSE_TRAVEL_S
    print(f"  Relays coupes — course mecanique {travel_s:.0f}s...")
    _countdown(lcd, "INIT CONDENSATEURS", (),
               f"Course fermt {travel_s:.0f}s", travel_s)

    _lcd_valves(lcd, "INIT CONDENSATEURS", (), "Toutes fermees", "Charge OK")
    print(f"  Condensateurs charges — toutes les vannes fermees.")


# ============================================================
# Phase 1 — Une par une
# ============================================================

def phase1_une_par_une(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 1 — ACTIVATION UNE PAR UNE")
    charge_s = config.VALVE_OPEN_CAPACITOR_CHARGE_S
    obs_s    = 5.0
    print(f"  Charge condensateur : {charge_s:.0f}s apres ouverture")
    print(f"  Observation         : {obs_s:.0f}s vanne ouverte")
    print(f"  Entree pour lancer chaque vanne.")

    for name in _ALL_VALVES:
        gpio = _GPIO[name]
        print(f"\n  --- {name} (GPIO {gpio}) ---")
        print(f"  >>> Entree pour ouvrir {name}...", end="", flush=True)
        input()

        # Ouverture
        relays.open_valve(name)
        open_now = (name,)
        print(f"  {name} OUVERTE")

        # Attente charge condensateur
        print(f"  Charge condensateur {charge_s:.0f}s...")
        _countdown(lcd, "Phase 1 — une/une", open_now,
                   f"Charge {name[:3]}", charge_s)

        # Observation
        print(f"  Observation {obs_s:.0f}s...")
        _countdown(lcd, "Phase 1 — une/une", open_now,
                   f"Obs.  {name[:3]}", obs_s)

        # Fermeture — attente course mecanique
        relays.close_valve(name)
        print(f"  {name} FERMEE — course {config.VALVE_CLOSE_TRAVEL_S:.0f}s...")
        _countdown(lcd, "Phase 1 — une/une", (),
                   f"Course {name[:3]}", config.VALVE_CLOSE_TRAVEL_S)
        print(f"  {name} en butee fermee")

    print("\n  Phase 1 terminee — toutes les vannes fermees.")


# ============================================================
# Phase 2 — Toutes ensemble
# ============================================================

def phase2_toutes(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 2 — TOUTES ENSEMBLE")
    charge_s = config.VALVE_OPEN_CAPACITOR_CHARGE_S
    obs_s    = 5.0
    print(f"  Les 4 vannes s'ouvrent simultanement.")
    print(f"  Charge condensateur : {charge_s:.0f}s  |  Observation : {obs_s:.0f}s")
    print()
    print("  >>> Entree pour ouvrir toutes les vannes...", end="", flush=True)
    input()

    # Ouverture de toutes
    relays.open_all_valves()
    open_all = _ALL_VALVES
    print("  Toutes les vannes OUVERTES")

    # Charge condensateurs
    print(f"  Charge condensateurs {charge_s:.0f}s...")
    _countdown(lcd, "Phase 2 — toutes", open_all, "Charge 4 vannes", charge_s)

    # Observation
    print(f"  Observation {obs_s:.0f}s...")
    _countdown(lcd, "Phase 2 — toutes", open_all, "Observation", obs_s)

    # Fermeture — attente course mecanique (toutes en parallele)
    relays.close_all_valves()
    print(f"  Relays coupes — course {config.VALVE_CLOSE_TRAVEL_S:.0f}s...")
    _countdown(lcd, "Phase 2 — toutes", (), "Course fermeture", config.VALVE_CLOSE_TRAVEL_S)
    _lcd_valves(lcd, "Phase 2 — toutes", (), "Toutes fermees")
    print("  Toutes les vannes en butee fermee")

    print("\n  Phase 2 terminee.")


# ============================================================
# Phase 3 — Simulation programmes
# ============================================================

def phase3_programmes(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 3 — SIMULATION PROGRAMMES  (5s actives par PRG)")
    charge_s = config.VALVE_OPEN_CAPACITOR_CHARGE_S
    active_s = 5.0
    print(f"  Sequence : ouverture → charge {charge_s:.0f}s → actif {active_s:.0f}s → fermeture")
    print()

    for prg_id in range(1, 6):
        open_valves = _PRG_VALVES[prg_id]
        prg_name    = _PRG_NAMES[prg_id]

        print(f"\n  --- PRG{prg_id} {prg_name} ---")
        if open_valves:
            print(f"  Vannes : {', '.join(open_valves)}")
        else:
            print(f"  Vannes : aucune (toutes fermees)")
        print(f"  >>> Entree pour lancer PRG{prg_id}...", end="", flush=True)
        input()

        # Ouverture des vannes du programme
        relays.close_all_valves()
        for name in open_valves:
            relays.open_valve(name)

        title = f"PRG{prg_id} {prg_name}"

        if open_valves:
            print(f"  Vannes ouvertes — charge condensateurs {charge_s:.0f}s...")
            _countdown(lcd, title, open_valves,
                       f"Charge PRG{prg_id}", charge_s)

            print(f"  Phase active {active_s:.0f}s...")
            _countdown(lcd, title, open_valves,
                       f"Actif PRG{prg_id}", active_s)
        else:
            # PRG3 : pas de vanne ouverte au start
            print(f"  Aucune vanne ouverte (PRG3 — EGOUTS cycle en tick)")
            _lcd_valves(lcd, title, (), f"PRG{prg_id} — 0 vanne")
            _countdown(lcd, title, (), f"PRG{prg_id} actif", active_s)

        # Fermeture — attente course mecanique (toutes en parallele)
        relays.close_all_valves()
        print(f"  PRG{prg_id} — relays coupes — course {config.VALVE_CLOSE_TRAVEL_S:.0f}s...")
        _countdown(lcd, title, (), f"Fermt PRG{prg_id}", config.VALVE_CLOSE_TRAVEL_S)
        _lcd_valves(lcd, title, (), f"PRG{prg_id} ferme")
        print(f"  PRG{prg_id} — toutes vannes en butee fermee")

    print("\n  Phase 3 terminee — toutes les vannes fermees.")


# ============================================================
# Phase 4 — Cycles ouverture / fermeture simultanes
# ============================================================

def phase4_cycles(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 4 — CYCLES OUVERTURE/FERMETURE SEQUENTIELS (10 cycles)")
    charge_s  = config.VALVE_OPEN_CAPACITOR_CHARGE_S
    travel_s  = config.VALVE_CLOSE_TRAVEL_S
    obs_s     = 3.0
    pause_s   = 2.0
    n_cycles  = 10
    n_valves  = len(_ALL_VALVES)

    total_s = n_cycles * (n_valves * charge_s + obs_s + n_valves * travel_s + pause_s)

    print(f"  {n_cycles} cycles — sequence par cycle :")
    print(f"    ouverture sequentielle {n_valves} vannes ({charge_s:.0f}s apres chaque)")
    print(f"    observation      : {obs_s:.0f}s")
    print(f"    fermeture sequentielle ({travel_s:.0f}s de course apres chaque relay OFF)")
    print(f"    pause            : {pause_s:.0f}s")
    print(f"  Duree totale estimee : ~{int(total_s // 60)}min{int(total_s % 60):02d}s")
    print()
    print("  >>> Entree pour lancer les cycles...", end="", flush=True)
    input()

    t_total = time.monotonic()

    for i in range(1, n_cycles + 1):
        print(f"\n  --- Cycle {i}/{n_cycles} ---")

        # Ouverture sequentielle — charge condensateur apres chaque vanne
        current_open: list[str] = []
        for valve in _ALL_VALVES:
            relays.open_valve(valve)
            current_open.append(valve)
            print(f"    {valve} OUVERTE — charge {charge_s:.0f}s...")
            _countdown(lcd, "Phase 4 cycles", tuple(current_open),
                       f"C{i}/{n_cycles} chrg {_SHORT[valve]}", charge_s)

        # Observation toutes vannes ouvertes
        _countdown(lcd, "Phase 4 cycles", _ALL_VALVES,
                   f"C{i}/{n_cycles} obs.", obs_s)

        # Fermeture sequentielle — attente course mecanique apres chaque relay OFF
        open_set: set[str] = set(_ALL_VALVES)
        for valve in _ALL_VALVES:
            relays.close_valve(valve)
            open_set.discard(valve)
            print(f"    {valve} FERMEE — course {travel_s:.0f}s...")
            _countdown(lcd, "TEST VANNES US", tuple(open_set),
                       f"C{i}/{n_cycles} fermt {_SHORT[valve]}", travel_s)

        if i < n_cycles:
            time.sleep(pause_s)

    elapsed = time.monotonic() - t_total
    m = int(elapsed) // 60
    s = int(elapsed) % 60
    print(f"\n  Phase 4 terminee — {n_cycles} cycles en {m:02d}:{s:02d}.")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST VANNES US SOLID — Clean & Protech V5")
    print("=" * 54)
    print(f"  PAB : POT_A_BOUE   GPIO {config.RELAY_POT_A_BOUE_GPIO}")
    print(f"  EGO : EGOUTS       GPIO {config.RELAY_EGOUTS_GPIO}")
    print(f"  CUV : CUVE_TRAVAIL GPIO {config.RELAY_CUVE_TRAVAIL_GPIO}")
    print(f"  EAU : EAU_PROPRE   GPIO {config.RELAY_EAU_PROPRE_GPIO}")
    print()
    print(f"  Charge init  : VALVE_STARTUP_CAPACITOR_CHARGE_S = "
          f"{config.VALVE_STARTUP_CAPACITOR_CHARGE_S:.0f}s")
    print(f"  Charge ouvert: VALVE_OPEN_CAPACITOR_CHARGE_S    = "
          f"{config.VALVE_OPEN_CAPACITOR_CHARGE_S:.0f}s")
    print("  Ctrl+C pour quitter proprement\n")

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()

        relays = Relays()
        relays.open()

        try:
            phase0_init_charge(lcd, relays)
            phase1_une_par_une(lcd, relays)
            phase2_toutes(lcd, relays)
            phase3_programmes(lcd, relays)
            phase4_cycles(lcd, relays)

        except KeyboardInterrupt:
            print("\n\n  Arret (Ctrl+C)")

        finally:
            relays.close_all_valves()
            relays.close()
            lcd.clear()
            lcd.write_centered(1, "TEST VANNES US")
            lcd.write_centered(2, "Termine")
            lcd.write_centered(3, "Toutes fermees")

    gpio_handle.close()
    print("=== FIN TEST VANNES US SOLID ===")


if __name__ == "__main__":
    main()
