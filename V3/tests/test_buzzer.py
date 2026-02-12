#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Test du buzzer.

- Lit la config pour connaître le GPIO du buzzer.
- Génère quelques bips simples.

Utilisation :
    python tests/test_buzzer.py
"""

import time
from pathlib import Path

import lgpio  # type: ignore
import yaml  # type: ignore


def main() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    buzzer_pin = int(cfg["gpio"]["buzzer"])

    # Ouvre le contrôleur GPIO (chip 0 par défaut sur Raspberry Pi)
    h = lgpio.gpiochip_open(0)
    # Configure la ligne en sortie, niveau bas initial
    lgpio.gpio_claim_output(h, buzzer_pin, 0)

    print("=== Test buzzer ===")
    print(f"GPIO buzzer : {buzzer_pin}")
    print("3 séries de bips. CTRL+C pour arrêter.")

    try:
        for serie in range(3):
            print(f"Série {serie + 1}/3")
            for _ in range(5):
                lgpio.gpio_write(h, buzzer_pin, 1)
                time.sleep(0.1)
                lgpio.gpio_write(h, buzzer_pin, 0)
                time.sleep(0.1)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur.")
    finally:
        # Stoppe le buzzer et ferme le contrôleur proprement
        lgpio.gpio_write(h, buzzer_pin, 0)
        lgpio.gpiochip_close(h)
        print("Test buzzer terminé.")


if __name__ == "__main__":
    main()

