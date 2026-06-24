"""
test_lcd.py — Test complet de l'afficheur LCD 20x4 V5.

Partie 1 — Geometrie (interaction manuelle) :
    Verifie que les 4 lignes et les 20 colonnes s'affichent correctement.
    Appuyer sur Entree pour passer a l'etape suivante.

Partie 2 — Ecrans machine (avance automatique) :
    Reproduit la sequence d'ecrans reels : splash, homing, IDLE,
    STARTING / RUNNING / STOPPING de chaque programme.
    Avance automatiquement toutes les 3 secondes.

Ctrl+C pour quitter a tout moment.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from libs.i2c_bus import I2CBus
from libs.lcd2004 import LCD2004

_COLS: int = config.LCD_COLS   # 20
_ROWS: int = config.LCD_ROWS   # 4


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    """Tronque ou complete a 20 caracteres (identique a programs.py / display.py)."""
    return s[:_COLS].ljust(_COLS)


def _step(lcd: LCD2004, title: str, hint: str = "") -> None:
    """
    Affiche le titre de l'etape dans le terminal et attend que l'utilisateur
    appuie sur Entree avant de continuer (laisse le temps d'observer le LCD).
    """
    print(f"\n{'─' * 54}")
    print(f"  {title}")
    if hint:
        for line in hint.splitlines():
            print(f"  {line}")
    print("  >>> Appuyer sur Entree pour continuer...", end="", flush=True)
    input()


def _auto(title: str, delay: float = 3.0) -> None:
    """Affiche le titre de l'etape et avance automatiquement apres delay secondes."""
    print(f"\n{'─' * 54}")
    print(f"  {title}")
    t0 = time.monotonic()
    while time.monotonic() - t0 < delay:
        remaining = delay - (time.monotonic() - t0)
        print(f"  Suite dans {remaining:.1f}s...      \r", end="", flush=True)
        time.sleep(0.1)
    print()


# ============================================================
# Partie 1 — Geometrie
# ============================================================

def part1_geometry(lcd: LCD2004) -> None:

    # ── 1.1 — Ecran vide ──────────────────────────────────────────────────────
    _step(lcd, "1.1 — Ecran vide (lcd.clear())",
          "L'ecran doit etre entierement vide — aucun caractere visible.")
    lcd.clear()

    # ── 1.2 — Lignes une par une ──────────────────────────────────────────────
    for row in range(1, 5):
        _step(lcd, f"1.2 — Ligne {row} seule",
              f"Seule la LIGNE {row} doit afficher du texte.\n"
              f"Les {_ROWS - 1} autres doivent rester vides.")
        lcd.clear()
        lcd.write_centered(row, f"=== LIGNE {row} ===")

    # ── 1.3 — Toutes les lignes simultanement ─────────────────────────────────
    _step(lcd, "1.3 — Les 4 lignes en meme temps",
          "Chaque ligne doit afficher son numero (1 a 4).")
    lcd.clear()
    for row in range(1, 5):
        lcd.write_centered(row, f"---  LIGNE {row}  ---")

    # ── 1.4 — Regle 20 colonnes ───────────────────────────────────────────────
    _step(lcd, "1.4 — Regle 20 colonnes",
          "L1 : '|' marque les colonnes 1 et 20 (debut et fin).\n"
          "L2 : chiffres 1..9 0 1..9 0  (20 chars exactement).\n"
          "L3 : lettres A..T              (20 chars exactement).\n"
          "L4 : vide.")
    lcd.clear()
    lcd.write(1, "|                  |")
    lcd.write(2, "12345678901234567890")
    lcd.write(3, "ABCDEFGHIJKLMNOPQRST")
    lcd.write(4, "")

    # ── 1.5 — Troncature (overflow) ───────────────────────────────────────────
    _step(lcd, "1.5 — Troncature a 20 chars (overflow)",
          "Chaque ligne contient 25 caracteres.\n"
          "Seuls les 20 premiers doivent apparaitre — pas de debordement.")
    lcd.clear()
    for row in range(1, 5):
        lcd.write(row, f"LIGNE{row}__ABCDEFGHIJKLMNOP")  # 25 chars

    # ── 1.6 — Ligne pleine ────────────────────────────────────────────────────
    _step(lcd, "1.6 — Ligne pleine (20 x '#')",
          "Les 4 lignes doivent etre entierement remplies de '#'.\n"
          "Aucun espace visible en debut ou fin de ligne.")
    lcd.clear()
    for row in range(1, 5):
        lcd.write(row, "#" * _COLS)

    # ── 1.7 — Centrage write_centered() ──────────────────────────────────────
    _step(lcd, "1.7 — Centrage write_centered()",
          "Chaque texte doit etre centre sur sa ligne :\n"
          "  L1 : 'CLEAN & PROTECH'  (15 chars)\n"
          "  L2 : 'SERENA 230V'      (11 chars)\n"
          "  L3 : 'OK'               ( 2 chars — tres centre)\n"
          "  L4 : '12345678901234567890' (20 chars — deja plein)")
    lcd.clear()
    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "SERENA 230V")
    lcd.write_centered(3, "OK")
    lcd.write_centered(4, "12345678901234567890")

    # ── 1.8 — write() ras-gauche vs write_centered() ─────────────────────────
    _step(lcd, "1.8 — write() vs write_centered()",
          "L1 et L3 : ras-gauche (write()).\n"
          "L2 et L4 : centre    (write_centered()).")
    lcd.clear()
    lcd.write(1,          "RAS-GAUCHE")
    lcd.write_centered(2, "CENTRE")
    lcd.write(3,          "RAS-GAUCHE")
    lcd.write_centered(4, "CENTRE")


# ============================================================
# Partie 2 — Ecrans machine reels
# ============================================================

def part2_screens(lcd: LCD2004) -> None:

    print("\n" + "=" * 54)
    print("  PARTIE 2 — ECRANS MACHINE (avance automatique 3s)")
    print("=" * 54)

    # ── Splash ────────────────────────────────────────────────────────────────
    _auto("2.1 — Splash (demarrage machine)")
    lcd.clear()
    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "")
    lcd.write_centered(3, "SERENA 230V")
    lcd.write_centered(4, "")

    # ── Homing ────────────────────────────────────────────────────────────────
    _auto("2.2 — Homing VIC en cours")
    lcd.clear()
    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "SERENA")
    lcd.write_centered(3, "Preparation ...")
    lcd.write_centered(4, "")

    # ── IDLE ──────────────────────────────────────────────────────────────────
    _auto("2.3 — IDLE (VIC pos 2 = NEUTRE / AIR = MOY)")
    lcd.clear()
    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "Choisir programme")
    lcd.write_centered(3, "PRG1  a  PRG5")
    lcd.write(4, _pad(" VIC:2     AIR:MOY"))

    # ── PRG1 ──────────────────────────────────────────────────────────────────
    _auto("2.4 — STARTING PRG1")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 1")
    lcd.write_centered(2, "PREM.VIDANGE")
    lcd.write_centered(3, "Demarrage...")
    lcd.write_centered(4, "")

    _auto("2.5 — RUNNING PRG1 (AIR ON / 01:30)")
    lcd.clear()
    lcd.write(1, _pad("PRG1 PREM.VIDANGE"))
    lcd.write(2, _pad("VIC:A/DEP  AIR: ON "))
    lcd.write(3, _pad(""))
    lcd.write(4, _pad("Duree   00:01:30"))

    _auto("2.6 — RUNNING PRG1 (AIR OFF / 03:12)")
    lcd.clear()
    lcd.write(1, _pad("PRG1 PREM.VIDANGE"))
    lcd.write(2, _pad("VIC:A/DEP  AIR:OFF "))
    lcd.write(3, _pad(""))
    lcd.write(4, _pad("Duree   00:03:12"))

    _auto("2.7 — STOPPING PRG1")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 1")
    lcd.write_centered(2, "PREM.VIDANGE")
    lcd.write_centered(3, "Arret...")
    lcd.write_centered(4, "")

    # ── PRG2 ──────────────────────────────────────────────────────────────────
    _auto("2.8 — STARTING PRG2")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 2")
    lcd.write_centered(2, "VIDANGE CUVE")
    lcd.write_centered(3, "Demarrage...")
    lcd.write_centered(4, "")

    _auto("2.9 — RUNNING PRG2 (45.3 L/min / 02:15)")
    lcd.clear()
    lcd.write(1, _pad("PRG2 VIDANGE CUVE"))
    lcd.write(2, _pad("VIC:A/NEU  POMPE: ON"))
    lcd.write(3, _pad("Debit:  45.3 L/min"))
    lcd.write(4, _pad("Duree   00:02:15"))

    _auto("2.10 — STOPPING PRG2")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 2")
    lcd.write_centered(2, "VIDANGE CUVE")
    lcd.write_centered(3, "Arret...")
    lcd.write_centered(4, "")

    # ── PRG3 ──────────────────────────────────────────────────────────────────
    _auto("2.11 — STARTING PRG3")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 3")
    lcd.write_centered(2, "SECHAGE")
    lcd.write_centered(3, "Demarrage...")
    lcd.write_centered(4, "")

    _auto("2.12 — RUNNING PRG3 (AIR ON / EGOUTS FERME)")
    lcd.clear()
    lcd.write(1, _pad("PRG3 SECHAGE"))
    lcd.write(2, _pad("VIC:A/DEP  AIR: ON "))
    lcd.write(3, _pad("EGOUTS:   FERME "))
    lcd.write(4, _pad("Duree   00:05:00"))

    _auto("2.13 — RUNNING PRG3 (AIR OFF / EGOUTS OUVERT)")
    lcd.clear()
    lcd.write(1, _pad("PRG3 SECHAGE"))
    lcd.write(2, _pad("VIC:A/DEP  AIR:OFF "))
    lcd.write(3, _pad("EGOUTS:   OUVERT"))
    lcd.write(4, _pad("Duree   00:05:02"))

    _auto("2.14 — STOPPING PRG3")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 3")
    lcd.write_centered(2, "SECHAGE")
    lcd.write_centered(3, "Arret...")
    lcd.write_centered(4, "")

    # ── PRG4 ──────────────────────────────────────────────────────────────────
    _auto("2.15 — STARTING PRG4")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 4")
    lcd.write_centered(2, "REMPLISSAGE")
    lcd.write_centered(3, "Demarrage...")
    lcd.write_centered(4, "")

    _auto("2.16 — RUNNING PRG4 (52.7 L/min / 03:45)")
    lcd.clear()
    lcd.write(1, _pad("PRG4 REMPLISSAGE"))
    lcd.write(2, _pad("VIC:A/NEU  POMPE: ON"))
    lcd.write(3, _pad("Debit:  52.7 L/min"))
    lcd.write(4, _pad("Duree   00:03:45"))

    _auto("2.17 — STOPPING PRG4")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 4")
    lcd.write_centered(2, "REMPLISSAGE")
    lcd.write_centered(3, "Arret...")
    lcd.write_centered(4, "")

    # ── PRG5 ──────────────────────────────────────────────────────────────────
    _auto("2.18 — STARTING PRG5")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 5")
    lcd.write_centered(2, "DESEMBOUAGE")
    lcd.write_centered(3, "Demarrage...")
    lcd.write_centered(4, "")

    _auto("2.19 — RUNNING PRG5 (VIC:NEU / AIR:MOY / 10:42)")
    lcd.clear()
    lcd.write(1, _pad("PRG5 DESEMBOUAGE"))
    lcd.write(2, _pad("VIC:M/NEU  AIR:MOY "))
    lcd.write(3, _pad("Debit:  48.2 L/min"))
    lcd.write(4, _pad("Duree   00:10:42"))

    _auto("2.20 — RUNNING PRG5 (VIC:DEP / AIR:FAI / 11:05)")
    lcd.clear()
    lcd.write(1, _pad("PRG5 DESEMBOUAGE"))
    lcd.write(2, _pad("VIC:M/DEP  AIR:FAI "))
    lcd.write(3, _pad("Debit:  39.6 L/min"))
    lcd.write(4, _pad("Duree   00:11:05"))

    _auto("2.21 — RUNNING PRG5 (VIC:RET / AIR:CON / 15:20)")
    lcd.clear()
    lcd.write(1, _pad("PRG5 DESEMBOUAGE"))
    lcd.write(2, _pad("VIC:M/RET  AIR:CON "))
    lcd.write(3, _pad("Debit:  61.5 L/min"))
    lcd.write(4, _pad("Duree   00:15:20"))

    _auto("2.22 — STOPPING PRG5")
    lcd.clear()
    lcd.write_centered(1, "PROGRAMME 5")
    lcd.write_centered(2, "DESEMBOUAGE")
    lcd.write_centered(3, "Arret...")
    lcd.write_centered(4, "")

    # ── Arret machine ─────────────────────────────────────────────────────────
    _auto("2.23 — Arret machine (ecran final main.py)")
    lcd.clear()
    lcd.write_centered(1, "ARRET")
    lcd.write_centered(2, "Machine arretee")
    lcd.write_centered(3, "")
    lcd.write_centered(4, "")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST LCD 20x4 — Clean & Protech V5")
    print("=" * 54)
    print(f"  Ecran : {_COLS} colonnes x {_ROWS} lignes — 0x{config.LCD_ADDR:02X}")
    print()
    print("  PARTIE 1 : geometrie (Entree pour avancer)")
    print("  PARTIE 2 : ecrans machine (avance auto 3s)")
    print("  Ctrl+C   : quitter a tout moment")

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()

        try:
            print("\n" + "=" * 54)
            print("  PARTIE 1 — TEST GEOMETRIQUE")
            print("=" * 54)
            part1_geometry(lcd)
            part2_screens(lcd)

        except KeyboardInterrupt:
            print("\n\n  Arret (Ctrl+C)")
        finally:
            lcd.clear()

    print("=== FIN TEST LCD ===")


if __name__ == "__main__":
    main()
