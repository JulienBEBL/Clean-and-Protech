#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Test lecture des entrées sur MCP23017.

- MCP1 : boutons programmes.
- MCP2 : sélecteurs VIC / AIR.

Affiche en boucle les états, jusqu'à CTRL+C.

Utilisation :
    python tests/test_mcp_inputs.py
"""

import time
from pathlib import Path

import yaml  # type: ignore

from libs.i2c_devices import MCP23017, LCD20x4, SMBus


def main() -> None:
    # Charge la config sans dépendre de main.py
    config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    i2c_cfg = cfg["i2c"]
    bus_id = int(i2c_cfg.get("bus", 1))
    bus = SMBus(bus_id)

    # Instancie MCP1, MCP2 et LCD
    mcp1 = MCP23017(bus, int(i2c_cfg["mcp1"]), name="MCP1_programs")
    mcp2 = MCP23017(bus, int(i2c_cfg["mcp2"]), name="MCP2_selectors")
    lcd = LCD20x4(bus, int(i2c_cfg["lcd"]), width=20)

    mcp_cfg = cfg["mcp23017"]
    m1_cfg = mcp_cfg["mcp1_programs"]
    m2_cfg = mcp_cfg["mcp2_selectors"]

    btn_bank = m1_cfg["buttons_bank"]
    btn_bits = m1_cfg["buttons_bits"]

    vic_bank = m2_cfg["vic_bank"]
    vic_bits = m2_cfg["vic_bits"]
    air_bank = m2_cfg["air_bank"]
    air_bit = m2_cfg["air_bit"]

    lcd.clear()
    lcd.write_line(1, "Test MCP INPUTS")
    lcd.write_line(2, "Voir console Pi")

    print("=== Test entrées MCP ===")
    print("CTRL+C pour quitter.")

    try:
        while True:
            # Boutons programmes (actif bas)
            val_btn = mcp1.read_bank(btn_bank)
            states_btn = []
            for idx, bit in enumerate(btn_bits, start=1):
                pressed = (val_btn & (1 << bit)) == 0
                states_btn.append(f"P{idx}={'1' if pressed else '0'}")

            # Sélecteur VIC (vecteur de bits)
            val_vic = mcp2.read_bank(vic_bank)
            vic_state_bits = []
            for i, bit in enumerate(vic_bits):
                active = (val_vic & (1 << bit)) == 0  # si câblé en actif bas
                vic_state_bits.append('1' if active else '0')

            # AIR
            val_air = mcp2.read_bank(air_bank)
            air_on = (val_air & (1 << air_bit)) == 0  # actif bas supposé

            print(
                "BTN:",
                " ".join(states_btn),
                "| VIC bits:",
                "".join(vic_state_bits),
                "| AIR:",
                "1" if air_on else "0",
                end="\r",
                flush=True,
            )

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nArrêt du test MCP inputs.")
        lcd.clear()
        lcd.write_line(1, "Test MCP inputs")
        lcd.write_line(2, "STOP")
        time.sleep(1)


if __name__ == "__main__":
    main()

