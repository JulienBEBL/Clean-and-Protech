import RPi.GPIO as GPIO
from typing import List, Tuple
from config.settings import GPIO_MODE

class GPIOController:
    def __init__(self):
        GPIO.setmode(getattr(GPIO, GPIO_MODE))
        self._setup_done = False
        
    def setup_outputs(self, pins: List[int]):
        GPIO.setup(pins, GPIO.OUT)
        GPIO.output(pins, GPIO.LOW)
        
    def setup_input(self, pin: int, pull_up_down=GPIO.PUD_UP):
        GPIO.setup(pin, GPIO.IN, pull_up_down=pull_up_down)
        
    def output(self, pin: int, state: bool):
        GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
        
    def output_multiple(self, pins: List[int], states: List[bool]):
        for pin, state in zip(pins, states):
            self.output(pin, state)
            
    def cleanup(self):
        GPIO.cleanup()
        
    def add_event_detect(self, pin: int, edge, callback):
        GPIO.add_event_detect(pin, edge, callback=callback)
