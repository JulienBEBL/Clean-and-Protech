from time import monotonic
from drivers.flow_sensor import FlowSensor
from config.settings import FLOW_LOG_EVERY_S, FLOW_LOG_DELTA_FRAC

class FlowMeterController:
    def __init__(self, flow_sensor: FlowSensor):
        self.sensor = flow_sensor
        self.total_volume = 0.0
        self.last_debit_time = monotonic()
        self.last_log_time = 0.0
        self.last_flow_rate = None
        self.instant_flow_rate = 0.0
        
    def calculate_flow(self):
        current_time = monotonic()
        interval = current_time - self.last_debit_time
        
        if interval <= 0:
            return 0.0, 0.0, 0.0
            
        pulses = self.sensor.get_pulse_delta()
        frequency = pulses / interval
        flow_rate = frequency / 0.2  # Formula to be refined later
        volume = flow_rate * (interval / 60)
        
        self.total_volume += volume
        self.last_debit_time = current_time
        self.instant_flow_rate = flow_rate
        
        # Throttled logging
        should_log = False
        if (current_time - self.last_log_time) >= FLOW_LOG_EVERY_S:
            should_log = True
        elif self.last_flow_rate is None:
            should_log = True
        else:
            prev = self.last_flow_rate
            if prev == 0.0:
                if flow_rate > 0.0:
                    should_log = True
            else:
                if abs(flow_rate - prev) / abs(prev) >= FLOW_LOG_DELTA_FRAC:
                    should_log = True
                    
        if should_log:
            self.last_log_time = current_time
            self.last_flow_rate = flow_rate
            
        return volume, flow_rate, interval
        
    def reset_total_volume(self):
        self.total_volume = 0.0
        
    def get_total_volume(self):
        return self.total_volume
        
    def get_instant_flow_rate(self):
        return self.instant_flow_rate
