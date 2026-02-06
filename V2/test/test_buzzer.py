#!/usr/bin/env python3
from gpiozero import PWMOutputDevice
from time import sleep
import math

GPIO_BUZZER = 26

# Réglages
DUTY = 0.35          # 35% pour éviter trop de "claque"/saturation mécanique
F_START = 200        # Hz
F_STOP = 8000        # Hz
STEPS = 60           # nb de pas du sweep
TONE_TIME = 0.18     # durée par fréquence (s)
GAP_TIME = 0.05      # silence entre pas (s)

def log_sweep_freqs(f_start, f_stop, steps):
    """Liste de fréquences logarithmiques entre f_start et f_stop."""
    freqs = []
    ratio = f_stop / f_start
    for i in range(steps):
        f = f_start * (ratio ** (i / (steps - 1)))
        freqs.append(int(round(f)))
    # supprime doublons éventuels après arrondi
    out = []
    for f in freqs:
        if not out or f != out[-1]:
            out.append(f)
    return out

buzzer = PWMOutputDevice(pin=GPIO_BUZZER, frequency=2000, initial_value=0.0)

try:
    print("Sweep LOG (200 -> 8000 Hz). Ctrl+C pour arrêter.")
    freqs = log_sweep_freqs(F_START, F_STOP, STEPS)

    for f in freqs:
        buzzer.frequency = f
        buzzer.value = DUTY
        print(f"f = {f} Hz")
        sleep(TONE_TIME)
        buzzer.off()
        sleep(GAP_TIME)

    # petit test autour de la résonance datasheet (2 kHz) plus fin
    print("\nSweep FIN autour de 2 kHz (1500 -> 3000 Hz)")
    for f in range(1500, 3001, 50):
        buzzer.frequency = f
        buzzer.value = DUTY
        print(f"f = {f} Hz")
        sleep(0.15)
        buzzer.off()
        sleep(0.05)

finally:
    buzzer.off()
    buzzer.close()
