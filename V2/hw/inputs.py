# hw/inputs.py
from __future__ import annotations

import time
import threading
import queue
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

from hw.mcp_hub import MCPHub


@dataclass(frozen=True)
class InputEvent:
    """
    Événements générés par Inputs.
    type:
      - "btn_prog_pressed" (programme 1..6)
      - "vic_changed" (position 1..5 ou None ou "invalid")
      - "air_changed" (position 1..4 ou None ou "invalid")
    """
    type: str
    value: object
    timestamp_s: float


class Inputs:
    """
    Lecture des entrées via MCPHub, avec anti-rebond logiciel + détection de changements.

    Mapping (fixe selon tes infos) :
      MCP1 (programme) : boutons sur PORT B bits 0..5 => PRG1..PRG6 (actif bas)
      MCP2 (sélecteurs):
        - VIC1..VIC5 sur PORT B bits 0..4 (actif bas)
        - AIR4..AIR1 sur PORT A bits 4..7 (actif bas)  (attention: ordre inversé)
    """

    def __init__(
        self,
        mcp: MCPHub,
        poll_hz: int = 100,
        debounce_ms: int = 30,
        active_low_buttons: bool = True,
        active_low_selectors: bool = True,
    ):
        self.mcp = mcp
        self.poll_period_s = 1.0 / max(1, poll_hz)
        self.debounce_s = debounce_ms / 1000.0
        self.active_low_buttons = active_low_buttons
        self.active_low_selectors = active_low_selectors

        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None
        self._q: "queue.Queue[InputEvent]" = queue.Queue()

        # états "bruts" et "stables" pour anti-rebond
        self._btn_raw: Dict[int, int] = {}
        self._btn_stable: Dict[int, int] = {}
        self._btn_last_change: Dict[int, float] = {}

        # état sélecteurs (positions exclusives)
        self._vic_raw: Optional[object] = None
        self._vic_stable: Optional[object] = None
        self._vic_last_change: float = 0.0

        self._air_raw: Optional[object] = None
        self._air_stable: Optional[object] = None
        self._air_last_change: float = 0.0

    # ----------------------- API publique -----------------------

    def start(self) -> None:
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._run, name="inputs", daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._stop.set()
        if self._th:
            self._th.join(timeout=1.0)

    def get_events(self, max_events: int = 50) -> List[InputEvent]:
        events: List[InputEvent] = []
        for _ in range(max_events):
            try:
                events.append(self._q.get_nowait())
            except queue.Empty:
                break
        return events

    def snapshot(self) -> dict:
        """État stable courant (utile pour debug/LCD)."""
        return {
            "buttons": {f"PRG{i}": self._btn_stable.get(i, 0) for i in range(1, 7)},
            "vic": self._vic_stable,
            "air": self._air_stable,
        }

    # ----------------------- interne -----------------------

    def _run(self) -> None:
        # init states
        now = time.monotonic()
        self._init_states(now)

        while not self._stop.is_set():
            t = time.monotonic()
            self._poll_once(t)
            time.sleep(self.poll_period_s)

    def _init_states(self, t: float) -> None:
        # boutons
        b = self.mcp.read_port("mcp1", "B")
        for i in range(1, 7):
            bit = i - 1  # B0..B5
            raw = 1 if (b & (1 << bit)) else 0
            pressed = self._apply_active_low(raw, self.active_low_buttons)
            self._btn_raw[i] = pressed
            self._btn_stable[i] = pressed
            self._btn_last_change[i] = t

        # sélecteurs
        vic = self._read_vic_position()
        air = self._read_air_position()
        self._vic_raw = vic
        self._vic_stable = vic
        self._vic_last_change = t

        self._air_raw = air
        self._air_stable = air
        self._air_last_change = t

    @staticmethod
    def _apply_active_low(level: int, active_low: bool) -> int:
        # level=1 => "haut", level=0 => "bas"
        # pressed = 1 si actif, sinon 0
        if active_low:
            return 1 if level == 0 else 0
        return 1 if level == 1 else 0

    def _poll_once(self, t: float) -> None:
        # --- boutons programmes ---
        b = self.mcp.read_port("mcp1", "B")
        for i in range(1, 7):
            bit = i - 1
            level = 1 if (b & (1 << bit)) else 0
            pressed = self._apply_active_low(level, self.active_low_buttons)
            self._debounce_button(i, pressed, t)

        # --- VIC ---
        vic = self._read_vic_position()
        self._debounce_selector("vic", vic, t)

        # --- AIR ---
        air = self._read_air_position()
        self._debounce_selector("air", air, t)

    def _debounce_button(self, prog_index: int, pressed: int, t: float) -> None:
        raw_prev = self._btn_raw.get(prog_index, 0)
        if pressed != raw_prev:
            self._btn_raw[prog_index] = pressed
            self._btn_last_change[prog_index] = t

        stable = self._btn_stable.get(prog_index, 0)
        last_change = self._btn_last_change.get(prog_index, t)

        if (t - last_change) >= self.debounce_s and stable != self._btn_raw[prog_index]:
            new_stable = self._btn_raw[prog_index]
            self._btn_stable[prog_index] = new_stable

            # événement sur front montant (pression)
            if new_stable == 1:
                self._q.put(InputEvent("btn_prog_pressed", prog_index, t))

    def _debounce_selector(self, which: str, position: object, t: float) -> None:
        if which == "vic":
            raw_prev = self._vic_raw
            if position != raw_prev:
                self._vic_raw = position
                self._vic_last_change = t

            if (t - self._vic_last_change) >= self.debounce_s and self._vic_stable != self._vic_raw:
                self._vic_stable = self._vic_raw
                self._q.put(InputEvent("vic_changed", self._vic_stable, t))
            return

        if which == "air":
            raw_prev = self._air_raw
            if position != raw_prev:
                self._air_raw = position
                self._air_last_change = t

            if (t - self._air_last_change) >= self.debounce_s and self._air_stable != self._air_raw:
                self._air_stable = self._air_raw
                self._q.put(InputEvent("air_changed", self._air_stable, t))
            return

    def _read_vic_position(self) -> object:
        """
        Retourne:
          - 1..5 si une seule position active
          - None si aucune
          - "invalid" si plusieurs actives
        """
        port_b = self.mcp.read_port("mcp2", "B")
        actives: List[int] = []
        for pos in range(1, 6):  # VIC1..VIC5 = B0..B4
            bit = pos - 1
            level = 1 if (port_b & (1 << bit)) else 0
            active = self._apply_active_low(level, self.active_low_selectors)
            if active:
                actives.append(pos)

        if len(actives) == 0:
            return None
        if len(actives) == 1:
            return actives[0]
        return "invalid"

    def _read_air_position(self) -> object:
        """
        Mapping AIR selon ton info:
          MCP2 port A bits 4..7 = AIR4..AIR1 (actif bas)

        Retourne:
          - 1..4 si une seule position active (AIR1..AIR4)
          - None si aucune
          - "invalid" si plusieurs actives
        """
        port_a = self.mcp.read_port("mcp2", "A")
        actives: List[int] = []

        # bit 7 -> AIR1, bit 6 -> AIR2, bit 5 -> AIR3, bit 4 -> AIR4
        mapping: List[Tuple[int, int]] = [(7, 1), (6, 2), (5, 3), (4, 4)]
        for bit, air_pos in mapping:
            level = 1 if (port_a & (1 << bit)) else 0
            active = self._apply_active_low(level, self.active_low_selectors)
            if active:
                actives.append(air_pos)

        if len(actives) == 0:
            return None
        if len(actives) == 1:
            return actives[0]
        return "invalid"
