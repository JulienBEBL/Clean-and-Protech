from dataclasses import dataclass
from typing import List, Callable

@dataclass
class IrrigationProgram:
    number: int
    name: str
    valves_to_open: List[str]
    valves_to_close: List[str]
    function: Callable
    
    def execute(self):
        self.function()
