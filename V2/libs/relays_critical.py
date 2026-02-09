#!/usr/bin/env python3
# --------------------------------------
# libs/relays_critical.py
# API minimale:
#   - air(duration_s): pulse si duration_s>0, sinon ON continu si duration_s is None
#   - pump(duration_s): pulse (typiquement 0.5s)
#   - air_on(), air_off() : contrôle direct (air uniquement)
# --------------------------------------

import time
import threading
import RPi.GPIO as GPIO


class CriticalRelays:
    def __init__(
        self,
        pin_air: int = 16,
        pin_pump: int = 20,
        active_high_air: bool = True,
        active_high_pump: bool = True,
        i2c_mode: int = GPIO.BCM,
        warnings: bool = False,
    ):
        self.pin_air = pin_air
        self.pin_pump = pin_pump

        self._air_on_level = GPIO.HIGH if active_high_air else GPIO.LOW
        self._air_off_level = GPIO.LOW if active_high_air else GPIO.HIGH

        self._pump_on_level = GPIO.HIGH if active_high_pump else GPIO.LOW
        self._pump_off_level = GPIO.LOW if active_high_pump else GPIO.HIGH

        self._air_timer: threading.Timer | None = None
        self._pump_timer: threading.Timer | None = None
        self._lock = threading.RLock()

        GPIO.setwarnings(warnings)
        GPIO.setmode(i2c_mode)
        GPIO.setup(self.pin_air, GPIO.OUT, initial=self._air_off_level)
        GPIO.setup(self.pin_pump, GPIO.OUT, initial=self._pump_off_level)

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
            GPIO.output(self.pin_air, self._air_on_level)

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
            GPIO.output(self.pin_pump, self._pump_on_level)

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
            GPIO.output(self.pin_air, self._air_on_level)

    def air_off(self) -> None:
        with self._lock:
            self._cancel_air_timer()
            GPIO.output(self.pin_air, self._air_off_level)

    # --------------------
    # Internes / sécurité
    # --------------------

    def pump_off(self) -> None:
        with self._lock:
            self._cancel_pump_timer()
            GPIO.output(self.pin_pump, self._pump_off_level)

    def all_off(self) -> None:
        self.air_off()
        self.pump_off()

    def cleanup(self) -> None:
        try:
            self.all_off()
        finally:
            GPIO.cleanup()

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
