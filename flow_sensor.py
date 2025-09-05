from drivers.gpio import GPIOController
from config.settings import FLOW_SENSOR_PIN

class FlowSensor:
    def __init__(self, gpio_controller: GPIOController):
        self.gpio = gpio_controller
        self.pin = FLOW_SENSOR_PIN
        self.pulse_count = 0
        self.last_pulse_count = 0
        
        # Setup sensor
        self.gpio.setup_input(self.pin)
        self.gpio.add_event_detect(self.pin, GPIO.FALLING, self._count_pulse)
        
    def _count_pulse(self, channel):
        self.pulse_count += 1
        
    def get_pulses(self) -> int:
        return self.pulse_count
        
    def reset(self):
        self.pulse_count = 0
        self.last_pulse_count = 0
        
    def get_pulse_delta(self) -> int:
        delta = self.pulse_count - self.last_pulse_count
        self.last_pulse_count = self.pulse_count
        return delta
