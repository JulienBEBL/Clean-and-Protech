"""
test_relays.py — Test interactif des relais V5.

Teste séquentiellement :
    1. Relais POMPE : ON 2s → OFF
    2. Relais AIR   : ON 2s → OFF (timer)
    3. Vannes US Solid : POT_A_BOUE, EGOUTS, CUVE_TRAVAIL, EAU_PROPRE
                         chacune ON 2s → OFF, avec confirmation visuelle

Modifier la constante PAUSE_S pour ajuster la durée ON de chaque relais.
Presser Entrée entre chaque test pour continuer.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import libs.gpio_handle as gpio_handle
from libs.relays import Relays

# ── Paramètre modifiable ──────────────────────────────────────────────────────
PAUSE_S: float = 2.0   # durée ON de chaque relais (s)
# ─────────────────────────────────────────────────────────────────────────────


def _pause(msg: str) -> None:
    try:
        input(f"  {msg} [Entrée] : ")
    except EOFError:
        pass


def main() -> None:
    print("=" * 54)
    print("  TEST RELAIS V5")
    print("=" * 54)
    print(f"  Durée ON : {PAUSE_S}s par relais")
    print("  Ctrl+C pour arrêter\n")

    gpio_handle.init()
    relays = Relays()
    relays.open()

    try:
        # ── POMPE ─────────────────────────────────────────────────────────
        print("\n[1] POMPE — GPIO 19")
        _pause("Appuyer pour activer POMPE ON (GPIO HIGH → relais ON → pompe tourne)")
        relays.set_pompe_on()
        print(f"    POMPE ON ({PAUSE_S}s)...")
        time.sleep(PAUSE_S)
        relays.set_pompe_off()
        print("    POMPE OFF — OK")

        # ── AIR ───────────────────────────────────────────────────────────
        print("\n[2] AIR — GPIO 26")
        _pause("Appuyer pour activer AIR ON (EV ouverte)")
        relays.set_air_on(time_s=PAUSE_S)
        print(f"    AIR ON {PAUSE_S}s (timer)...")
        while relays.air_is_on:
            relays.tick()
            time.sleep(0.1)
        print("    AIR OFF auto — OK")

        # ── Vannes US Solid ───────────────────────────────────────────────
        valves = ["POT_A_BOUE", "EGOUTS", "CUVE_TRAVAIL", "EAU_PROPRE"]
        for i, name in enumerate(valves, start=3):
            print(f"\n[{i}] Vanne {name}")
            _pause(f"Appuyer pour ouvrir {name}")
            relays.open_valve(name)
            print(f"    {name} OUVERTE ({PAUSE_S}s)...")
            time.sleep(PAUSE_S)
            relays.close_valve(name)
            print(f"    {name} FERMÉE — OK")

        print("\n" + "=" * 54)
        print("  TEST TERMINÉ — tous relais OK")
        print("=" * 54)

    except KeyboardInterrupt:
        print("\n  Arrêté par l'utilisateur.")
    finally:
        # État sûr
        relays.set_pompe_off()
        relays.set_air_off()
        relays.close_all_valves()
        relays.close()

    gpio_handle.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Arrêté par l'utilisateur.")
        gpio_handle.close()
