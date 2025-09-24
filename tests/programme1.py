#!/usr/bin/python3
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
import time
import sys
import os
from libs_tests.MCP3008_0 import MCP3008_0
from libs_tests.MCP3008_1 import MCP3008_1

STEPS       = 1200         # nombre de pas par mouvement
STEP_DELAY  = 0.002       # secondes entre niveaux (1 kHz approx)
DIR_CLOSE   = 1           # sens "fermeture" (à inverser si besoin)
DIR_OPEN    = 0           # sens "ouverture" (à inverser si besoin)

SEUIL = 1000  # à ajuster si besoin

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

def home_v4v():
    global _current_v4v_pos
    set_all_dir(DIR_CLOSE)
    move_motor("V4V", 1000, STEP_DELAY)
    _current_v4v_pos = 0

def _pulse_steps(pul_pin, steps):
    for _ in range(steps):
        GPIO.output(pul_pin, 1)
        time.sleep(STEP_DELAY)
        GPIO.output(pul_pin, 0)
        time.sleep(STEP_DELAY)

def goto_v4v_steps(target_steps):
    """Va à une position absolue (0..800) depuis l’origine fermeture."""
    global _current_v4v_pos
    if _current_v4v_pos is None:
        raise RuntimeError("V4V non référencée : appeler home_v4v() d’abord.")
    delta = target_steps - _current_v4v_pos
    if delta == 0:
        return
    if delta > 0:
        set_all_dir(DIR_OPEN)
        _pulse_steps(5, delta)
    else:
        set_all_dir(DIR_CLOSE)
        _pulse_steps(5, -delta)
    _current_v4v_pos = target_steps

_prev_idx = None

# index 0..4 (exactement un seul '1' attendu)
SELECT_TO_STEPS = {
    0: 0,     # 1.0.0.0.0  => origine fermeture
    1: 300,   # 0.1.0.0.0  => +200
    2: 500,   # 0.0.1.0.0  => +400
    3: 700,   # 0.0.0.1.0  => +600
    4: 1000,   # 0.0.0.0.1  => butée ouverture
}

def update_v4v_from_selector(mcp1, seuil=SEUIL):

    global _prev_idx

    selec_raw = [mcp1.read(i) for i in range(5)]
    selec_state = [1 if v > seuil else 0 for v in selec_raw]

    # On ne réagit que si exactement 1 entrée est active.
    if selec_state.count(1) != 1:
        return  # ignore bruit / 0 ou multi-sélections

    idx = selec_state.index(1)  # 0..4
    if idx == _prev_idx:
        return  # pas de changement

    # Nouvelle commande : aller à la position demandée
    target = SELECT_TO_STEPS[idx]
    print(f"[V4V] sélecteur={selec_state} -> target={target} pas")
    goto_v4v_steps(target)
    _prev_idx = idx

# =========================
# Main
# =========================

def main():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    
    mcp1 = MCP3008_0()
    mcp2 = MCP3008_1()

    # 74HC595
    GPIO.setup((dataPIN, latchPIN, clockPIN), GPIO.OUT, initial=GPIO.LOW)

    # PUL moteurs
    for pin in motor_map.values():
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    try:
        print("=== Programme 1 ===")
        clear_all_shift()
        
        print("FERMETURE")
        set_all_dir(DIR_CLOSE)
        move_motor("eau", STEPS, STEP_DELAY)
        move_motor("cuve", STEPS, STEP_DELAY)
        move_motor("pompeOUT", STEPS, STEP_DELAY)
        move_motor("egout", STEPS, STEP_DELAY)
        
        time.sleep(1)
        
        print("OUVERTURE")
        set_all_dir(DIR_OPEN)
        move_motor("clientD", STEPS, STEP_DELAY)
        move_motor("clientG", STEPS, STEP_DELAY)
        move_motor("boue", STEPS, STEP_DELAY)
        
        print("Attente 5s...")
        time.sleep(5)
        print("Référence V4V...")
        set_all_dir(DIR_CLOSE)
        home_v4v()
        print("Position initiale V4V OK.")
        print("Mise à jour V4V depuis sélecteur (CTRL-C pour arrêter)...") 
        set_all_dir(DIR_OPEN)       
        update_v4v_from_selector(mcp1, seuil=SEUIL)
        
        
        

        print("\n[OK] PRG1 terminé.")

    except KeyboardInterrupt:
        print("\n[STOP] Interruption par l'utilisateur.")
    finally:
        clear_all_shift()
        mcp1.close(); mcp2.close()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
