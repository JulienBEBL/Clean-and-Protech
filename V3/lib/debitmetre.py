"""
debitmetre.py — Débitmètre impulsionnel sur GPIO via lgpio (Raspberry Pi 5)

- Mesure débit instantané (L/min) via fenêtre glissante.
- Mesure volume total (L) depuis reset / mise sous tension.

Hypothèse câblage (classique):
- Sortie type NPN/open-collector + pull-up => repos HIGH, impulsions LOW
- Comptage sur FRONT DESCENDANT (FALLING_EDGE)

Calibration:
- K = pulses_per_liter (impulsions par litre)
  liters = pulses / K

Robustesse:
- Filtrage anti-parasites (debounce) si supporté par lgpio
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, Optional

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio is required. Install python3-lgpio on Raspberry Pi OS.") from e


class FlowMeterError(Exception):
    pass


class FlowMeterNotInitializedError(FlowMeterError):
    pass


@dataclass(frozen=True)
class FlowMeterConfig:
    gpiochip_index: int = 0          # /dev/gpiochip0
    gpio: int = 21                   # BCM 21
    pulses_per_liter: float = 450.0  # K (à calibrer)
    edge: int = lgpio.FALLING_EDGE   # impulsion LOW
    filter_us: int = 1000            # anti-rebond/parasites (µs). 0 = désactivé
    window_s_default: float = 1.0    # fenêtre débit instantané


class FlowMeter:
    """
    Débitmètre impulsionnel via callback lgpio.

    API:
      - flow_lpm(window_s=None) -> float
      - total_liters() -> float
      - total_pulses() -> int
      - reset_total()
    """

    def __init__(self, config: FlowMeterConfig = FlowMeterConfig()):
        if config.pulses_per_liter <= 0:
            raise ValueError("pulses_per_liter must be > 0")
        if config.window_s_default <= 0:
            raise ValueError("window_s_default must be > 0")
        if config.filter_us < 0:
            raise ValueError("filter_us must be >= 0")

        self.config = config
        self._chip: Optional[int] = None
        self._cb = None  # lgpio callback object

        self._lock = Lock()
        self._pulse_count_total: int = 0
        self._pulse_times: Deque[float] = deque()  # monotonic timestamps (seconds)

    # -----------------
    # lifecycle
    # -----------------
    def open(self) -> None:
        if self._chip is not None:
            return

        try:
            chip = lgpio.gpiochip_open(self.config.gpiochip_index)

            # configure input + edge detection
            lgpio.gpio_claim_alert(chip, self.config.gpio, self.config.edge)

            # Filtrage (selon API dispo)
            if self.config.filter_us > 0:
                self._apply_filter(chip, self.config.gpio, self.config.filter_us)

            # callback
            self._cb = lgpio.callback(chip, self.config.gpio, self.config.edge, self._on_edge)
            self._chip = chip

        except Exception as e:
            # cleanup best-effort
            try:
                if self._cb is not None:
                    self._cb.cancel()
            except Exception:
                pass
            try:
                if self._chip is not None:
                    lgpio.gpiochip_close(self._chip)
            except Exception:
                pass
            self._cb = None
            self._chip = None
            raise FlowMeterError(f"Failed to open FlowMeter on gpio={self.config.gpio}: {e}") from e

    def close(self) -> None:
        if self._chip is None:
            return
        try:
            if self._cb is not None:
                self._cb.cancel()
                self._cb = None
        finally:
            lgpio.gpiochip_close(self._chip)
            self._chip = None

    def __enter__(self) -> "FlowMeter":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise FlowMeterNotInitializedError("FlowMeter not initialized. Call open() first.")
        return self._chip

    # -----------------
    # filter helper (portable)
    # -----------------
    @staticmethod
    def _apply_filter(chip: int, gpio: int, filter_us: int) -> None:
        """
        Applique un filtre anti-glitch/anti-rebond si l'API le permet.

        Selon versions lgpio, la fonction s'appelle souvent gpio_set_debounce().
        """
        if hasattr(lgpio, "gpio_set_debounce"):
            lgpio.gpio_set_debounce(chip, gpio, int(filter_us))
            return

        # Anciennes docs parlent parfois de glitch_filter ; si absent, on ignore.
        if hasattr(lgpio, "gpio_set_glitch_filter"):
            lgpio.gpio_set_glitch_filter(chip, gpio, int(filter_us))  # pragma: no cover
            return

        # Sinon: pas supporté, on ne plante pas.
        return

    # -----------------
    # callback
    # -----------------
    def _on_edge(self, chip: int, gpio: int, level: int, tick: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._pulse_count_total += 1
            self._pulse_times.append(now)

            # purge pour limiter la mémoire (2x fenêtre par défaut)
            cutoff = now - (self.config.window_s_default * 2.0)
            while self._pulse_times and self._pulse_times[0] < cutoff:
                self._pulse_times.popleft()

    # -----------------
    # public API
    # -----------------
    def reset_total(self) -> None:
        with self._lock:
            self._pulse_count_total = 0
            self._pulse_times.clear()

    def total_pulses(self) -> int:
        with self._lock:
            return int(self._pulse_count_total)

    def total_liters(self) -> float:
        with self._lock:
            pulses = self._pulse_count_total
        return float(pulses) / float(self.config.pulses_per_liter)

    def flow_lpm(self, window_s: Optional[float] = None) -> float:
        self._require_open()

        w = self.config.window_s_default if window_s is None else float(window_s)
        if w <= 0:
            raise ValueError("window_s must be > 0")

        now = time.monotonic()
        cutoff = now - w

        with self._lock:
            while self._pulse_times and self._pulse_times[0] < cutoff:
                self._pulse_times.popleft()
            pulses_in_window = len(self._pulse_times)

        liters_per_s = (float(pulses_in_window) / float(self.config.pulses_per_liter)) / w
        return liters_per_s * 60.0