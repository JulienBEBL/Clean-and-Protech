#!/usr/bin/env python3
import pigpio
import time

pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("pigpio daemon inaccessible")

BUZZER_PIN = 16  # ou autre GPIO BCM

pi.set_mode(BUZZER_PIN, pigpio.OUTPUT)

# fonction pour buzzer court
def buzz(duration_s=0.2):
    pi.write(BUZZER_PIN, 1)
    time.sleep(duration_s)
    pi.write(BUZZER_PIN, 0)

try:
    for i in range(5):
        buzz(0.1)
        time.sleep(0.2)
finally:
    pi.write(BUZZER_PIN, 0)
    pi.stop()
