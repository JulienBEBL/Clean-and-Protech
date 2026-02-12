# hw/buzzer.py
from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional, List, Tuple

import lgpio


@dataclass(frozen=True)
class BuzzerConfig:
    gpio_bcm: int = 26
    chip: int = 0
    active_high: bool = True


class Buzzer:
    def __init__(self, cfg: BuzzerConfig, gpiochip_handle: Optional[int] = None):
        self.cfg = cfg
        self._own_handle = gpiochip_handle is None
        self.h = gpiochip_handle if gpiochip_handle is not None else lgpio.gpiochip_open(int(cfg.chip))

        self._on_level = 1 if cfg.active_high else 0
        self._off_level = 0 if cfg.active_high else 1

        lgpio.gpio_claim_output(self.h, int(cfg.gpio_bcm), self._off_level)

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def beep(self, duration_s: float = 0.12, freq_hz: float = 2000.0) -> None:
        """
        Bip bloquant (simple, fiable).
        """
        duration_s = float(duration_s)
        freq_hz = float(freq_hz)
        if duration_s <= 0 or freq_hz <= 0:
            return

        half_period = 0.5 / freq_hz
        t_end = time.monotonic() + duration_s

        with self._lock:
            while time.monotonic() < t_end:
                lgpio.gpio_write(self.h, self.cfg.gpio_bcm, self._on_level)
                time.sleep(half_period)
                lgpio.gpio_write(self.h, self.cfg.gpio_bcm, self._off_level)
                time.sleep(half_period)

            lgpio.gpio_write(self.h, self.cfg.gpio_bcm, self._off_level)

    def pattern(self, seq: List[Tuple[float, float]], pause_s: float = 0.05) -> None:
        """
        seq = [(duration_s, freq_hz), ...]
        """
        for d, f in seq:
            self.beep(d, f)
            time.sleep(pause_s)

    def off(self) -> None:
        with self._lock:
            lgpio.gpio_write(self.h, self.cfg.gpio_bcm, self._off_level)

    def cleanup(self) -> None:
        try:
            self.off()
        finally:
            if self._own_handle:
                try:
                    lgpio.gpiochip_close(self.h)
                except Exception:
                    pass
