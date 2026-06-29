"""
main.py — Programme principal Clean & Protech V5 (SERENA 230V).

FSM à 4 états actifs :
    IDLE     — attente sélection programme, LCD mis à jour 10 Hz
    STARTING — mise en place des vannes (relais, non-bloquant), placement VIC (bloquant), démarrage pompe / air
    RUNNING  — programme actif, tick 10 Hz ; arrêt si tick() retourne False (sécurité débit)
    STOPPING — arrêt pompe / air (instant), retour IDLE

Séquence de démarrage :
    1. Init hardware (IOBoard, LCD, Buzzer, Relays, FlowMeter, VICController)
    2. Homing VIC — DEPART→RETOUR×3 → NEUTRE (50 pas)
       → vic_steps = 50, valve_state = tout False (relais OFF par défaut)
    3. Boucle principale

Arrêt propre sur Ctrl+C :
    - program.stop() si programme actif
    - Pompe + air + toutes vannes forcés OFF
    - VIC driver désactivé
    - LEDs éteintes
    - 3 bips

Différences V4→V5 :
    - MotorController remplacé par VICController (GPIO direct)
    - MCP3 supprimé (plus de ENA/DIR via I2C)
    - 4 vannes relais US Solid remplacent les vannes-moteurs
    - POMPE = relais actif haut (direct, non inversé)
    - tick() retourne bool → gestion sécurité débit
"""

from __future__ import annotations

import sys
import time
from enum import Enum, auto
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
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
from programs import MachineContext, PROGRAMS, ProgramBase


# ============================================================
# FSM — états
# ============================================================

class State(Enum):
    IDLE     = auto()
    STARTING = auto()
    RUNNING  = auto()
    STOPPING = auto()


# ============================================================
# Lecture boutons — front montant + debounce
# ============================================================

def _poll_button(
    io: IOBoard,
    prev: list[bool],
    last_t: dict[int, float],
) -> int:
    """
    Retourne l'ID (1..5) du bouton sur front montant avec debounce.
    Retourne 0 si aucun bouton nouvellement pressé.
    """
    now        = time.monotonic()
    debounce_s = config.BTN_DEBOUNCE_MS / 1000.0

    for i in range(1, 6):
        cur     = bool(io.read_btn_active(i))
        was     = prev[i]
        prev[i] = cur
        if cur and not was and (now - last_t.get(i, 0.0)) >= debounce_s:
            last_t[i] = now
            return i
    return 0


# ============================================================
# Utilitaire
# ============================================================

def _fmt_elapsed(elapsed_s: float) -> str:
    m   = int(elapsed_s) // 60
    sec = int(elapsed_s) % 60
    return f"{m:02d}:{sec:02d}"


# ============================================================
# Main
# ============================================================

def main() -> None:
    log.info("=" * 44)
    log.info("  CLEAN & PROTECH — SERENA 230V — démarrage")
    log.info("=" * 44)

    gpio_handle.init()

    with I2CBus() as bus:

        # ── Init périphériques ───────────────────────────────────────────────
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

        # Variables de boucle déclarées ici pour être accessibles dans finally
        state      : State                = State.IDLE
        active_prg : ProgramBase | None   = None
        start_time : float                = 0.0
        ctx        : MachineContext | None = None

        try:
            # ── Splash ──────────────────────────────────────────────────────
            display.render_splash(lcd)
            bz.beep(repeat=2)
            time.sleep(1.5)

            # ── Homing VIC ──────────────────────────────────────────────────
            display.render_homing(lcd)
            log.info("Homing VIC — démarrage")
            t0 = time.monotonic()
            vic.homing()
            homing_dt = time.monotonic() - t0
            log.info(f"Homing VIC — terminé en {homing_dt:.1f}s")

            # MachineContext initialisé après homing :
            # valve_state = tout False (relais GPIO LOW par défaut)
            # vic_steps   = 50 (NEUTRE, résultat du homing)
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
                lcd = lcd,
                bz  = bz,
            )

            bz.ringtone_startup()
            lcd.clear()

            # ── Variables boucle ────────────────────────────────────────────
            btn_prev   : list[bool]       = [False] * 7  # index 1..5 utilisés
            btn_last_t : dict[int, float] = {}
            loop_s     : float            = 1.0 / config.MAIN_LOOP_HZ

            log.info("Machine prête — état IDLE")

            # ── Boucle principale ───────────────────────────────────────────
            while True:
                t_loop = time.monotonic()

                btn = _poll_button(io, btn_prev, btn_last_t)
                relays.tick()

                # ── IDLE ────────────────────────────────────────────────────
                if state == State.IDLE:
                    display.render_idle(lcd, io)

                    if 1 <= btn <= 5:
                        active_prg = PROGRAMS[btn]
                        bz.beep(repeat=1)  # 1 beep — bouton pressé
                        log.info(f"PRG{btn} sélectionné — {active_prg.name}")
                        state = State.STARTING

                # ── STARTING ────────────────────────────────────────────────
                elif state == State.STARTING:
                    lcd.clear()
                    display.render_starting(lcd, active_prg.id, active_prg.name)
                    io.set_led(active_prg.led_index, 1)
                    flow.reset_total()

                    log.info(f"PRG{active_prg.id} — mise en place vannes + démarrage")
                    active_prg.start(ctx)

                    start_time = time.monotonic()
                    log.info(
                        f"PRG{active_prg.id} — RUNNING"
                        f" — VIC={ctx.vic_steps} pas"
                        f" — vannes ouvertes={[k for k, v in ctx.valve_state.items() if v]}"
                    )
                    bz.beep(repeat=2)  # 2 beeps — initialisation terminée, timer démarré
                    lcd.clear()
                    state = State.RUNNING

                # ── RUNNING ─────────────────────────────────────────────────
                elif state == State.RUNNING:
                    elapsed = time.monotonic() - start_time
                    ok = active_prg.tick(ctx)
                    display.render_running(lcd, active_prg, ctx, elapsed)

                    if not ok:
                        # Sécurité débit — arrêt forcé
                        log.error(f"PRG{active_prg.id} — sécurité débit → arrêt")
                        state = State.STOPPING
                    elif btn == active_prg.id:
                        log.info(f"PRG{active_prg.id} — arrêt demandé par opérateur")
                        state = State.STOPPING

                # ── STOPPING ────────────────────────────────────────────────
                elif state == State.STOPPING:
                    elapsed = time.monotonic() - start_time
                    lcd.clear()
                    display.render_stopping(lcd, active_prg.id, active_prg.name)
                    io.set_led(active_prg.led_index, 0)

                    active_prg.stop(ctx)
                    bz.beep(repeat=1)

                    log.info(
                        f"PRG{active_prg.id} — arrêté"
                        f"  durée {_fmt_elapsed(elapsed)}"
                        f"  volume {flow.total_liters():.2f} L"
                    )

                    time.sleep(4.0)   # laisse l'écran "Arret..." visible 4 s
                    active_prg = None
                    lcd.clear()
                    state = State.IDLE

                # ── Respect timing boucle ────────────────────────────────────
                remaining = loop_s - (time.monotonic() - t_loop)
                if remaining > 0:
                    time.sleep(remaining)

        except KeyboardInterrupt:
            log.info("Arrêt demandé (Ctrl+C)")

        finally:
            # ── Arrêt propre — toujours exécuté ─────────────────────────────
            log.info("Sécurisation machine...")

            if active_prg is not None and ctx is not None:
                try:
                    active_prg.stop(ctx)
                except Exception as e:
                    log.error(f"Erreur stop PRG{active_prg.id} : {e}")

            # Sécurité double — force tout OFF même si stop() a échoué
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

            log.info("Arrêt terminé")

    gpio_handle.close()


if __name__ == "__main__":
    main()
