"""
debitmetre.py — Débitmètre impulsionnel sur GPIO via lgpio (Raspberry Pi 5)

Fonctions:
- débit instantané (L/min) basé sur une fenêtre glissante (timestamps d'impulsions)
- volume total (L) depuis reset / mise sous tension

Hypothèse:
- capteur type NPN/open-collector -> ligne au repos HIGH (pull-up),
  impulsions à LOW => on compte sur FRONT DESCENDANT (FALLING).

Calibration:
- K = pulses_per_liter (impulsions par litre). Exemple: K=450 => 450 pulses = 1 L.
  => liters = pulses / K
  => flow_lpm = (pulses_in_window / K) / (window_s / 60)

Robustesse:
- glitch filter lgpio (anti-rebond / parasites) configurable (µs)
- thread-safe via Lock
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
    """Base error for flow meter."""


class FlowMeterNotInitializedError(FlowMeterError):
    """Raised when used before open()."""


@dataclass(frozen=True)
class FlowMeterConfig:
    gpiochip_index: int = 0          # /dev/gpiochip0
    gpio: int = 21                   # BCM 21
    pulses_per_liter: float = 450.0  # K (à calibrer)
    edge: int = lgpio.FALLING_EDGE   # capteur NPN: impulsion LOW
    glitch_filter_us: int = 500      # filtre anti-glitch (µs), à ajuster selon capteur et débit
    window_s_default: float = 1.0    # fenêtre par défaut pour débit instantané


class FlowMeter:
    """
    Débitmètre impulsionnel avec callback lgpio.

    Usage:
        fm = FlowMeter(FlowMeterConfig(pulses_per_liter=450.0))
        fm.open()
        ...
        flow = fm.flow_lpm()      # L/min
        total = fm.total_liters() # L
        fm.close()

    Important:
    - window_s doit être assez grand pour lisser (ex: 1.0 à 2.0 s)
      surtout si le débit est faible (pulses rares).
    """

    def __init__(self, config: FlowMeterConfig = FlowMeterConfig()):
        if config.pulses_per_liter <= 0:
            raise ValueError("pulses_per_liter must be > 0")
        if config.window_s_default <= 0:
            raise ValueError("window_s_default must be > 0")
        if config.glitch_filter_us < 0:
            raise ValueError("glitch_filter_us must be >= 0")

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

            # entrée + alerte
            # NOTE: gpio_claim_alert configure l'input + edge detection côté kernel
            lgpio.gpio_claim_alert(chip, self.config.gpio, self.config.edge)

            if self.config.glitch_filter_us > 0:
                # filtre anti-glitch (microsecondes)
                lgpio.gpio_set_glitch_filter(chip, self.config.gpio, self.config.glitch_filter_us)

            # callback Python
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
            raise FlowMeterError(f"Failed to open flow meter on gpio={self.config.gpio}: {e}") from e

    def close(self) -> None:
        if self._chip is None:
            return

        try:
            if self._cb is not None:
                try:
                    self._cb.cancel()
                finally:
                    self._cb = None
        finally:
            try:
                lgpio.gpiochip_close(self._chip)
            finally:
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
    # callback
    # -----------------
    def _on_edge(self, chip: int, gpio: int, level: int, tick: int) -> None:
        # level: 0/1, tick: timestamp (µs) depending on lgpio; we use monotonic instead for simplicity.
        now = time.monotonic()
        with self._lock:
            self._pulse_count_total += 1
            self._pulse_times.append(now)

            # purge ancien (fenêtre max = 2x fenêtre par défaut pour éviter croissance)
            cutoff = now - (self.config.window_s_default * 2.0)
            while self._pulse_times and self._pulse_times[0] < cutoff:
                self._pulse_times.popleft()

    # -----------------
    # public API
    # -----------------
    def reset_total(self) -> None:
        """Remise à zéro du volume total et de l'historique instantané."""
        with self._lock:
            self._pulse_count_total = 0
            self._pulse_times.clear()

    def total_pulses(self) -> int:
        """Impulsions totales depuis reset / power-on."""
        with self._lock:
            return int(self._pulse_count_total)

    def total_liters(self) -> float:
        """Volume total en litres depuis reset / power-on."""
        with self._lock:
            pulses = self._pulse_count_total
        return float(pulses) / float(self.config.pulses_per_liter)

    def flow_lpm(self, window_s: Optional[float] = None) -> float:
        """
        Débit instantané en L/min via fenêtre glissante.

        window_s:
          - si None => config.window_s_default
          - recommandé: 1.0 à 2.0 s (plus grand si débit faible)
        """
        self._require_open()

        w = self.config.window_s_default if window_s is None else float(window_s)
        if w <= 0:
            raise ValueError("window_s must be > 0")

        now = time.monotonic()
        cutoff = now - w

        with self._lock:
            # purge selon window_s demandé (sans détruire toute la deque)
            while self._pulse_times and self._pulse_times[0] < cutoff:
                self._pulse_times.popleft()

            pulses_in_window = len(self._pulse_times)

        liters_per_s = (float(pulses_in_window) / float(self.config.pulses_per_liter)) / w
        return liters_per_s * 60.0