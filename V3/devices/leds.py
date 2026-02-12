# devices/leds.py
# -*- coding: utf-8 -*-

_mcp = None
_bank = "B"


def init(mcp, bank="B"):
    global _mcp, _bank
    _mcp = mcp
    _bank = bank


def set_led(bit: int, state: int):
    _mcp.write_bit(_bank, bit, state)


def set_mask(mask: int):
    _mcp.write_gpio(_bank, mask)
