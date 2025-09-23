#!/usr/bin/python3
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
import time

# =========================
# Paramètres généraux
# =========================
STEPS       = 1200         # nombre de pas par mouvement
STEP_DELAY  = 0.002       # secondes entre niveaux (1 kHz approx)
DIR_CLOSE   = 1           # sens "fermeture" (à inverser si besoin)
DIR_OPEN    = 0           # sens "ouverture" (à inverser si besoin)

# =========================
# PINS 74HC595 (BCM)
# =========================
dataPIN  = 21   # DS
latchPIN = 20   # ST_CP / Latch
clockPIN = 16   # SH_CP / Clock

# =========================
# LEDs & DIR via 2 x 74HC595
# Layout (16 bits total) : [bits_dir(8)] + [bits_blank(4)] + [bits_leds(4)]
# =========================
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

def set_leds(lst4):
    """lst4: [L3,L2,L1,L0] (4 LEDs)"""
    if len(lst4) != 4:
        raise ValueError("set_leds attend 4 bits")
    for i in range(4):
        bits_leds[i] = 1 if lst4[i] else 0
    push_shift()

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

# Ordre des bits DIR (Q0..Q7 du 1er 74HC595) -> à ajuster si besoin
DIR_BIT_ORDER = ["V4V", "clientG", "clientD", "egout",
                 "boue", "pompeOUT", "cuve", "eau"]
DIR_INDEX = {name: i for i, name in enumerate(DIR_BIT_ORDER)}

def set_dir(name, value):
    """Fixe le bit DIR du moteur 'name' à 0/1 et pousse sur le 595."""
    idx = DIR_INDEX[name]
    bits_dir[idx] = 1 if value else 0
    push_shift()

def set_all_dir(value):
    v = 1 if value else 0
    for k in DIR_INDEX.values():
        bits_dir[k] = v
    push_shift()

def pulse_steps(pul_pin, steps, delay_s):
    """Génère 'steps' impulsions sur 'pul_pin'."""
    for _ in range(steps):
        GPIO.output(pul_pin, GPIO.HIGH)
        time.sleep(delay_s)
        GPIO.output(pul_pin, GPIO.LOW)
        time.sleep(delay_s)

def move_motor(name, steps, dir_value, delay_s):
    """Déplace un moteur dans un sens donné."""
    pul = motor_map[name]
    set_dir(name, dir_value)
    print(f"[MOTOR] {name:8s} | DIR bit #{DIR_INDEX[name]} -> {dir_value} | PUL GPIO {pul} | {steps} pas")
    pulse_steps(pul, steps, delay_s)

# =========================
# Séquences de test
# =========================
def test_leds_rapide():
    print("\n[TEST] LEDs: ALL ON -> ALL OFF")
    set_all_leds(1)
    time.sleep(1)
    set_all_leds(0)
    time.sleep(1)
    set_all_leds(1)
    time.sleep(1)
    set_all_leds(0)
    time.sleep(1)

def fermer_toutes_les_vannes():
    print("\n[TEST] FERMETURE de toutes les vannes (sens = DIR_CLOSE)")
    for name in DIR_BIT_ORDER:
        move_motor(name, STEPS, DIR_CLOSE, STEP_DELAY)

def ouvrir_toutes_les_vannes():
    print("\n[TEST] OUVERTURE de toutes les vannes (sens = DIR_OPEN)")
    for name in DIR_BIT_ORDER:
        move_motor(name, STEPS, DIR_OPEN, STEP_DELAY)

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
        print("=== Programme de test LEDs & Moteurs ===")
        clear_all_shift()

        # 1) LEDs
        test_leds_rapide()
        # s'assurer que les LEDs sont éteintes pendant les tests moteurs
        set_all_leds(1)

        # 2) Fermer toutes les vannes
        #fermer_toutes_les_vannes()
        # 3) Ouvrir toutes les vannes
        #ouvrir_toutes_les_vannes()
        
        set_all_dir(0)
        move_motor("cuve", 1200, 0, 0.002)
        time.sleep(1)
        set_all_dir(1)
        move_motor("cuve", 1200, 1, 0.002)
        

        print("\n[OK] Test terminé.")

    except KeyboardInterrupt:
        print("\n[STOP] Interruption par l'utilisateur.")
    finally:
        clear_all_shift()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
