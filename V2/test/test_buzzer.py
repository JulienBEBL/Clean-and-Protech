#!/usr/bin/env python3

import RPi.GPIO as GPIO
import time

BUZZER_GPIO = 26      # GPIO26 BCM
FREQUENCY = 2000      # 2 kHz (buzzer resonance)

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_GPIO, GPIO.OUT)

# PWM à 2 kHz
pwm = GPIO.PWM(BUZZER_GPIO, FREQUENCY)

try:
    # Démarrage du buzzer (50 % duty)
    pwm.start(50.0)
    time.sleep(2.0)   # buzzer ON pendant 2 s

    # Pause
    pwm.stop()
    time.sleep(1.0)

    # Deuxième test : bip court répété
    pwm = GPIO.PWM(BUZZER_GPIO, FREQUENCY)
    pwm.start(50.0)
    for _ in range(3):
        time.sleep(0.2)
        pwm.ChangeDutyCycle(0)
        time.sleep(0.2)
        pwm.ChangeDutyCycle(50)

    pwm.stop()

finally:
    GPIO.cleanup()
