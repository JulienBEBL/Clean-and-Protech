from dataclasses import dataclass
from typing import Optional

@dataclass
class SystemState:
    program_number: int = 0
    selector_position: int = 0
    air_mode: int = 0
    v4v_position: int = 0
    display_toggle: bool = False
    idle_prompt_shown: bool = False
    last_display_switch: float = 0.0
    air_frozen: bool = False
    last_air_button: int = 0
    program_start_time: Optional[float] = None
