#!/usr/bin/env python3
import pigpio
import time
import sys

pi = pigpio.pi()
if not pi.connected:
    sys.exit("pigpio daemon non accessible")

RELAY_PIN = 21  # BCM

pi.set_mode(RELAY_PIN, pigpio.OUTPUT)
pi.write(RELAY_PIN, 0)  # s’assure qu’on démarre relais OFF

def relay_on():
    pi.write(RELAY_PIN, 1)

def relay_off():
    pi.write(RELAY_PIN, 0)

try:
    print("Relais ON pour 2 secondes")
    relay_on()
    time.sleep(2)
    print("Relais OFF")
    relay_off()
    time.sleep(1)
    # boucle de test
    for i in range(3):
        relay_on()
        time.sleep(0.5)
        relay_off()
        time.sleep(0.5)
finally:
    pi.write(RELAY_PIN, 0)
    pi.stop()
