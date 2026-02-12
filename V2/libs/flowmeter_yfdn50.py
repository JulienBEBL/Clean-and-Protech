#!/usr/bin/env python3
# --------------------------------------
# libs/flowmeter_yfdn50_lgpio.py
# Débitmètre YF-DN50-S (Hall) via lgpio
#
# API identique à ta version RPi.GPIO:
#  - start(), stop(), cleanup()
#  - get_flow_l_min(), get_total_liters(), get_total_pulses(), reset_total()
#
# Implémentation:
#  - Si callbacks lgpio dispo -> interruptions
#  - Sinon fallback polling léger (1 kHz par défaut)
# --------------------------------------

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional

import lgpio


@dataclass(frozen=True)
class FlowMeterConfig:
    gpio_bcm: int = 21
    pulses_per_liter: float = 12.0
    sample_period_s: float = 1.0
    bouncetime_ms: int = 2          # anti-rebond minimal
    edge: str = "FALLING"           # "FALLING" / "RISING" / "BOTH"
    chip: int = 0
    poll_hz_fallback: int = 1000    # utilisé seulement si callbacks indisponibles


class FlowMeterYFDN50:
    def __init__(self, cfg: FlowMeterConfig = FlowMeterConfig(), gpiochip_handle: Optional[int] = None):
        self.cfg = cfg

        self._lock = threading.RLock()
        self._running = False

        self._pulse_total = 0
        self._pulse_since = 0

        self._flow_l_min = 0.0
        self._last_update_t = time.monotonic()

        self._thread: Optional[threading.Thread] = None
        self._cb = None  # callback handle si utilisé

        self._own_handle = gpiochip_handle is None
        self.h = gpiochip_handle if gpiochip_handle is not None else lgpio.gpiochip_open(int(cfg.chip))

        # état pour anti-rebond simple
        self._last_pulse_ns = 0

    # -----------------
    # Lifecycle
    # -----------------
    def start(self) -> None:
        with self._lock:
            if self._running:
                return

            # input
            lgpio.gpio_claim_input(self.h, int(self.cfg.gpio_bcm))

            self._pulse_total = 0
            self._pulse_since = 0
            self._flow_l_min = 0.0
            self._last_update_t = time.monotonic()
            self._last_pulse_ns = 0

            self._running = True

            # Essaye mode callback/alert si disponible, sinon fallback polling
            if hasattr(lgpio, "callback"):
                self._start_callback_mode()
            else:
                self._start_polling_mode()

            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False

        # stop callback/polling
        try:
            if self._cb is not None and hasattr(self._cb, "cancel"):
                self._cb.cancel()
        except Exception:
            pass
        self._cb = None

        th = self._thread
        if th is not None:
            th.join(timeout=1.0)

    def cleanup(self) -> None:
        self.stop()
        if self._own_handle:
            try:
                lgpio.gpiochip_close(self.h)
            except Exception:
                pass

    # -----------------
    # API lecture
    # -----------------
    def get_flow_l_min(self) -> float:
        with self._lock:
            return float(self._flow_l_min)

    def get_total_liters(self) -> float:
        with self._lock:
            return self._pulse_total / self.cfg.pulses_per_liter

    def get_total_pulses(self) -> int:
        with self._lock:
            return int(self._pulse_total)

    def reset_total(self) -> None:
        with self._lock:
            self._pulse_total = 0
            self._pulse_since = 0
            self._flow_l_min = 0.0
            self._last_update_t = time.monotonic()
            self._last_pulse_ns = 0

    # -----------------
    # Internals
    # -----------------
    def _edge_const(self) -> int:
        # Constantes lgpio: on reste défensif
        e = str(self.cfg.edge).upper()
        if hasattr(lgpio, "FALLING_EDGE") and hasattr(lgpio, "RISING_EDGE") and hasattr(lgpio, "BOTH_EDGES"):
            if e == "FALLING":
                return lgpio.FALLING_EDGE
            if e == "RISING":
                return lgpio.RISING_EDGE
            return lgpio.BOTH_EDGES

        # fallback (valeurs courantes)
        if e == "FALLING":
            return 2
        if e == "RISING":
            return 1
        return 3

    def _start_callback_mode(self) -> None:
        """
        Utilise lgpio.callback(handle, gpio, edge, func) si dispo.
        """
        edge = self._edge_const()

        def _cb_fn(chip, gpio, level, tick):
            # tick: dépend de lgpio; on ignore et on fait notre anti-rebond monotonic_ns
            self._on_pulse(level)

        self._cb = lgpio.callback(self.h, int(self.cfg.gpio_bcm), edge, _cb_fn)

    def _start_polling_mode(self) -> None:
        """
        Fallback si callbacks indisponibles: polling léger.
        """
        period_s = 1.0 / max(10, int(self.cfg.poll_hz_fallback))
        edge = str(self.cfg.edge).upper()
        gpio = int(self.cfg.gpio_bcm)

        def poll_loop():
            last_level = lgpio.gpio_read(self.h, gpio)
            while True:
                with self._lock:
                    if not self._running:
                        return
                time.sleep(period_s)
                level = lgpio.gpio_read(self.h, gpio)
                if level == last_level:
                    continue

                # transition détectée
                if edge == "FALLING" and (last_level == 1 and level == 0):
                    self._on_pulse(level)
                elif edge == "RISING" and (last_level == 0 and level == 1):
                    self._on_pulse(level)
                elif edge == "BOTH":
                    self._on_pulse(level)

                last_level = level

        t = threading.Thread(target=poll_loop, daemon=True)
        t.start()
        self._cb = t  # juste pour garder une référence

    def _on_pulse(self, _level: int) -> None:
        # anti-rebond minimal (bouncetime_ms)
        now_ns = time.monotonic_ns()
        min_dt_ns = int(self.cfg.bouncetime_ms * 1_000_000)
        with self._lock:
            if not self._running:
                return
            if (now_ns - self._last_pulse_ns) < min_dt_ns:
                return
            self._last_pulse_ns = now_ns
            self._pulse_total += 1
            self._pulse_since += 1

    def _worker(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    return
                period = float(self.cfg.sample_period_s)

            time.sleep(period)

            now = time.monotonic()
            with self._lock:
                dt = now - self._last_update_t
                pulses = self._pulse_since
                self._pulse_since = 0
                self._last_update_t = now

                if dt <= 0 or self.cfg.pulses_per_liter <= 0:
                    self._flow_l_min = 0.0
                else:
                    liters = pulses / self.cfg.pulses_per_liter
                    l_per_s = liters / dt
                    self._flow_l_min = l_per_s * 60.0
