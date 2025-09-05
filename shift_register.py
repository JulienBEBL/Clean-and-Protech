from drivers.gpio import GPIOController
from config.settings import SHIFT_REGISTER_PINS

class ShiftRegister:
    def __init__(self, gpio_controller: GPIOController):
        self.gpio = gpio_controller
        self.data_pin, self.latch_pin, self.clock_pin = SHIFT_REGISTER_PINS
        self.dir_mask = 0x00
        self.led_mask = 0x01
        
        # Setup pins
        self.gpio.setup_outputs([self.data_pin, self.latch_pin, self.clock_pin])
        
    def update(self, new_dir_mask=None, new_led_mask=None):
        if new_dir_mask is not None:
            self.dir_mask = new_dir_mask & 0xFF
        if new_led_mask is not None:
            self.led_mask = new_led_mask & 0x0F
            
        word = (self.dir_mask << 8) | (self.led_mask << 4)
        
        # Latch low during shift
        self.gpio.output(self.latch_pin, False)
        
        # Shift MSB first
        for i in range(15, -1, -1):
            bit = (word >> i) & 1
            self.gpio.output(self.clock_pin, False)
            self.gpio.output(self.data_pin, bool(bit))
            self.gpio.output(self.clock_pin, True)
            
        # Latch high to update outputs
        self.gpio.output(self.latch_pin, True)
        
    def set_direction(self, motor_index: int, direction: int):
        bit = 1 << motor_index
        if direction == 0:  # OPEN
            self.dir_mask &= ~bit
        else:  # CLOSE
            self.dir_mask |= bit
        self.update(new_dir_mask=self.dir_mask)
