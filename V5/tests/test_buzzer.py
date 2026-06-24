"""
test_buzzer.py — Test du buzzer passif piezo — V5.

5 phases progressives :

    Phase 1 — Bip simple (parametres defaut config.py)
        Joue un bip avec les valeurs de config.py.
        Rejoue 3 fois pour evaluation du rendu.

    Phase 2 — Variations repeat
        Series de 1, 2, 3 et 5 bips successifs.
        Confirme le comportement multi-bip et le gap entre bips.

    Phase 3 — Balayage frequence (500 Hz -> 4500 Hz)
        12 paliers progressifs montee puis descente.
        Permet d'evaluer la reponse en frequence du buzzer.

    Phase 4 — Variation puissance (duty cycle)
        Bips a 10, 25, 50, 75, 100 %.
        Permet d'evaluer la plage sonore utilisable.

    Phase 5 — Sonnerie de demarrage
        Joue ringtone_startup() — identique au demarrage machine.
        Repete 3 fois pour evaluation du rendu.

Materiel implique :
    GPIO 21 -> 2x SEA-1295Y piezo passifs en parallele (5V, 42 Ohm, 2 kHz)

Ctrl+C quitte proprement.
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
from libs.buzzer import Buzzer

_COLS = config.LCD_COLS  # 20


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _sep(title: str) -> None:
    print(f"\n{'=' * 54}")
    print(f"  {title}")
    print(f"{'=' * 54}")


def _wait_enter(msg: str = "") -> None:
    prompt = f"  >>> {msg}Entree pour continuer..." if msg else "  >>> Entree pour continuer..."
    print(prompt, end="", flush=True)
    input()


# ============================================================
# Phase 1 — Bip simple
# ============================================================

def phase1_bip_simple(lcd: LCD2004, bz: Buzzer) -> None:
    _sep("PHASE 1 — BIP SIMPLE (defaut config)")
    print(f"  freq    : {config.BUZZER_DEFAULT_FREQ_HZ} Hz")
    print(f"  duree   : {config.BUZZER_BEEP_TIME_MS} ms")
    print(f"  puiss.  : {config.BUZZER_BEEP_POWER_PCT} %")
    print(f"  repeat  : {config.BUZZER_BEEP_REPEAT}")
    print(f"  gap     : {config.BUZZER_BEEP_GAP_MS} ms")
    print()

    lcd.clear()
    lcd.write_centered(1, "TEST BUZZER")
    lcd.write_centered(2, "Phase 1 - bip simple")
    lcd.write(3, _pad(f"Freq : {config.BUZZER_DEFAULT_FREQ_HZ} Hz"))
    lcd.write(4, _pad(f"Pwr:{config.BUZZER_BEEP_POWER_PCT}%  {config.BUZZER_BEEP_TIME_MS}ms"))

    _wait_enter("Jouer bip simple... ")
    bz.beep()
    print("  BIP (defaut) — OK")
    time.sleep(1.0)

    _wait_enter("Rejouer 3 fois... ")
    for i in range(1, 4):
        lcd.write(4, _pad(f"Bip {i}/3"))
        print(f"  Bip {i}/3...")
        bz.beep()
        time.sleep(0.5)

    print("\n  Phase 1 terminee.")


# ============================================================
# Phase 2 — Variations repeat
# ============================================================

def phase2_repeat(lcd: LCD2004, bz: Buzzer) -> None:
    _sep("PHASE 2 — VARIATIONS REPEAT")
    repeats = (1, 2, 3, 5)
    print(f"  Series testees   : {repeats}")
    print(f"  freq : {config.BUZZER_DEFAULT_FREQ_HZ} Hz  "
          f"| duree : {config.BUZZER_BEEP_TIME_MS} ms  "
          f"| gap : {config.BUZZER_BEEP_GAP_MS} ms")
    print()

    for n in repeats:
        lcd.clear()
        lcd.write_centered(1, "TEST BUZZER")
        lcd.write_centered(2, "Phase 2 - repeat")
        lcd.write(3, _pad(f"Repeat : {n}"))
        lcd.write(4, _pad(f"Gap    : {config.BUZZER_BEEP_GAP_MS} ms"))

        _wait_enter(f"Jouer {n} bip(s)... ")
        print(f"  {n} bip(s)...")
        bz.beep(repeat=n)
        time.sleep(1.0)

    print("\n  Phase 2 terminee.")


# ============================================================
# Phase 3 — Balayage frequence
# ============================================================

def phase3_frequence(lcd: LCD2004, bz: Buzzer) -> None:
    _sep("PHASE 3 — BALAYAGE FREQUENCE (500 -> 4500 Hz)")
    step = (config.BUZZER_FREQ_MAX_HZ - config.BUZZER_FREQ_MIN_HZ) // 11
    freqs = list(range(config.BUZZER_FREQ_MIN_HZ, config.BUZZER_FREQ_MAX_HZ + 1, step))[:12]

    print(f"  Plage   : {config.BUZZER_FREQ_MIN_HZ} - {config.BUZZER_FREQ_MAX_HZ} Hz")
    print(f"  Paliers : {freqs}")
    print()

    lcd.clear()
    lcd.write_centered(1, "TEST BUZZER")
    lcd.write_centered(2, "Phase 3 - freq sweep")
    lcd.write(3, _pad(f"{config.BUZZER_FREQ_MIN_HZ}Hz -> {config.BUZZER_FREQ_MAX_HZ}Hz"))
    lcd.write(4, _pad(f"{len(freqs)} paliers"))

    _wait_enter("Lancer balayage... ")

    # Montee
    print("  Montee...")
    for freq in freqs:
        lcd.write(3, _pad(f"Freq : {freq} Hz"))
        lcd.write(4, _pad("Montee..."))
        print(f"  {freq:4d} Hz  (montee)\r", end="", flush=True)
        bz.beep(freq_hz=freq, time_ms=300, power_pct=config.BUZZER_BEEP_POWER_PCT)
        time.sleep(0.2)
    print()

    time.sleep(0.5)

    # Descente
    print("  Descente...")
    for freq in reversed(freqs):
        lcd.write(3, _pad(f"Freq : {freq} Hz"))
        lcd.write(4, _pad("Descente..."))
        print(f"  {freq:4d} Hz  (descente)\r", end="", flush=True)
        bz.beep(freq_hz=freq, time_ms=200, power_pct=config.BUZZER_BEEP_POWER_PCT)
        time.sleep(0.15)
    print()

    print("\n  Phase 3 terminee.")


# ============================================================
# Phase 4 — Variation puissance
# ============================================================

def phase4_puissance(lcd: LCD2004, bz: Buzzer) -> None:
    _sep("PHASE 4 — VARIATION PUISSANCE (duty cycle)")
    powers = (10, 25, 50, 75, 100)
    print(f"  Puissances testees : {powers} %")
    print(f"  freq : {config.BUZZER_DEFAULT_FREQ_HZ} Hz  |  duree : 400 ms")
    print()

    for pwr in powers:
        lcd.clear()
        lcd.write_centered(1, "TEST BUZZER")
        lcd.write_centered(2, "Phase 4 - puissance")
        lcd.write(3, _pad(f"Power : {pwr} %"))
        lcd.write(4, _pad(f"Freq  : {config.BUZZER_DEFAULT_FREQ_HZ} Hz"))

        _wait_enter(f"Jouer a {pwr}%... ")
        print(f"  Power {pwr:3d}% ...")
        bz.beep(power_pct=pwr, time_ms=400)
        time.sleep(0.8)

    print("\n  Phase 4 terminee.")


# ============================================================
# Phase 5 — Sonnerie de demarrage
# ============================================================

def phase5_ringtone(lcd: LCD2004, bz: Buzzer) -> None:
    _sep("PHASE 5 — SONNERIE DE DEMARRAGE")
    print("  Joue ringtone_startup() — identique au demarrage machine.")
    print("  Repete 3 fois.")
    print()

    for i in range(1, 4):
        lcd.clear()
        lcd.write_centered(1, "TEST BUZZER")
        lcd.write_centered(2, "Phase 5 - ringtone")
        lcd.write(3, _pad(f"Demarrage {i}/3"))
        lcd.write(4, _pad("En cours..."))

        _wait_enter(f"Jouer sonnerie {i}/3... ")
        print(f"  Sonnerie {i}/3 ...")
        bz.ringtone_startup()
        print(f"  Sonnerie {i}/3 terminee.")

        lcd.write(4, _pad("Terminee"))
        time.sleep(1.5)

    print("\n  Phase 5 terminee.")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST BUZZER — Clean & Protech V5")
    print("=" * 54)
    print(f"  GPIO         : {config.BUZZER_GPIO}")
    print(f"  Freq defaut  : {config.BUZZER_DEFAULT_FREQ_HZ} Hz")
    print(f"  Freq min/max : {config.BUZZER_FREQ_MIN_HZ} / {config.BUZZER_FREQ_MAX_HZ} Hz")
    print(f"  Beep time    : {config.BUZZER_BEEP_TIME_MS} ms")
    print(f"  Beep power   : {config.BUZZER_BEEP_POWER_PCT} %")
    print(f"  Beep gap     : {config.BUZZER_BEEP_GAP_MS} ms")
    print("  Ctrl+C pour quitter proprement\n")

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST BUZZER")
        lcd.write_centered(2, "Init...")

        bz = Buzzer()
        bz.open()

        try:
            phase1_bip_simple(lcd, bz)
            phase2_repeat(lcd, bz)
            phase3_frequence(lcd, bz)
            phase4_puissance(lcd, bz)
            phase5_ringtone(lcd, bz)

        except KeyboardInterrupt:
            print("\n\n  Arret (Ctrl+C)")

        finally:
            bz.close()
            lcd.clear()
            lcd.write_centered(1, "TEST BUZZER")
            lcd.write_centered(2, "Termine")

    gpio_handle.close()
    print("=== FIN TEST BUZZER ===")


if __name__ == "__main__":
    main()
