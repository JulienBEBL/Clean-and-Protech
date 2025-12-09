#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import RPi.GPIO as GPIO

BUZZER_PIN = 21

# Fréquences d'essai (Hz)
FREQ_TONES = [800, 1500, 2700, 3500]  # 2700 Hz ≈ fréquence de résonance donnée

# Durées de base
SHORT_BEEP = 0.15
LONG_BEEP = 0.40

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# PWM initialisé à la fréquence nominale
pwm = GPIO.PWM(BUZZER_PIN, 2700)
pwm.start(0)   # duty cycle à 0 % => silence


def play_tone(freq=2700, duty=50, duration=0.2, post_silence=0.05):
    """
    Joue un bip simple.
    - freq : fréquence en Hz
    - duty : "puissance apparente" (0–100 %)
    - duration : durée du bip
    - post_silence : temps de silence après le bip
    """
    pwm.ChangeFrequency(freq)
    pwm.ChangeDutyCycle(duty)
    time.sleep(duration)
    pwm.ChangeDutyCycle(0)   # coupe le son
    time.sleep(post_silence)


def sequence_tonalites():
    """Balaye quelques fréquences typiques, à puissance moyenne."""
    print("\n=== Séquence tonalités (fréquences différentes) ===")
    for f in FREQ_TONES:
        print(f"Ton {f} Hz")
        play_tone(freq=f, duty=60, duration=0.25, post_silence=0.10)
    time.sleep(0.5)


def sequence_puissances():
    """Teste l'effet du duty-cycle (volume) à la fréquence nominale (~2,7 kHz)."""
    print("\n=== Séquence puissances (duty-cycle) à 2700 Hz ===")
    freq = 2700
    for duty in [20, 40, 60, 80, 100]:
        print(f"2700 Hz - duty {duty}%")
        play_tone(freq=freq, duty=duty, duration=0.25, post_silence=0.10)
    time.sleep(0.5)


def sequence_alarme():
    """Petit motif type alarme : grave / aigu répétés."""
    print("\n=== Séquence alarme ===")
    low = 1500
    high = 3200
    for _ in range(4):
        play_tone(freq=low, duty=70, duration=SHORT_BEEP, post_silence=0.05)
        play_tone(freq=high, duty=70, duration=SHORT_BEEP, post_silence=0.10)
    time.sleep(0.5)


def sequence_sweep():
    """Sweep de fréquence pour entendre la résonance du buzzer."""
    print("\n=== Sweep de fréquence (1000 → 4000 Hz) ===")
    start_f = 1000
    end_f = 4000
    step = 100
    pwm.ChangeDutyCycle(50)

    # Montée
    for f in range(start_f, end_f + step, step):
        pwm.ChangeFrequency(f)
        time.sleep(0.03)

    # Descente
    for f in range(end_f, start_f - step, -step):
        pwm.ChangeFrequency(f)
        time.sleep(0.03)

    pwm.ChangeDutyCycle(0)
    time.sleep(0.5)


try:
    print("Test buzzer sur GPIO 21 démarré. CTRL+C pour arrêter.")

    while True:
        sequence_tonalites()
        sequence_puissances()
        sequence_alarme()
        sequence_sweep()

        print("\nPause 2 s avant de recommencer...\n")
        time.sleep(2)

except KeyboardInterrupt:
    pass

pwm.stop()
GPIO.cleanup()
print("Test buzzer terminé proprement.")
