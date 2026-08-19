"""
main.py — Programme principal Clean & Protech V5 (SERENA 230V).

FSM à 5 états actifs :
    IDLE     — attente sélection programme, LCD mis à jour 10 Hz
    CONFIRM  — avertissement "cuve vide" avant PRG2 / PRG4 ; validation par un
               2e appui sur le même bouton, abandon automatique après timeout
    STARTING — écran de consignes avant-programme (bloquant, automatique), puis
               mise en place des vannes (relais, non-bloquant), placement VIC (bloquant), démarrage pompe / air
    RUNNING  — programme actif, tick 10 Hz ; arrêt si tick() retourne False (sécurité débit / cuve vide)
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
from libs.led_blinker import LedBlinker
from libs.relays import Relays
from libs.vic import VICController
from logger import log
from programs import MachineContext, PROGRAMS, ProgramBase


# ============================================================
# FSM — états
# ============================================================

class State(Enum):
    IDLE     = auto()
    CONFIRM  = auto()   # avertissement cuve vide — attente 2e appui (PRG2 / PRG4)
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
# Motif sonore non bloquant
# ============================================================

class _SalvoBeeper:
    """
    Motif sonore répétitif NON BLOQUANT : salve de N bips, pause, répétition.

    Piloté par la boucle principale via tick(). Contrairement à Buzzer.beep(),
    il ne bloque jamais : indispensable sur un écran qui doit rester à l'écoute
    des boutons pendant que le buzzer sonne (confirmation cuve vide).

    La résolution est celle de la boucle principale (MAIN_LOOP_HZ) : un bip dure
    au minimum une itération, soit 100 ms à 10 Hz. Le gap inter-bips est donc
    arrondi à la période de boucle — le motif reste "bip-bip … pause … bip-bip".
    """

    def __init__(
        self,
        bz: Buzzer,
        count: int,
        pause_s: float,
        beep_ms: int = config.BUZZER_BEEP_TIME_MS,
        gap_ms: int  = config.BUZZER_BEEP_GAP_MS,
    ) -> None:
        self._bz       = bz
        self._count    = max(1, int(count))
        self._pause_s  = float(pause_s)
        self._beep_s   = max(1, int(beep_ms)) / 1000.0
        self._gap_s    = max(0, int(gap_ms)) / 1000.0
        self._phase    = "idle"      # idle | on | gap | pause
        self._deadline = 0.0
        self._left     = 0

    def start(self, now: float) -> None:
        """Démarre le motif immédiatement par une première salve."""
        self._left = self._count
        self._beep_on(now)

    def stop(self) -> None:
        """Coupe le buzzer et arrête le motif. Idempotente."""
        self._phase = "idle"
        try:
            self._bz.off()
        except Exception:
            pass

    def _beep_on(self, now: float) -> None:
        self._bz.on()
        self._phase    = "on"
        self._deadline = now + self._beep_s

    def tick(self, now: float) -> None:
        """À appeler à chaque itération de la boucle principale."""
        if self._phase == "idle" or now < self._deadline:
            return
        if self._phase == "on":
            self._bz.off()
            self._left -= 1
            if self._left > 0:
                self._phase    = "gap"
                self._deadline = now + self._gap_s
            else:
                self._phase    = "pause"
                self._deadline = now + self._pause_s
        elif self._phase == "gap":
            self._beep_on(now)
        elif self._phase == "pause":
            self._left = self._count
            self._beep_on(now)


# ============================================================
# Écran avant-programme — consignes opérateur
# ============================================================

def _show_pre_program_screen(
    lcd: LCD2004,
    bz: Buzzer,
    prg_id: int,
    leds: LedBlinker | None = None,
) -> None:
    """
    Affiche les consignes opérateur avant le lancement du programme.

    BLOQUANTE et purement automatique : aucun bouton n'est lu pendant
    l'affichage, et le programme démarre seul à l'expiration du délai.
    Appelée avant toute action machine (ni vanne, ni VIC, ni pompe).

    Motif sonore : salve de PREMSG_BEEP_COUNT bips, pause PREMSG_BEEP_PAUSE_S,
    répétée jusqu'à la fin du délai. La dernière pause est tronquée pour ne
    pas dépasser la durée demandée.
    """
    duration = config.PREMSG_TIME_S.get(prg_id, 0.0)
    if duration <= 0.0:
        return

    log.info(f"PRG{prg_id} — écran avant-programme ({duration:.0f}s)")

    # Rendu une seule fois : le contenu est fixe (pas de compte à rebours)
    lcd.clear()
    display.render_pre_program(lcd, prg_id)

    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        bz.beep(repeat=config.PREMSG_BEEP_COUNT)
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            break
        pause = min(config.PREMSG_BEEP_PAUSE_S, remaining)
        # Attente animée : la LED programme continue de clignoter
        if leds is not None:
            leds.sleep(pause)
        else:
            time.sleep(pause)


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

        # Animation des LEDs programme. Le callback de pas VIC permet à la LED
        # de continuer à clignoter pendant les déplacements moteur bloquants
        # (mini-homing d'un start(), retour NEUTRE d'un stop()).
        leds = LedBlinker(io)
        vic.set_step_callback(leds.tick)

        # Variables de boucle déclarées ici pour être accessibles dans finally
        state        : State                = State.IDLE
        active_prg   : ProgramBase | None   = None
        start_time   : float                = 0.0
        confirm_until: float                = 0.0
        ctx          : MachineContext | None = None

        try:
            # ── Splash ──────────────────────────────────────────────────────
            display.render_splash(lcd)
            bz.beep(repeat=2)
            time.sleep(config.LCD_WELCOME_SCREEN_TIME_S)

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
                lcd  = lcd,
                bz   = bz,
                leds = leds,
            )

            bz.ringtone_startup()
            lcd.clear()

            # ── Variables boucle ────────────────────────────────────────────
            btn_prev   : list[bool]       = [False] * 7  # index 1..5 utilisés
            btn_last_t : dict[int, float] = {}
            loop_s     : float            = 1.0 / config.MAIN_LOOP_HZ

            # Motif sonore de l'écran de confirmation cuve vide — non bloquant,
            # pour que le 2e appui reste détectable pendant que le buzzer sonne.
            confirm_beeper = _SalvoBeeper(
                bz,
                config.CUVE_VIDE_CONFIRM_BEEP_COUNT,
                config.CUVE_VIDE_CONFIRM_BEEP_PAUSE_S,
            )

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
                        # Transition : LED du programme clignotante jusqu'à RUNNING
                        leds.attach(active_prg.led_index)
                        leds.blink(time.monotonic())

                        if btn in config.CUVE_VIDE_CONFIRM_PROGRAMS:
                            # PRG2 / PRG4 — avertissement cuve vide avant lancement
                            lcd.clear()
                            confirm_until = (
                                time.monotonic() + config.CUVE_VIDE_CONFIRM_TIMEOUT_S
                            )
                            log.info(
                                f"PRG{btn} — attente confirmation cuve vide "
                                f"({config.CUVE_VIDE_CONFIRM_TIMEOUT_S:.0f}s max)"
                            )
                            confirm_beeper.start(time.monotonic())
                            state = State.CONFIRM
                        else:
                            state = State.STARTING

                # ── CONFIRM — avertissement cuve vide (PRG2 / PRG4) ─────────
                elif state == State.CONFIRM:
                    now_confirm = time.monotonic()
                    remaining   = confirm_until - now_confirm
                    display.render_cuve_vide_confirm(lcd, active_prg.id)
                    confirm_beeper.tick(now_confirm)
                    leds.tick(now_confirm)

                    if btn == active_prg.id:
                        # 2e appui sur le même bouton → validation
                        confirm_beeper.stop()
                        log.info(f"PRG{active_prg.id} — cuve vide confirmée par l'opérateur")
                        state = State.STARTING
                    elif remaining <= 0.0:
                        # Pas de confirmation → abandon, retour IDLE
                        confirm_beeper.stop()
                        log.info(f"PRG{active_prg.id} — confirmation non reçue → abandon")
                        leds.off()          # retour IDLE — plus aucune LED allumée
                        active_prg = None
                        lcd.clear()
                        state = State.IDLE

                # ── STARTING ────────────────────────────────────────────────
                elif state == State.STARTING:
                    # Consignes opérateur — bloquant, avant toute action machine
                    _show_pre_program_screen(lcd, bz, active_prg.id, leds)

                    lcd.clear()
                    display.render_starting(lcd, active_prg.id, active_prg.name)
                    flow.reset_total()

                    log.info(f"PRG{active_prg.id} — mise en place vannes + démarrage")
                    active_prg.start(ctx)

                    log.info(
                        f"PRG{active_prg.id} — RUNNING"
                        f" — VIC={ctx.vic_steps} pas"
                        f" — vannes ouvertes={[k for k, v in ctx.valve_state.items() if v]}"
                    )
                    # Bip long — signale le lancement effectif du programme
                    bz.beep(time_ms=config.BUZZER_PROGRAM_SIGNAL_MS, repeat=1)
                    # RUNNING : la LED passe de clignotante à allumée fixe
                    leds.fixed()
                    # Timer démarré APRÈS le bip : la durée affichée part de 00:00
                    start_time = time.monotonic()
                    lcd.clear()
                    state = State.RUNNING

                # ── RUNNING ─────────────────────────────────────────────────
                elif state == State.RUNNING:
                    elapsed = time.monotonic() - start_time
                    ok = active_prg.tick(ctx)
                    display.render_running(lcd, active_prg, ctx, elapsed)

                    if not ok:
                        # Sécurité débit (PRG5) ou cuve vide (PRG2/PRG4) — arrêt forcé
                        log.error(f"PRG{active_prg.id} — sécurité → arrêt")
                        state = State.STOPPING
                    elif btn == active_prg.id:
                        log.info(f"PRG{active_prg.id} — arrêt demandé par opérateur")
                        state = State.STOPPING

                # ── STOPPING ────────────────────────────────────────────────
                elif state == State.STOPPING:
                    elapsed = time.monotonic() - start_time
                    lcd.clear()
                    display.render_stopping(lcd, active_prg.id, active_prg.name)
                    # Transition d'arrêt : LED clignotante jusqu'au retour IDLE
                    leds.blink(time.monotonic())

                    active_prg.stop(ctx)
                    # Bip long — signale l'arrêt du programme (même signal qu'au lancement)
                    bz.beep(time_ms=config.BUZZER_PROGRAM_SIGNAL_MS, repeat=1)

                    log.info(f"PRG{active_prg.id} — arrêté  durée {_fmt_elapsed(elapsed)}")

                    if active_prg.id == 5:
                        # PRG5 — récapitulatif volume total consommé sur cette exécution
                        lcd.clear()
                        display.render_prg5_summary(lcd, active_prg.id, active_prg.name, flow.total_liters())
                        leds.sleep(config.LCD_PRG5_SUMMARY_TIME_S)
                    else:
                        leds.sleep(config.LCD_STOP_SCREEN_TIME_S)

                    leds.off()          # retour IDLE — plus aucune LED allumée
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
                    # Séquence d'arrêt machine : LED clignotante pendant stop()
                    leds.blink(time.monotonic())
                except Exception:
                    pass
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
