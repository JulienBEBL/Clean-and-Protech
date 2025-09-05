from enum import IntEnum
from dataclasses import dataclass
from typing import Dict, List, Tuple

# GPIO Pins
GPIO_MODE = 'BCM'

# Motor pins
MOTOR_PINS = {
    "V4V": 19, "clientG": 18, "clientD": 15, "egout": 14,
    "boue": 13, "pompeOUT": 12, "cuve": 6, "eau": 5
}

MOTOR_BIT_INDEX = { 
    "V4V": 0, "clientG": 1, "clientD": 2, "egout": 3,
    "boue": 4, "pompeOUT": 5, "cuve": 6, "eau": 7 
}

# Shift register pins
SHIFT_REGISTER_PINS = (21, 20, 16)  # DATA, LATCH, CLOCK

# Air system
AIR_RELAY_PIN = 23
FLOW_SENSOR_PIN = 26

# MCP3008 thresholds
MCP_THRESHOLD = 1000

# Timings
WAIT_DELAY = 0.001
STEP_DELAY = 0.001
MAZ_DELAY = 0.002

# Steps
STEP_MAZ = 800
STEP_MICRO_MAZ = 20
STEP_MOVE = 800

# Program duration
PROGRAM_DURATION_SEC = 5 * 60

# V4V positions
V4V_POS_STEPS = [0, 160, 320, 480, 640, 800]

# Air modes
@dataclass
class AirMode:
    label: str
    pulse_s: float
    period_s: float

AIR_MODES = [
    AirMode("OFF", 0.0, 0.0),
    AirMode("2s", 2.0, 2.0),
    AirMode("4s", 2.0, 4.0),
    AirMode("CONTINU", 0.0, 0.0),
]

# Flow meter
FLOW_LOG_EVERY_S = 2.0
FLOW_LOG_DELTA_FRAC = 0.05

# Display
DISPLAY_PERIOD_S = 1.0

# Directions
class Direction(IntEnum):
    OPEN = 0
    CLOSE = 1
