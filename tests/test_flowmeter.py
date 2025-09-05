#!/usr/bin/python3
import RPi.GPIO as GPIO
import time
from time import monotonic
import threading

FLOW_SENSOR = 26
pulse_count = 0
last_pulse_count = 0
last_ts = monotonic()
volume_total_l = 0.0

_lock = threading.Lock()

def countPulse(channel):
    global pulse_count
    with _lock:
        pulse_count += 1

def read_flow(interval_s=1.0):
    """Calcule débit (L/min) et volume (L) sur l'intervalle écoulé."""
    global last_ts, last_pulse_count, pulse_count, volume_total_l
    now = monotonic()
    dt = now - last_ts
    if dt <= 0:
        return 0.0, 0.0, 0.0

    with _lock:
        pulses = pulse_count - last_pulse_count
        last_pulse_count = pulse_count

    freq = pulses / dt            # Hz
    flow_l_min = freq / 0.2       # L/min (datasheet)
    vol_l = flow_l_min * (dt/60)  # L
    volume_total_l += vol_l
    last_ts = now
    return flow_l_min, vol_l, dt

if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(FLOW_SENSOR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(FLOW_SENSOR, GPIO.FALLING, callback=countPulse)
    try:
        print("[TEST] Débitmètre : 1s d’intervalle (Ctrl+C pour quitter)")
        while True:
            time.sleep(1.0)
            q, v, dt = read_flow()
            print(f"{dt:4.1f}s | {q:7.3f} L/min | +{v:6.3f} L | total={volume_total_l:7.3f} L")
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
