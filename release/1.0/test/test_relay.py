#!/usr/bin/python3
import time
import RPi.GPIO as GPIO

RELAY_PIN = 16

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)

try:
    while True:
        print("Relais ON")
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        time.sleep(1)

        print("Relais OFF")
        GPIO.output(RELAY_PIN, GPIO.LOW)
        time.sleep(1)

except KeyboardInterrupt:
    pass

GPIO.cleanup()
print("Test relais terminé.")
