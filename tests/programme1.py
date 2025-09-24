#!/usr/bin/python3
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
import time
import sys
import os

STEPS       = 1200         # nombre de pas par mouvement
STEP_DELAY  = 0.002       # secondes entre niveaux (1 kHz approx)
DIR_CLOSE   = 1           # sens "fermeture" (à inverser si besoin)
DIR_OPEN    = 0           # sens "ouverture" (à inverser si besoin)

dataPIN  = 21   # DS
latchPIN = 20   # ST_CP / Latch
clockPIN = 16   # SH_CP / Clock

bits_dir   = [0]*8
bits_blank = [0]*4
bits_leds  = [0]*4

def _bits_to_str(bits16):
    if len(bits16) != 16:
        raise ValueError(f"Expected 16 bits, got {len(bits16)}")
    return "".join("1" if int(b) else "0" for b in bits16)

def shift_update(input_str, data, clock, latch):
    """Envoie une chaîne 16 bits MSB-first vers 2x 74HC595 en cascade."""
    GPIO.output(clock, 0)
    GPIO.output(latch, 0)
    GPIO.output(clock, 1)

    for i in range(15, -1, -1):
        GPIO.output(clock, 0)
        GPIO.output(data, int(input_str[i]))
        GPIO.output(clock, 1)

    GPIO.output(clock, 0)
    GPIO.output(latch, 1)
    GPIO.output(clock, 1)

def push_shift():
    """Applique l'état des 16 bits sur les 595."""
    s = _bits_to_str(bits_dir + bits_blank + bits_leds)
    shift_update(s, dataPIN, clockPIN, latchPIN)

def set_all_leds(val):
    for i in range(4):
        bits_leds[i] = 1 if val else 0
    push_shift()

def clear_all_shift():
    for i in range(8): bits_dir[i] = 0
    for i in range(4): bits_blank[i] = 0
    for i in range(4): bits_leds[i] = 0
    push_shift()

# =========================
# Moteurs (PUL = GPIO BCM)
# =========================
motor_map = {
    "V4V": 5, "clientG": 27, "clientD": 26, "egout": 22,
    "boue": 13, "pompeOUT": 17, "cuve": 19, "eau": 6
}

def set_all_dir(value):
    bits_dir[:] = [value]*8
    push_shift()

def pulse_steps(pul_pin, steps, delay_s):
    """Génère 'steps' impulsions sur 'pul_pin'."""
    for _ in range(steps):
        GPIO.output(pul_pin, GPIO.HIGH)
        time.sleep(delay_s)
        GPIO.output(pul_pin, GPIO.LOW)
        time.sleep(delay_s)

def move_motor(name, steps, delay_s):
    """Déplace un moteur dans un sens donné."""
    pul = motor_map[name]
    print(f"[MOTOR] {name:8s} | DIR = {bits_dir} | PUL GPIO {pul} | {steps} pas")
    pulse_steps(pul, steps, delay_s)

# =========================
# Main
# =========================

def main():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    # 74HC595
    GPIO.setup((dataPIN, latchPIN, clockPIN), GPIO.OUT, initial=GPIO.LOW)

    # PUL moteurs
    for pin in motor_map.values():
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    try:
        print("=== Programme 1 ===")
        clear_all_shift()
        
        set_all_dir(DIR_CLOSE)
        move_motor("eau", 1200, 0.002)
        move_motor("cuve", 1200, 0.002)
        move_motor("pompeOUT", 1200, 0.002)
        move_motor("egout", 1200, 0.002)
        
        time.sleep(1)
        
        set_all_dir(DIR_OPEN)
        move_motor("clientD", 1200, 0.002)
        move_motor("clientG", 1200, 0.002)
        move_motor("boue", 1200, 0.002)
        

        print("\n[OK] Test terminé.")

    except KeyboardInterrupt:
        print("\n[STOP] Interruption par l'utilisateur.")
    finally:
        clear_all_shift()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
