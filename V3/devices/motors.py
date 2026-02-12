# devices/motors.py
# -*- coding: utf-8 -*-

import time
import math
import lgpio

_gpio = None
_mcp = None
_step_pins = {}
_motor_map = {}
_dir_open_level = 1
_dir_inverted = True
_ena_active_low = True
_steps_per_rev = 3200


def init(gpio_chip, mcp3, step_pins: dict, motor_map: dict,
         dir_open_level=1,
         dir_inverted=True,
         ena_active_low=True,
         steps_per_rev=3200):

    global _gpio, _mcp, _step_pins, _motor_map
    global _dir_open_level, _dir_inverted, _ena_active_low, _steps_per_rev

    _gpio = gpio_chip
    _mcp = mcp3
    _step_pins = step_pins
    _motor_map = motor_map
    _dir_open_level = dir_open_level
    _dir_inverted = dir_inverted
    _ena_active_low = ena_active_low
    _steps_per_rev = steps_per_rev

    for pin in _step_pins.values():
        lgpio.gpio_claim_output(_gpio.handle, pin, 0)


def open_standard(motor_id: str, turns: float):
    steps = int(turns * _steps_per_rev)
    _move_with_ramp(motor_id, steps, open_dir=True)


def _move_with_ramp(motor_id, steps, open_dir=True):
    idx = _motor_map[motor_id]
    dir_bit = 7 - idx if _dir_inverted else idx
    ena_bit = idx

    dir_level = _dir_open_level if open_dir else (1 - _dir_open_level)

    _mcp.write_bit("A", dir_bit, dir_level)
    _mcp.write_bit("B", ena_bit, 0 if _ena_active_low else 1)

    pin = _step_pins[motor_id]

    ramp = 200
    for i in range(steps):
        if i < ramp:
            delay = 0.0015 - (i / ramp) * 0.001
        elif i > steps - ramp:
            delay = 0.0015 - ((steps - i) / ramp) * 0.001
        else:
            delay = 0.0005

        lgpio.gpio_write(_gpio.handle, pin, 1)
        time.sleep(delay)
        lgpio.gpio_write(_gpio.handle, pin, 0)
        time.sleep(delay)

    _mcp.write_bit("B", ena_bit, 1 if _ena_active_low else 0)
