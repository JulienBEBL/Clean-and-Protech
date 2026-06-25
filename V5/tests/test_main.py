"""
test_main.py — Test machine complet — simulation operateur — V5.

Reproduit le comportement de main.py sans la boucle FSM :
    1. Demarrage machine : splash + homing VIC + ringtone
    2. Pour chaque programme 1..5 :
       a. Presse Entree pour simuler la pression du bouton programme
       b. start() — vannes + VIC + pompe/air (bloquant, delais reels)
       c. Observation : LCD mis a jour en temps reel, presse Entree pour arreter
       d. stop() — arret pompe/air, VIC NEUTRE si applicable
    3. Arret propre

La securite debit n'est PAS activee (tick() non appele) — test sans eau OK.
Le comportement VIC en mode manuel PRG5 n'est pas simule (start() lit le selecteur,
puis la position reste fixe pendant l'observation).

Ctrl+C quitte proprement a tout moment.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
import display
import libs.gpio_handle as gpio_handle
from libs.buzzer import Buzzer
from libs.debitmetre import FlowMeter
from libs.i2c_bus import I2CBus
from libs.io_board import IOBoard
from libs.lcd2004 import LCD2004
from libs.relays import Relays
from libs.vic import VICController
from logger import log
from programs import MachineContext, PROGRAMS


# ============================================================
# Helpers
# ============================================================

def _sep(title: str) -> None:
    print(f"\n{'=' * 58}")
    print(f"  {title}")
    print(f"{'=' * 58}")


def _fmt_elapsed(elapsed_s: float) -> str:
    m = int(elapsed_s) // 60
    s = int(elapsed_s) % 60
    return f"{m:02d}:{s:02d}"


def _lcd_update_loop(
    lcd: LCD2004,
    prg,
    ctx: MachineContext,
    t_start: float,
    stop_event: threading.Event,
) -> None:
    """Thread : met a jour le LCD toutes les 500ms pendant l'observation."""
    while not stop_event.is_set():
        elapsed = time.monotonic() - t_start
        try:
            lines = prg.lcd_info(ctx, elapsed)
            for i, line in enumerate(lines, 1):
                lcd.write(i, line)
        except Exception:
            pass
        time.sleep(0.5)


# ============================================================
# Test d'un programme
# ============================================================

def _run_program(
    lcd: LCD2004,
    bz: Buzzer,
    io: IOBoard,
    prg,
    ctx: MachineContext,
) -> None:
    _sep(f"PRG{prg.id} — {prg.name}")

    # Info programme
    open_valves = getattr(prg, "_OPEN_VALVES", ())
    if open_valves:
        print(f"  Vannes  : {', '.join(open_valves)}")
    else:
        print(f"  Vannes  : aucune (gestion interne tick)")
    print(f"  Note    : start() bloque pendant la mise en place des vannes")
    print()
    print(f"  >>> Entree pour demarrer PRG{prg.id}...", end="", flush=True)
    input()

    # Affichage demarrage
    lcd.clear()
    display.render_starting(lcd, prg.id, prg.name)
    io.set_led(prg.led_index, 1)
    log.info(f"PRG{prg.id} — start()")

    t_before = time.monotonic()
    prg.start(ctx)
    t_start = time.monotonic()
    dt_start = t_start - t_before
    log.info(f"PRG{prg.id} — actif (start en {dt_start:.1f}s)")
    print(f"  PRG{prg.id} actif (mise en place : {dt_start:.1f}s)")
    print()
    print(f"  >>> Entree pour arreter PRG{prg.id}...", end="", flush=True)

    # Thread LCD pendant l'observation
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_lcd_update_loop,
        args=(lcd, prg, ctx, t_start, stop_event),
        daemon=True,
    )
    thread.start()

    input()  # Attente operateur

    stop_event.set()
    thread.join(timeout=1.0)

    elapsed = time.monotonic() - t_start
    log.info(f"PRG{prg.id} — stop() apres {_fmt_elapsed(elapsed)}")

    # Affichage arret
    lcd.clear()
    display.render_stopping(lcd, prg.id, prg.name)
    prg.stop(ctx)
    io.set_led(prg.led_index, 0)
    bz.beep(repeat=1)

    print(f"  PRG{prg.id} arrete (duree : {_fmt_elapsed(elapsed)})")


# ============================================================
# Main
# ============================================================

def main() -> None:
    _sep("TEST MACHINE COMPLET — simulation operateur — V5")
    print()
    print("  Ce test reproduit l'utilisation de la machine par un operateur.")
    print("  La securite debit est desactivee (pas d'eau necessaire).")
    print()
    print("  Sequence :")
    print("    1. Demarrage machine (homing VIC)")
    for prg_id, prg in PROGRAMS.items():
        print(f"    {prg_id + 1}. PRG{prg_id} {prg.name}")
    print()
    print("  Ctrl+C pour quitter proprement a tout moment.")
    print()
    print("  >>> Entree pour demarrer...", end="", flush=True)
    input()

    log.info("test_main — demarrage")
    gpio_handle.init()

    with I2CBus() as bus:

        # ---- Init hardware ----
        io = IOBoard(bus)
        io.init()
        io.set_all_leds(0)

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()

        bz = Buzzer()
        bz.open()

        relays = Relays()
        relays.open()

        flow = FlowMeter()
        flow.open()

        vic = VICController()
        vic.open()

        ctx: MachineContext | None = None

        try:
            # ---- Splash ----
            _sep("DEMARRAGE MACHINE")
            display.render_splash(lcd)
            bz.beep(repeat=2)
            time.sleep(1.5)

            # ---- Homing VIC ----
            print("  Homing VIC en cours...")
            display.render_homing(lcd)
            log.info("Homing VIC — demarrage")
            t0 = time.monotonic()
            vic.homing()
            dt = time.monotonic() - t0
            log.info(f"Homing VIC — termine en {dt:.1f}s, position {vic.position} pas")
            print(f"  Homing VIC termine en {dt:.1f}s — position : {vic.position} pas")

            # ---- Context ----
            ctx = MachineContext(
                vic    = vic,
                relays = relays,
                io     = io,
                flow   = flow,
                valve_state = {
                    "POT_A_BOUE":   False,
                    "EGOUTS":       False,
                    "CUVE_TRAVAIL": False,
                    "EAU_PROPRE":   False,
                },
                vic_steps = config.VIC_NEUTRE_STEPS,
            )

            bz.ringtone_startup()
            lcd.clear()
            print("  Machine prete.")

            # ---- Programmes ----
            for prg_id, prg in PROGRAMS.items():
                _run_program(lcd, bz, io, prg, ctx)

            # ---- Fin ----
            _sep("TEST TERMINE")
            print("  Tous les programmes ont ete executes.")
            lcd.clear()
            lcd.write_centered(1, "TEST TERMINE")
            lcd.write_centered(2, "Tous PRG OK")
            bz.beep(repeat=3)
            log.info("test_main — tous programmes executes")

        except KeyboardInterrupt:
            print("\n\n  Arret demande (Ctrl+C)")
            log.info("test_main — arret Ctrl+C")

        finally:
            # ---- Arret propre ----
            log.info("Securisation machine...")
            try:
                relays.set_pompe_off()
                relays.set_air_off()
                relays.close_all_valves()
            except Exception:
                pass
            try:
                vic.disable()
            except Exception:
                pass
            io.set_all_leds(0)
            try:
                bz.beep(time_ms=200, repeat=3, gap_ms=150)
            except Exception:
                pass

            lcd.clear()
            lcd.write_centered(1, "ARRET")
            lcd.write_centered(2, "Machine arretee")

            bz.close()
            relays.close()
            flow.close()
            vic.close()
            log.info("test_main — arret termine")

    gpio_handle.close()
    print("=== FIN TEST MAIN ===")


if __name__ == "__main__":
    main()
