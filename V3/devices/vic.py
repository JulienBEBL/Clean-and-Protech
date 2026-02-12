# devices/vic.py
# -*- coding: utf-8 -*-

_current_position = 0
_positions = {}
_motor_id = None
_motors = None


def init(motors_module, motor_id: str, positions_steps: dict):
    global _motor_id, _positions, _motors
    _motor_id = motor_id
    _positions = positions_steps
    _motors = motors_module


def goto_position(pos: int):
    global _current_position

    if pos not in _positions:
        raise ValueError("Position VIC invalide")

    target = _positions[pos]
    delta = target - _current_position

    if delta != 0:
        turns = delta / _motors._steps_per_rev
        _motors.open_standard(_motor_id, turns)

    _current_position = target
