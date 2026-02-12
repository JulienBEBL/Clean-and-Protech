#!/usr/bin/env python3
# --------------------------------------
# libs/relays_critical_lgpio.py
# Relais critiques (AIR + POMPE) via lgpio
#
# API identique à ta version RPi.GPIO:
#   - air(duration_s): pulse si duration_s>0, sinon ON continu si None
#   - pump(duration_s): pulse (typiquement 0.5s)
#   - air_on(), air_off(), pump_off(), all_off(), cleanup()
# --------------------------------------

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

import lgpio


@dataclass(frozen=True)
class CriticalRelaysConfig:
    pin_air: int = 16
    pin_pump: int = 20
    active_high_air: bool = True
    active_high_pump: bool = True
    chip: int = 0  # gpiochip index


class CriticalRelays:
    """
    Version lgpio.
    - Ouvre son propre handle gpiochip par défaut.
    - Tu peux partager un handle si besoin (en passant gpiochip_handle=...).
    """

    def __init__(
        self,
        pin_air: int = 16,
        pin_pump: int = 20,
        active_high_air: bool = True,
        active_high_pump: bool = True,
        chip: int = 0,
        gpiochip_handle: Optional[int] = None,
    ):
        self.pin_air = int(pin_air)
        self.pin_pump = int(pin_pump)

        self._air_on_level = 1 if active_high_air else 0
        self._air_off_level = 0 if active_high_air else 1

        self._pump_on_level = 1 if active_high_pump else 0
        self._pump_off_level = 0 if active_high_pump else 1

        self._air_timer: Optional[threading.Timer] = None
        self._pump_timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()

        self._own_handle = gpiochip_handle is None
        self.h = gpiochip_handle if gpiochip_handle is not None else lgpio.gpiochip_open(int(chip))

        # claim outputs + init OFF
        lgpio.gpio_claim_output(self.h, self.pin_air, self._air_off_level)
        lgpio.gpio_claim_output(self.h, self.pin_pump, self._pump_off_level)

    # --------------------
    # API utilisateur
    # --------------------

    def air(self, duration_s: float | None) -> None:
        """
        Ouvre le relais AIR.
        - duration_s = None : ON continu (jusqu'à air_off())
        - duration_s > 0    : pulse puis OFF auto
        """
        with self._lock:
            self._cancel_air_timer()
            lgpio.gpio_write(self.h, self.pin_air, self._air_on_level)

            if duration_s is None:
                return

            d = float(duration_s)
            if d <= 0:
                self.air_off()
                return

            t = threading.Timer(d, self.air_off)
            t.daemon = True
            self._air_timer = t
            t.start()

    def pump(self, duration_s: float) -> None:
        """
        Ouvre le relais POMPE (ton relais "STOP variateur").
        duration_s typique: 0.5 (500ms)
        """
        with self._lock:
            self._cancel_pump_timer()
            lgpio.gpio_write(self.h, self.pin_pump, self._pump_on_level)

            d = float(duration_s)
            if d <= 0:
                self.pump_off()
                return

            t = threading.Timer(d, self.pump_off)
            t.daemon = True
            self._pump_timer = t
            t.start()

    def air_on(self) -> None:
        with self._lock:
            self._cancel_air_timer()
            lgpio.gpio_write(self.h, self.pin_air, self._air_on_level)

    def air_off(self) -> None:
        with self._lock:
            self._cancel_air_timer()
            lgpio.gpio_write(self.h, self.pin_air, self._air_off_level)

    def pump_off(self) -> None:
        with self._lock:
            self._cancel_pump_timer()
            lgpio.gpio_write(self.h, self.pin_pump, self._pump_off_level)

    def all_off(self) -> None:
        self.air_off()
        self.pump_off()

    def cleanup(self) -> None:
        # Pas de cleanup global destructif (contrairement à RPi.GPIO).
        try:
            self.all_off()
        finally:
            if self._own_handle:
                try:
                    lgpio.gpiochip_close(self.h)
                except Exception:
                    pass

    # --------------------
    # Internes
    # --------------------

    def _cancel_air_timer(self) -> None:
        if self._air_timer is not None:
            try:
                self._air_timer.cancel()
            finally:
                self._air_timer = None

    def _cancel_pump_timer(self) -> None:
        if self._pump_timer is not None:
            try:
                self._pump_timer.cancel()
            finally:
                self._pump_timer = None
