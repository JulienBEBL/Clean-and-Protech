# devices/buzzer.py
# -*- coding: utf-8 -*-

import time
import math
import lgpio

_gpio = None
_pin = None


def init(gpio_chip, pin: int):
    global _gpio, _pin
    _gpio = gpio_chip
    _pin = int(pin)

    lgpio.gpio_claim_output(_gpio.handle, _pin, 0)


def beep(duration_ms: int = 100, frequency: int = 2000):
    lgpio.tx_pwm(_gpio.handle, _pin, frequency, 50)
    time.sleep(duration_ms / 1000)
    lgpio.tx_pwm(_gpio.handle, _pin, 0, 0)


def sweep(duration_ms: int = 800, f0: int = 500, f1: int = 3000):
    steps = 40
    step_time = duration_ms / steps / 1000
    for i in range(steps):
        f = int(f0 + (f1 - f0) * (i / steps))
        lgpio.tx_pwm(_gpio.handle, _pin, f, 50)
        time.sleep(step_time)
    lgpio.tx_pwm(_gpio.handle, _pin, 0, 0)
