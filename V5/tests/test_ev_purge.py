"""
test_ev_purge.py — Test de l'electrovanne de purge pompe (relais PURGE) — V5.

Teste UNIQUEMENT l'EV de purge : le relais POMPE n'est jamais commande.

Trois phases progressives :

    Phase 1 — ON/OFF manuel
        L'utilisateur ouvre et ferme l'EV a la main.
        Verifie que le relais V5 commute et que l'EV claque.

    Phase 2 — Purge temporisee (PURGE_TIME_S)
        L'EV s'ouvre puis se referme seule, par la minuterie utilisee en
        production. Pendant ce temps le programme de test reste BLOQUE dans
        un time.sleep() plus long que la purge : la fermeture a l'heure
        prouve que la minuterie ne depend pas de la boucle principale.

    Phase 3 — Fermeture anticipee
        L'EV est ouverte pour PURGE_TIME_S puis refermee avant la fin,
        comme lors d'un arret pompe pendant la purge. On verifie ensuite
        que l'ancienne minuterie ne fait plus rien.

Materiels impliques :
    GPIO 23 → relais V5 (contact NO) → EV purge 230V normalement fermee

Ctrl+C interrompt proprement et ferme l'EV.
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

# Marge de tolerance sur l'heure de fermeture automatique (s)
_TOLERANCE_S: float = 0.5


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _lcd_status(lcd: LCD2004, phase: str, etat: bool, info: str = "") -> None:
    """Rafraichit les 4 lignes du LCD avec l'etat courant de l'EV."""
    etat_str = "OUVERTE (ON) " if etat else "FERMEE  (OFF)"
    lcd.write_centered(1, "TEST EV PURGE")
    lcd.write(2, _pad(f"EV : {etat_str}"))
    lcd.write(3, _pad(phase))
    lcd.write(4, _pad(info))


def _sep(title: str) -> None:
    print(f"\n{'=' * 54}")
    print(f"  {title}")
    print(f"{'=' * 54}")


def _verdict(ok: bool, detail: str) -> bool:
    print(f"  {'OK   ' if ok else 'ECHEC'} — {detail}")
    return ok


# ============================================================
# Phase 1 — ON/OFF manuel
# ============================================================

def phase1_manuel(lcd: LCD2004, relays: Relays) -> None:
    _sep("PHASE 1 — ON/OFF MANUEL  (3 cycles)")
    print("  Appuyer sur Entree pour ouvrir / fermer l'EV.")
    print("  Ecouter le claquement du relais V5 et de l'EV.")

    for i in range(1, 4):
        print(f"\n  --- Cycle {i}/3 ---")

        print("  >>> Entree pour ouvrir l'EV (ON)...", end="", flush=True)
        input()
        relays.set_purge_on()
        _lcd_status(lcd, f"Phase 1 - cycle {i}/3", True, "EV ouverte")
        print("  EV OUVERTE")

        print("  >>> Entree pour fermer l'EV (OFF)...", end="", flush=True)
        input()
        relays.set_purge_off(reason="test manuel")
        _lcd_status(lcd, f"Phase 1 - cycle {i}/3", False, "EV fermee")
        print("  EV FERMEE")

    print("\n  Phase 1 terminee.")


# ============================================================
# Phase 2 — Purge temporisee, boucle volontairement bloquee
# ============================================================

def phase2_temporisee(lcd: LCD2004, relays: Relays) -> bool:
    duration = config.PURGE_TIME_S
    _sep(f"PHASE 2 — PURGE TEMPORISEE ({duration:g}s)")
    print("  L'EV s'ouvre puis se referme seule apres PURGE_TIME_S.")
    print("  Le test reste bloque pendant ce temps : la fermeture")
    print("  doit quand meme tomber a l'heure.")
    print("\n  >>> Entree pour lancer...", end="", flush=True)
    input()

    _lcd_status(lcd, "Phase 2 - temporise", True, f"Ouverte {duration:g}s")
    t0 = time.monotonic()
    relays.set_purge_on(time_s=duration)
    print(f"  EV OUVERTE — test bloque {duration + 2:g}s (sleep)...")

    # Attente bloquante qui releve l'instant de fermeture sans rien commander
    closed_at = None
    end = t0 + duration + 2.0
    while time.monotonic() < end:
        if closed_at is None and not relays.purge_is_on:
            closed_at = time.monotonic() - t0
        time.sleep(0.02)

    ok = closed_at is not None and abs(closed_at - duration) <= _TOLERANCE_S
    _lcd_status(lcd, "Phase 2 - temporise", relays.purge_is_on,
                "OK" if ok else "ECHEC")
    if closed_at is None:
        return _verdict(False, "EV toujours ouverte apres la duree prevue")
    return _verdict(ok, f"fermee apres {closed_at:.2f}s (attendu {duration:g}s)")


# ============================================================
# Phase 3 — Fermeture anticipee
# ============================================================

def phase3_anticipee(lcd: LCD2004, relays: Relays) -> bool:
    duration = config.PURGE_TIME_S
    early    = min(2.0, duration / 2)
    _sep("PHASE 3 — FERMETURE ANTICIPEE")
    print(f"  Ouverture pour {duration:g}s, fermeture forcee apres {early:g}s")
    print("  (cas d'un arret pompe pendant la purge).")
    print("\n  >>> Entree pour lancer...", end="", flush=True)
    input()

    relays.set_purge_on(time_s=duration)
    _lcd_status(lcd, "Phase 3 - anticipee", True, "EV ouverte")
    time.sleep(early)
    relays.set_purge_off(reason="test fermeture anticipee")
    ok1 = _verdict(not relays.purge_is_on, f"fermee immediatement a {early:g}s")
    _lcd_status(lcd, "Phase 3 - anticipee", relays.purge_is_on, "Fermee - attente")

    # L'ancienne minuterie ne doit plus rien faire apres son echeance
    time.sleep(duration - early + 1.0)
    ok2 = _verdict(not relays.purge_is_on, "toujours fermee apres l'echeance initiale")
    _lcd_status(lcd, "Phase 3 - anticipee", relays.purge_is_on,
                "OK" if (ok1 and ok2) else "ECHEC")
    return ok1 and ok2


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST EV PURGE — Clean & Protech V5")
    print("=" * 54)
    print(f"  Relais PURGE : GPIO {config.RELAY_PURGE_GPIO} (relais V5, contact NO)")
    print(f"  EV           : 230V, normalement fermee")
    print(f"  PURGE_TIME_S : {config.PURGE_TIME_S:g}s")
    if not config.PURGE_ENABLED:
        print("  ATTENTION : PURGE_ENABLED = False : la purge est desactivee dans les")
        print("    programmes. Ce test commande l'EV quand meme.")
    print("  Le relais POMPE n'est pas commande par ce test.")
    print("  Ctrl+C pour quitter proprement\n")

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()

        relays = Relays()
        relays.open()

        results: list[bool] = []
        try:
            phase1_manuel(lcd, relays)
            results.append(phase2_temporisee(lcd, relays))
            results.append(phase3_anticipee(lcd, relays))

        except KeyboardInterrupt:
            print("\n\n  Arret global (Ctrl+C)")

        finally:
            relays.set_purge_off(reason="fin de test")
            relays.close()
            lcd.clear()
            lcd.write_centered(1, "TEST EV PURGE")
            lcd.write_centered(2, "Termine")
            lcd.write_centered(3, "EV fermee")

    gpio_handle.close()
    if results:
        bilan = "OK" if all(results) else "ECHEC"
        print(f"\n  Bilan automatique (phases 2 et 3) : {bilan}")
    print("=== FIN TEST EV PURGE ===")


if __name__ == "__main__":
    main()
