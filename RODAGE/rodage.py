"""
rodage.py — Programme de rodage des moteurs Clean & Protech.

Objectif : simuler des cycles de désembouage semi-réalistes en enchaînant
automatiquement une séquence de programmes PRG1..PRG5 de V4.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CONFIGURATION (à ajuster selon le plombier)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Modifier les deux variables ci-dessous :

  SEQUENCE         — liste ordonnée des numéros de programme (1..5)
  DURATIONS_S      — durée en secondes de chaque programme par numéro
                     (si un numéro n'est pas dans le dict → DEFAULT_DURATION_S)

Exemple :
  SEQUENCE     = [1, 2, 3, 1, 2, 3, 1, 2, 3, 4, 3, 4, 5, 1, 5, 1]
  DURATIONS_S  = {1: 60, 2: 120, 3: 90, 4: 120, 5: 180}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ── Chemin vers V4 ────────────────────────────────────────────────────────────
# rodage.py est dans RODAGE/ — V4/ est au même niveau dans le dépôt
PROJECT_ROOT = Path(__file__).resolve().parent.parent / "V4"
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
from libs.moteur import MotorController
from libs.relays import Relays
from logger import log
from programs import MachineContext, PROGRAMS


# ============================================================
#  CONFIGURATION — modifier ici selon consignes du plombier
# ============================================================

# Séquence des programmes à enchaîner (numéros 1..5)
# Exemple provisoire — à remplacer avec la vraie séquence
SEQUENCE: list[int] = [
    1, 2, 3,
    1, 2, 3,
    1, 2, 3,
    4, 3, 4,
    5, 1, 5, 1,
]

# Durée d'exécution (secondes) par numéro de programme
# Ajuster chaque valeur selon les besoins du rodage
DURATIONS_S: dict[int, int] = {
    1: 60,   # PREM.VIDANGE  — 1 min
    2: 120,  # VIDANGE CUVE  — 2 min
    3: 90,   # SECHAGE       — 1 min 30 s
    4: 120,  # REMPLISSAGE   — 2 min
    5: 180,  # DESEMBOUAGE   — 3 min
}

# Durée utilisée si le numéro n'est pas dans DURATIONS_S
DEFAULT_DURATION_S: int = 10

# Pause entre deux programmes (secondes) — laisse l'écran "Arrêt" visible
PAUSE_BETWEEN_S: float = 5.0

# ============================================================
#  Helpers LCD
# ============================================================

def _fmt_elapsed(elapsed_s: float) -> str:
    m   = int(elapsed_s) // 60
    sec = int(elapsed_s) % 60
    return f"{m:02d}:{sec:02d}"


def _render_rodage_running(
    lcd: LCD2004,
    step: int,
    total_steps: int,
    prg_id: int,
    prg_name: str,
    elapsed_s: float,
    duration_s: int,
) -> None:
    """Affichage pendant l'exécution d'une étape du rodage."""
    remaining = max(0, duration_s - int(elapsed_s))
    rem_m  = remaining // 60
    rem_s  = remaining % 60
    pct    = int(elapsed_s / duration_s * 100) if duration_s > 0 else 100

    lcd.write(1, f"RODAGE  {step:>2}/{total_steps:<2}  {pct:3d}%")
    lcd.write(2, f"PRG{prg_id} {prg_name[:15]:<15}")
    lcd.write(3, f"Ecoule  {_fmt_elapsed(elapsed_s):>5}      ")
    lcd.write(4, f"Restant {rem_m:02d}:{rem_s:02d}      ")


def _render_rodage_step_start(
    lcd: LCD2004,
    step: int,
    total_steps: int,
    prg_id: int,
    prg_name: str,
) -> None:
    lcd.clear()
    lcd.write_centered(1, f"RODAGE  {step}/{total_steps}")
    lcd.write_centered(2, f"PROGRAMME {prg_id}")
    lcd.write_centered(3, prg_name[:20])
    lcd.write_centered(4, "Mise en place...")


def _render_rodage_step_stop(
    lcd: LCD2004,
    step: int,
    total_steps: int,
    prg_id: int,
) -> None:
    lcd.clear()
    lcd.write_centered(1, f"RODAGE  {step}/{total_steps}")
    lcd.write_centered(2, f"FIN PRG{prg_id}")
    lcd.write_centered(3, "")
    lcd.write_centered(4, "Pause...")


def _render_rodage_finished(lcd: LCD2004, total_volume: float) -> None:
    lcd.clear()
    lcd.write_centered(1, "RODAGE TERMINE")
    lcd.write_centered(2, f"Vol. total: {total_volume:.1f} L")
    lcd.write_centered(3, "")
    lcd.write_centered(4, "Arret machine")


# ============================================================
#  Main
# ============================================================

def main() -> None:
    total_steps = len(SEQUENCE)
    log.info("=" * 44)
    log.info("  RODAGE — démarrage")
    log.info(f"  Séquence : {SEQUENCE}")
    log.info(f"  {total_steps} étapes au total")
    log.info("=" * 44)

    gpio_handle.init()

    with I2CBus() as bus:

        # ── Init périphériques ────────────────────────────────────────────────
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

        with MotorController(io) as motors:

            active_prg = None
            ctx        = None

            try:
                # ── Splash ───────────────────────────────────────────────────
                lcd.clear()
                lcd.write_centered(1, "CLEAN & PROTECH")
                lcd.write_centered(2, "--- RODAGE ---")
                lcd.write_centered(3, f"{total_steps} etapes")
                lcd.write_centered(4, "Demarrage...")
                bz.beep(repeat=2)
                time.sleep(2.0)

                # ── Homing ───────────────────────────────────────────────────
                display.render_homing(lcd)
                log.info("Homing — démarrage")
                t0 = time.monotonic()
                motors.homing()
                homing_dt = time.monotonic() - t0
                log.info(f"Homing — terminé en {homing_dt:.1f}s")

                ctx = MachineContext(
                    motors = motors,
                    relays = relays,
                    io     = io,
                    flow   = flow,
                    valve_state = {
                        "RETOUR":       True,
                        "POT_A_BOUE":   True,
                        "CUVE_TRAVAIL": True,
                        "EGOUTS":       True,
                        "DEPART":       True,
                        "EAU_PROPRE":   True,
                        "POMPE":        True,
                    },
                    vic_steps = 0,
                )

                bz.ringtone_startup()
                lcd.clear()
                log.info("Machine prête — début séquence rodage")

                loop_s = 1.0 / config.MAIN_LOOP_HZ

                # ── Boucle séquence ───────────────────────────────────────────
                for step, prg_id in enumerate(SEQUENCE, start=1):

                    active_prg = PROGRAMS[prg_id]
                    duration_s = DURATIONS_S.get(prg_id, DEFAULT_DURATION_S)

                    log.info(
                        f"[{step}/{total_steps}] PRG{prg_id} — {active_prg.name}"
                        f"  durée prévue {duration_s}s"
                    )

                    # ── STARTING ─────────────────────────────────────────────
                    _render_rodage_step_start(lcd, step, total_steps, prg_id, active_prg.name)
                    io.set_led(active_prg.led_index, 1)
                    flow.reset_total()

                    active_prg.start(ctx)
                    start_time = time.monotonic()
                    lcd.clear()
                    log.info(f"[{step}/{total_steps}] PRG{prg_id} — RUNNING")

                    # ── RUNNING jusqu'à expiration ────────────────────────────
                    while True:
                        t_loop  = time.monotonic()
                        elapsed = t_loop - start_time

                        relays.tick()
                        active_prg.tick(ctx)
                        _render_rodage_running(
                            lcd, step, total_steps,
                            prg_id, active_prg.name,
                            elapsed, duration_s,
                        )

                        if elapsed >= duration_s:
                            break

                        remaining = loop_s - (time.monotonic() - t_loop)
                        if remaining > 0:
                            time.sleep(remaining)

                    # ── STOPPING ─────────────────────────────────────────────
                    elapsed = time.monotonic() - start_time
                    _render_rodage_step_stop(lcd, step, total_steps, prg_id)
                    io.set_led(active_prg.led_index, 0)

                    active_prg.stop(ctx)
                    bz.beep(repeat=1)

                    log.info(
                        f"[{step}/{total_steps}] PRG{prg_id} — arrêté"
                        f"  durée réelle {_fmt_elapsed(elapsed)}"
                        f"  volume {flow.total_liters():.2f} L"
                    )

                    active_prg = None
                    time.sleep(PAUSE_BETWEEN_S)
                    lcd.clear()

                # ── Fin de séquence ───────────────────────────────────────────
                total_volume = flow.total_liters()
                log.info(
                    f"Rodage terminé — {total_steps} étapes"
                    f"  volume total cumulé {total_volume:.2f} L"
                )
                _render_rodage_finished(lcd, total_volume)
                bz.beep(time_ms=300, repeat=3, gap_ms=200)
                time.sleep(10.0)

            except KeyboardInterrupt:
                log.info("Rodage interrompu (Ctrl+C)")

            finally:
                # ── Arrêt propre ─────────────────────────────────────────────
                log.info("Sécurisation machine...")

                if active_prg is not None and ctx is not None:
                    try:
                        active_prg.stop(ctx)
                    except Exception as e:
                        log.error(f"Erreur stop PRG{active_prg.id} : {e}")

                try:
                    relays.set_pompe_off()
                    relays.set_air_off()
                except Exception:
                    pass

                io.set_all_leds(0)
                io.disable_all_drivers()

                try:
                    bz.beep(time_ms=200, repeat=3, gap_ms=150)
                except Exception:
                    pass

                lcd.clear()
                lcd.write_centered(1, "ARRET RODAGE")
                lcd.write_centered(2, "Machine arretee")

                bz.close()
                relays.close()
                flow.close()

                log.info("Arrêt terminé")

    gpio_handle.close()


if __name__ == "__main__":
    main()
