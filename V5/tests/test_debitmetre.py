"""
test_debitmetre.py — Test du debitmetre a impulsions — V5.

Trois phases progressives :

    Phase 1 — Lecture live
        Affiche le debit instantane (L/min), le volume cumule (L) et le
        nombre brut d'impulsions a 10 Hz.
        Permet de verifier que le capteur repond correctement au passage d'eau.
        Ctrl+C pour passer a la phase suivante.

    Phase 2 — Comparaison des fenetres glissantes
        Affiche en parallele flow_lpm(1s), flow_lpm(2s) et flow_lpm(5s).
        Aide a evaluer la stabilite selon la fenetre choisie.
        La securite debit utilise la fenetre 1s (config par defaut).
        Ctrl+C pour passer a la phase suivante.

    Phase 3 — Validation du K-factor
        Remet le compteur a zero puis mesure les impulsions sur un volume connu.
        A la fin (Ctrl+C), affiche les impulsions totales et le K-factor effectif
        si l'utilisateur saisit le volume reel passe.
        K-factor configure : DEBITMETRE_K_FACTOR = 10.84 imp/L

Materiel implique :
    GPIO 13 → debitmetre a impulsions (front descendant, filtre anti-rebond 400 µs)
    K-factor : 10.84 impulsions / litre (valeur terrain)

Ctrl+C interrompt proprement chaque phase.
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
from libs.debitmetre import FlowMeter

_COLS = config.LCD_COLS   # 20
_LOOP_S = 0.1             # 10 Hz


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _fmt_elapsed(elapsed_s: float) -> str:
    m = int(elapsed_s) // 60
    s = int(elapsed_s) % 60
    return f"{m:02d}:{s:02d}"


def _sep(title: str) -> None:
    print(f"\n{'=' * 54}")
    print(f"  {title}")
    print(f"{'=' * 54}")


def _lcd_live(
    lcd: LCD2004,
    phase: str,
    lpm: float,
    liters: float,
    pulses: int,
    elapsed_s: float,
) -> None:
    lcd.write_centered(1, "TEST DEBITMETRE")
    lcd.write(2, _pad(f"Debit : {lpm:6.1f} L/min"))
    lcd.write(3, _pad(f"Vol   : {liters:7.3f} L"))
    lcd.write(4, _pad(f"Impuls: {pulses:6d}  {_fmt_elapsed(elapsed_s)}"))


# ============================================================
# Phase 1 — Lecture live
# ============================================================

def phase1_live(lcd: LCD2004, flow: FlowMeter) -> None:
    _sep("PHASE 1 — LECTURE LIVE  (10 Hz)")
    print(f"  GPIO debitmetre : {config.DEBITMETRE_GPIO}")
    print(f"  K-factor        : {config.DEBITMETRE_K_FACTOR} imp/L")
    print(f"  Anti-rebond     : {config.DEBITMETRE_DEBOUNCE_US} µs")
    print()
    print("  Faire circuler de l'eau dans l'installation.")
    print("  Ctrl+C pour passer a la phase 2.")
    print()

    flow.reset_total()
    t0 = time.monotonic()

    try:
        while True:
            t_loop = time.monotonic()

            lpm     = flow.flow_lpm()
            liters  = flow.total_liters()
            pulses  = flow.total_pulses()
            elapsed = time.monotonic() - t0

            _lcd_live(lcd, "Phase 1", lpm, liters, pulses, elapsed)
            print(
                f"  Debit: {lpm:6.1f} L/min   "
                f"Vol: {liters:7.3f} L   "
                f"Impuls: {pulses:6d}   "
                f"Duree: {_fmt_elapsed(elapsed)}     \r",
                end="", flush=True,
            )

            remaining = _LOOP_S - (time.monotonic() - t_loop)
            if remaining > 0:
                time.sleep(remaining)

    except KeyboardInterrupt:
        elapsed = time.monotonic() - t0
        print(f"\n\n  Fin phase 1 — duree {_fmt_elapsed(elapsed)}")
        print(f"  Volume total : {flow.total_liters():.3f} L")
        print(f"  Impulsions   : {flow.total_pulses()}")


# ============================================================
# Phase 2 — Comparaison fenetres glissantes
# ============================================================

def phase2_windows(lcd: LCD2004, flow: FlowMeter) -> None:
    _sep("PHASE 2 — FENETRES GLISSANTES  (1s / 2s / 5s)")
    print("  Comparaison des debits selon la fenetre de calcul.")
    print("  La securite debit utilise la fenetre 1s.")
    print("  Ctrl+C pour passer a la phase 3.")
    print()

    flow.reset_total()
    t0 = time.monotonic()
    first = True

    try:
        while True:
            t_loop = time.monotonic()

            lpm_1s = flow.flow_lpm(window_s=1.0)
            lpm_2s = flow.flow_lpm(window_s=2.0)
            lpm_5s = flow.flow_lpm(window_s=5.0)
            elapsed = time.monotonic() - t0

            # LCD : 3 fenetres + volume
            lcd.write_centered(1, "TEST DEBITMETRE")
            lcd.write(2, _pad(f"1s : {lpm_1s:6.1f} L/min"))
            lcd.write(3, _pad(f"2s : {lpm_2s:6.1f} L/min"))
            lcd.write(4, _pad(f"5s : {lpm_5s:6.1f} L/min"))

            # Terminal
            if not first:
                print("\033[4A", end="", flush=True)
            first = False

            print(f"  Fenetre 1s : {lpm_1s:6.1f} L/min  (securite debit)")
            print(f"  Fenetre 2s : {lpm_2s:6.1f} L/min")
            print(f"  Fenetre 5s : {lpm_5s:6.1f} L/min  (plus stable)")
            print(f"  Duree : {_fmt_elapsed(elapsed)}   Vol : {flow.total_liters():.3f} L     ", flush=True)

            remaining = _LOOP_S - (time.monotonic() - t_loop)
            if remaining > 0:
                time.sleep(remaining)

    except KeyboardInterrupt:
        print(f"\n\n  Fin phase 2.")


# ============================================================
# Phase 3 — Validation K-factor
# ============================================================

def phase3_kfactor(lcd: LCD2004, flow: FlowMeter) -> None:
    _sep("PHASE 3 — VALIDATION K-FACTOR")
    print(f"  K-factor configure : {config.DEBITMETRE_K_FACTOR} imp/L")
    print()
    print("  Preparer un recipient dose (ex: 1 litre precis).")
    print("  Le compteur sera remis a zero au lancement.")
    print("  Faire passer le volume connu, puis Ctrl+C pour le bilan.")
    print()
    print("  >>> Entree pour lancer (reset compteur)...", end="", flush=True)
    input()

    flow.reset_total()
    t0 = time.monotonic()

    lcd.clear()
    lcd.write_centered(1, "TEST DEBITMETRE")
    lcd.write_centered(2, "K-FACTOR")
    lcd.write_centered(3, "Faire circuler")
    lcd.write_centered(4, "puis Ctrl+C")

    first = True
    try:
        while True:
            t_loop = time.monotonic()

            lpm     = flow.flow_lpm()
            liters  = flow.total_liters()
            pulses  = flow.total_pulses()
            elapsed = time.monotonic() - t0

            # Calcul K effectif (evite division par zero)
            k_eff = pulses / liters if liters > 0.001 else 0.0

            # LCD
            lcd.write_centered(1, "TEST DEBITMETRE")
            lcd.write(2, _pad(f"Impuls : {pulses:7d}"))
            lcd.write(3, _pad(f"Vol    : {liters:7.3f} L"))
            lcd.write(4, _pad(f"K eff  : {k_eff:7.2f} imp/L"))

            # Terminal
            if not first:
                print("\033[4A", end="", flush=True)
            first = False

            print(f"  Impulsions : {pulses:7d}")
            print(f"  Volume     : {liters:7.3f} L")
            print(f"  Debit      : {lpm:6.1f} L/min")
            print(f"  K effectif : {k_eff:7.2f} imp/L   "
                  f"(configure: {config.DEBITMETRE_K_FACTOR})     ", flush=True)

            remaining = _LOOP_S - (time.monotonic() - t_loop)
            if remaining > 0:
                time.sleep(remaining)

    except KeyboardInterrupt:
        pass

    # Bilan
    pulses  = flow.total_pulses()
    liters  = flow.total_liters()
    elapsed = time.monotonic() - t0

    print(f"\n\n{'─' * 54}")
    print(f"  BILAN PHASE 3")
    print(f"{'─' * 54}")
    print(f"  Impulsions totales : {pulses}")
    print(f"  Volume calcule     : {liters:.4f} L  (K={config.DEBITMETRE_K_FACTOR})")
    print(f"  Duree              : {_fmt_elapsed(elapsed)}")
    print()

    # Saisie du volume reel pour calculer le K effectif
    print("  Entrer le volume reel passe (en litres, ex: 1.000)")
    print("  Laisser vide pour ignorer : ", end="", flush=True)
    try:
        raw = input().strip().replace(",", ".")
        if raw:
            vol_reel = float(raw)
            if vol_reel > 0 and pulses > 0:
                k_effectif = pulses / vol_reel
                ecart_pct  = (k_effectif - config.DEBITMETRE_K_FACTOR) / config.DEBITMETRE_K_FACTOR * 100.0
                print()
                print(f"  Volume reel    : {vol_reel:.4f} L")
                print(f"  K effectif     : {k_effectif:.4f} imp/L")
                print(f"  K configure    : {config.DEBITMETRE_K_FACTOR:.4f} imp/L")
                print(f"  Ecart          : {ecart_pct:+.2f} %")
                if abs(ecart_pct) > 5.0:
                    print(f"  => Ecart > 5% : mettre a jour DEBITMETRE_K_FACTOR dans config.py")
                else:
                    print(f"  => K-factor OK (ecart < 5%)")

                lcd.clear()
                lcd.write_centered(1, "K-FACTOR")
                lcd.write(2, _pad(f"Eff : {k_effectif:.2f} imp/L"))
                lcd.write(3, _pad(f"Cfg : {config.DEBITMETRE_K_FACTOR:.2f} imp/L"))
                lcd.write(4, _pad(f"Ecart: {ecart_pct:+.1f} %"))
    except (ValueError, EOFError):
        pass


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST DEBITMETRE — Clean & Protech V5")
    print("=" * 54)
    print(f"  GPIO          : {config.DEBITMETRE_GPIO}")
    print(f"  K-factor      : {config.DEBITMETRE_K_FACTOR} imp/L")
    print(f"  Anti-rebond   : {config.DEBITMETRE_DEBOUNCE_US} µs")
    print(f"  Seuil securite: {config.FLOW_SAFETY_MIN_LPM} L/min (PRG2/4/5)")
    print("  Ctrl+C pour quitter proprement\n")

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()

        flow = FlowMeter()
        flow.open()

        try:
            phase1_live(lcd, flow)
            phase2_windows(lcd, flow)
            phase3_kfactor(lcd, flow)

        except KeyboardInterrupt:
            print("\n\n  Arret global (Ctrl+C)")

        finally:
            flow.close()
            lcd.clear()
            lcd.write_centered(1, "TEST DEBITMETRE")
            lcd.write_centered(2, "Termine")

    gpio_handle.close()
    print("=== FIN TEST DEBITMETRE ===")


if __name__ == "__main__":
    main()
