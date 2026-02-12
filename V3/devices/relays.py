# devices/relays.py
# -*- coding: utf-8 -*-

from hw.gpio import GpioChip, setup_output, write

_gpio = None
_pump_pin = None
_air_pin = None


def init(gpio_chip: GpioChip, pump_pin: int, air_pin: int) -> None:
    global _gpio, _pump_pin, _air_pin
    _gpio = gpio_chip
    _pump_pin = int(pump_pin)
    _air_pin = int(air_pin)

    setup_output(_gpio, _pump_pin, initial=0)
    setup_output(_gpio, _air_pin, initial=0)


def pump_on():
    write(_gpio, _pump_pin, 1)


def pump_off():
    write(_gpio, _pump_pin, 0)


def air_on():
    write(_gpio, _air_pin, 1)


def air_off():
    write(_gpio, _air_pin, 0)


def all_off():
    pump_off()
    air_off()
