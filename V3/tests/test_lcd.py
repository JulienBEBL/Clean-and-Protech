#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Test dédié de l'écran LCD 20x4.

Objectif :
- Vérifier que le LCD fonctionne.
- Afficher des infos "réalistes" basées sur la config (programmes, sécurité).

Utilisation :
    python tests/test_lcd.py
"""

import time
from pathlib import Path

import yaml  # type: ignore

from libs.i2c_devices import LCD20x4, SMBus


def main() -> None:
    # Charge la config sans passer par main.py
    config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    i2c_cfg = cfg["i2c"]
    bus_id = int(i2c_cfg.get("bus", 1))
    lcd_addr = int(i2c_cfg["lcd"])

    bus = SMBus(bus_id)
    lcd = LCD20x4(bus, lcd_addr, width=20)

    progs = cfg.get("programs", {})

    # Écran 1 : écran d’accueil
    lcd.clear()
    lcd.write_line(1, "Clean & Protech")
    lcd.write_line(2, "Test LCD")
    lcd.write_line(3, "Ctrl+C pour stop")
    lcd.write_line(4, "")
    time.sleep(2)

    # Écran 2 : liste des programmes
    lcd.clear()
    lcd.write_line(1, "Programmes actifs")
    names = [f"{num}" for num, p in progs.items() if p.get("enabled", True)]
    lcd.write_line(2, "P: " + " ".join(names)[:20])
    lcd.write_line(3, "Total: " + str(len(progs)))
    lcd.write_line(4, "")
    time.sleep(3)

    # Écran 3 : défilement des paramètres de sécurité par programme
    try:
        while True:
            for num in sorted(progs.keys()):
                p = progs[num]
                safety = p.get("safety", {})
                air_mode = str(safety.get("air", {}).get("mode", "manual"))
                vic_mode = str(safety.get("vic", {}).get("mode", "manual"))
                pump_mode = str(safety.get("pump", {}).get("mode", "auto"))

                lcd.clear()
                lcd.write_line(1, f"P{num}: {p.get('name','')[:13]}")
                lcd.write_line(2, f"AIR: {air_mode[:6]}")
                lcd.write_line(3, f"VIC: {vic_mode[:6]}")
                lcd.write_line(4, f"PMP: {pump_mode[:6]}")
                time.sleep(2)
    except KeyboardInterrupt:
        lcd.clear()
        lcd.write_line(1, "Test LCD stoppe")
        lcd.write_line(2, "")
        lcd.write_line(3, "")
        lcd.write_line(4, "")
        time.sleep(1)


if __name__ == "__main__":
    main()

