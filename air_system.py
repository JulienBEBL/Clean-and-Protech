from time import monotonic
from drivers.gpio import GPIOController
from drivers.shift_register import ShiftRegister
from config.settings import AIR_RELAY_PIN, AIR_MODES

class AirSystemController:
    def __init__(self, gpio_controller: GPIOController, shift_register: ShiftRegister):
        self.gpio = gpio_controller
        self.shift_register = shift_register
        self.relay_pin = AIR_RELAY_PIN
        self.mode = 0
        self.frozen = False
        self.ev_on = False
        self.next_toggle = 0.0
        self.prev_mode = None
        self.last_button_state = 0
        
        # Setup relay pin
        self.gpio.setup_outputs([self.relay_pin])
        self.gpio.output(self.relay_pin, False)
        
    def set_mode(self, mode: int):
        self.mode = mode
        self._update_leds()
        
    def _update_leds(self):
        new_led = (1 << self.mode)
        self.shift_register.update(new_led_mask=new_led)
        
    def set_electrovalve(self, state: bool):
        self.gpio.output(self.relay_pin, state)
        self.ev_on = state
        
    def update_from_button(self, button_state: int):
        if button_state == 1 and self.last_button_state == 0:
            self.mode = (self.mode + 1) % len(AIR_MODES)
            self._update_leds()
        self.last_button_state = button_state
        
    def tick(self, current_time: float):
        # Implementation of non-blocking air control
        # ... (code from original air_tick_non_blocking function)
        pass
        
    def freeze(self, enable: bool):
        self.frozen = enable
        if enable and self.ev_on:
            self.set_electrovalve(False)
