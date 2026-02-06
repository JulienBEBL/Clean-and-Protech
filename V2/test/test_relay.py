#!/usr/bin/env python3

import RPi.GPIO as GPIO
import time

RELAY_AIR = 16     # GPIO16 BCM
RELAY_POMPE = 20   # GPIO20 BCM

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_AIR, GPIO.OUT)
GPIO.setup(RELAY_POMPE, GPIO.OUT)

# Adapte si tes relais sont actifs à l'état bas
RELAY_ON = GPIO.HIGH
RELAY_OFF = GPIO.LOW

def all_off():
    GPIO.output(RELAY_AIR, RELAY_OFF)
    GPIO.output(RELAY_POMPE, RELAY_OFF)

try:
    all_off()
    time.sleep(1)

    print("Test 1 : AIR seul")
    GPIO.output(RELAY_AIR, RELAY_ON)
    time.sleep(2)
    all_off()
    time.sleep(1)

    print("Test 2 : POMPE seule")
    GPIO.output(RELAY_POMPE, RELAY_ON)
    time.sleep(2)
    all_off()
    time.sleep(1)

    print("Test 3 : AIR + POMPE")
    GPIO.output(RELAY_AIR, RELAY_ON)
    GPIO.output(RELAY_POMPE, RELAY_ON)
    time.sleep(3)
    all_off()
    time.sleep(1)

    print("Test 4 : Séquence alternée")
    for i in range(5):
        print(f"Cycle {i+1} : AIR")
        GPIO.output(RELAY_AIR, RELAY_ON)
        time.sleep(0.8)
        all_off()
        time.sleep(0.3)

        print(f"Cycle {i+1} : POMPE")
        GPIO.output(RELAY_POMPE, RELAY_ON)
        time.sleep(0.8)
        all_off()
        time.sleep(0.3)

finally:
    all_off()
    GPIO.cleanup()
