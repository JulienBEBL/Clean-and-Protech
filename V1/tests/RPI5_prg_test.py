#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import RPi.GPIO as GPIO

# ===== RPI5 / DM860T GPIO (BCM) =====
# Tu as demandé : PUL DIR ENA sur GPIO 5/6/13
pul = 13   # STEP / PUL
dir = 6    # DIR
ena = 5    # ENA

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

on = GPIO.HIGH
off = GPIO.LOW

GPIO.setup(pul, GPIO.OUT, initial=off)
GPIO.setup(dir, GPIO.OUT, initial=off)
GPIO.setup(ena, GPIO.OUT, initial=off)

# IMPORTANT (reprend ton "enable pulse" RPi4) :
# Ici on fait un petit "toggle" ENA au démarrage.
# Si ton câblage est différent (ENA actif bas/haut), change ENA_ACTIVE_LEVEL.
ENA_ACTIVE_LEVEL = off   # driver ENABLE quand ENA=LOW (très fréquent). Mets 'on' si c'est l'inverse.
ENA_INACTIVE_LEVEL = on if ENA_ACTIVE_LEVEL == off else off

GPIO.output(dir, off)
GPIO.output(pul, off)

# Petit reset / init ENA
GPIO.output(ena, ENA_INACTIVE_LEVEL)
time.sleep(0.001)
GPIO.output(ena, ENA_ACTIVE_LEVEL)
time.sleep(0.001)

def step_pulse(delay_s):
    GPIO.output(pul, on)
    time.sleep(delay_s)
    GPIO.output(pul, off)
    time.sleep(delay_s)

def moveright(steps, speed):
    # Sens "right" = dir=off (comme ton script)
    GPIO.output(dir, off)
    time.sleep(0.001)
    delay_s = 0.001 / int(speed)  # même formule que ton code
    for _ in range(int(steps)):
        step_pulse(delay_s)

def moveleft(steps, speed):
    # Sens "left" = dir=on (comme ton script)
    GPIO.output(dir, on)
    time.sleep(0.001)
    delay_s = 0.001 / int(speed)
    for _ in range(int(steps)):
        step_pulse(delay_s)

try:
    howmany = input("Please enter how many steps: ")
    print("You entered: " + howmany)

    speed = input("Please enter how fast to step (1..500 typ.): ")
    print("You entered: " + speed)

    # Sécurité minimale
    steps = int(howmany)
    spd = int(speed)
    if steps <= 0:
        raise ValueError("steps must be > 0")
    if spd <= 0:
        raise ValueError("speed must be > 0")

    # Run
    moveright(steps, spd)
    time.sleep(0.01)
    moveleft(steps, spd)

finally:
    # Désactive driver et nettoie
    GPIO.output(pul, off)
    GPIO.output(ena, ENA_INACTIVE_LEVEL)
    GPIO.cleanup()
    print("Done.")
