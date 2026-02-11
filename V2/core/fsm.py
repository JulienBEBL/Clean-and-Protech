# core/fsm.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Dict

from hw.inputs import Inputs, InputEvent
from hw.leds import ProgramLeds


PROGRAMS: Dict[int, str] = {
    1: "Premiere Vidange",
    2: "Vidange Cuve Travail",
    3: "Sechage",
    4: "Remplissage Cuve",
    5: "Desembouage",
}


def _safe_set_pump(relays, on: bool) -> None:
    """
    Adaptateur minimal pour ta librairie relays_critical.py.
    On ne connaît pas encore ton API exacte, donc on tente plusieurs méthodes.
    """
    if hasattr(relays, "set_pump"):
        relays.set_pump(on)
        return
    if on and hasattr(relays, "pump_on"):
        relays.pump_on()
        return
    if (not on) and hasattr(relays, "pump_off"):
        relays.pump_off()
        return
    # fallback: all_off
    if hasattr(relays, "all_off") and not on:
        relays.all_off()
        return
    raise AttributeError("Impossible de piloter la pompe (API relais inconnue)")


def _safe_set_air(relays, on: bool) -> None:
    if hasattr(relays, "set_air"):
        relays.set_air(on)
        return
    if on and hasattr(relays, "air_on"):
        relays.air_on()
        return
    if (not on) and hasattr(relays, "air_off"):
        relays.air_off()
        return
    # fallback: all_off
    if hasattr(relays, "all_off") and not on:
        relays.all_off()
        return
    raise AttributeError("Impossible de piloter l'air (API relais inconnue)")


@dataclass
class MachineState:
    mode: str = "IDLE"                 # "IDLE" ou "RUN"
    active_program: Optional[int] = None
    program_start_mono: float = 0.0

    vic: Optional[object] = None       # 1..5 / None / "invalid"
    air: Optional[object] = None       # 1..4 / None / "invalid"


class MachineFSM:
    """
    FSM minimal:
      - IDLE: affichage choix programme
      - RUN: programme actif, pompe ON (optionnel), chrono

    Événements traités:
      - btn_prog_pressed (1..6) : start/stop programme
      - vic_changed / air_changed : log + mémorisation
    """

    def __init__(self, inputs: Inputs, leds: ProgramLeds, lcd, relays, flowmeter, logger):
        self.inputs = inputs
        self.leds = leds
        self.lcd = lcd
        self.relays = relays
        self.flowmeter = flowmeter
        self.log = logger

        self.state = MachineState()

        # rafraîchissement LCD
        self._last_lcd_update = 0.0
        self.lcd_period_s = 1.0

        # choix: pompe ON quand un programme tourne ?
        self.pump_on_when_running = True

    # ------------------ API principale ------------------

    def tick(self) -> None:
        """
        À appeler en boucle depuis le main (ex: toutes les 50-100ms).
        """
        now = time.monotonic()

        # 1) traiter événements entrées
        for ev in self.inputs.get_events():
            self._handle_event(ev)

        # 2) rafraîchir LCD
        if (now - self._last_lcd_update) >= self.lcd_period_s:
            self._update_lcd(now)
            self._last_lcd_update = now

    # ------------------ gestion événements ------------------

    def _handle_event(self, ev: InputEvent) -> None:
        if ev.type == "btn_prog_pressed":
            prog = int(ev.value)
            self._handle_program_button(prog)
            return

        if ev.type == "vic_changed":
            self.state.vic = ev.value
            self.log.info("Changement VIC: %s", ev.value)
            return

        if ev.type == "air_changed":
            self.state.air = ev.value
            self.log.info("Changement AIR: %s", ev.value)
            return

    def _handle_program_button(self, prog: int) -> None:
        # On ne gère que 1..5 pour l'instant
        if prog not in PROGRAMS:
            self.log.info("Bouton programme %d ignoré (non configuré)", prog)
            return

        if self.state.mode == "IDLE":
            self._start_program(prog)
            return

        # RUN
        if self.state.active_program == prog:
            self._stop_program()
        else:
            # ton besoin actuel: si un programme tourne et on appuie sur un autre,
            # on ignore (ou on pourrait faire "switch"). On ignore pour rester simple.
            self.log.info("Programme %d pressé pendant RUN(%s) -> ignoré",
                          prog, self.state.active_program)

    # ------------------ actions ------------------

    def _start_program(self, prog: int) -> None:
        self.state.mode = "RUN"
        self.state.active_program = prog
        self.state.program_start_mono = time.monotonic()

        self.leds.show_active_program(prog)

        if self.pump_on_when_running:
            try:
                _safe_set_pump(self.relays, True)
            except Exception as e:
                self.log.error("Impossible d'activer pompe: %s", e)

        name = PROGRAMS.get(prog, f"Programme {prog}")
        self.log.info("START programme %d: %s", prog, name)

        # petit bip court (si tu as un buzzer plus tard)
        # (pas implémenté ici)

    def _stop_program(self) -> None:
        prog = self.state.active_program
        elapsed = 0.0
        if prog is not None:
            elapsed = time.monotonic() - self.state.program_start_mono

        # pompe OFF
        try:
            _safe_set_pump(self.relays, False)
        except Exception as e:
            self.log.error("Impossible de couper pompe: %s", e)

        self.leds.show_active_program(None)

        self.log.info("STOP programme %s (durée %.1fs)", prog, elapsed)

        self.state.mode = "IDLE"
        self.state.active_program = None
        self.state.program_start_mono = 0.0

    # ------------------ LCD ------------------

    def _update_lcd(self, now_mono: float) -> None:
        try:
            flow_l_min = float(self.flowmeter.get_flow_l_min())
            total_l = float(self.flowmeter.get_total_liters())
        except Exception:
            flow_l_min = 0.0
            total_l = 0.0

        if self.state.mode == "IDLE":
            self._lcd_idle(total_l)
        else:
            prog = int(self.state.active_program or 0)
            elapsed = now_mono - self.state.program_start_mono
            self._lcd_run(prog, elapsed, flow_l_min, total_l)

    def _lcd_idle(self, total_l: float) -> None:
        self.lcd.lcd_string("Choix programme", self.lcd.LCD_LINE_1)
        self.lcd.lcd_string("1..5", self.lcd.LCD_LINE_2)
        self.lcd.lcd_string(f"Total: {total_l:6.1f} L", self.lcd.LCD_LINE_3)
        self.lcd.lcd_string("Pompe: OFF", self.lcd.LCD_LINE_4)

    def _lcd_run(self, prog: int, elapsed_s: float, flow_l_min: float, total_l: float) -> None:
        name = PROGRAMS.get(prog, f"Prog {prog}")
        # 20 char max (LCD 20x4)
        line1 = f"{prog}:{name}"[:20]
        mm = int(elapsed_s // 60)
        ss = int(elapsed_s % 60)
        line2 = f"Temps: {mm:02d}:{ss:02d}"

        line3 = f"Debit: {flow_l_min:6.1f}L/m"[:20]
        line4 = f"Total: {total_l:6.1f}L"[:20]

        self.lcd.lcd_string(line1, self.lcd.LCD_LINE_1)
        self.lcd.lcd_string(line2, self.lcd.LCD_LINE_2)
        self.lcd.lcd_string(line3, self.lcd.LCD_LINE_3)
        self.lcd.lcd_string(line4, self.lcd.LCD_LINE_4)
