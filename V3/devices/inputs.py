# devices/inputs.py
# -*- coding: utf-8 -*-

import time

_mcp = None
_program_bank = "A"
_selector_bank = "B"
_last_state = 0
_last_time = 0
_debounce_ms = 50


def init(mcp, program_bank="A", selector_bank="B", debounce_ms=50):
    global _mcp, _program_bank, _selector_bank, _debounce_ms
    _mcp = mcp
    _program_bank = program_bank
    _selector_bank = selector_bank
    _debounce_ms = debounce_ms


def read_program_buttons():
    return _read_bank(_program_bank)


def read_selectors():
    return _read_bank(_selector_bank)


def _read_bank(bank):
    global _last_state, _last_time

    now = time.time() * 1000
    state = _mcp.read_gpio(bank)

    if state != _last_state:
        if now - _last_time > _debounce_ms:
            _last_state = state
            _last_time = now
            return state

    return _last_state
