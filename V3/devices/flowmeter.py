# devices/flowmeter.py
# -*- coding: utf-8 -*-

import time
from hw.gpio import set_alert

_gpio = None
_pin = None

_pulse_count = 0
_last_tick = 0
_debounce_us = 2000
_pulses_per_liter = 12  # valeur par défaut


def init(gpio_chip, pin: int, pulses_per_liter: int = 12, debounce_us: int = 2000):
    global _gpio, _pin, _pulse_count, _last_tick
    global _pulses_per_liter, _debounce_us

    _gpio = gpio_chip
    _pin = int(pin)
    _pulse_count = 0
    _last_tick = 0
    _pulses_per_liter = pulses_per_liter
    _debounce_us = debounce_us

    set_alert(_gpio, _pin, "falling", _callback, glitch_filter_us=_debounce_us)


def _callback(gpio, level, tick):
    global _pulse_count, _last_tick

    if tick - _last_tick < _debounce_us:
        return

    _last_tick = tick
    _pulse_count += 1


def reset_total():
    global _pulse_count
    _pulse_count = 0


def get_total_liters():
    return _pulse_count / _pulses_per_liter


def get_l_min(window_sec: float = 1.0):
    start = _pulse_count
    time.sleep(window_sec)
    delta = _pulse_count - start
    return (delta / _pulses_per_liter) * (60 / window_sec)
