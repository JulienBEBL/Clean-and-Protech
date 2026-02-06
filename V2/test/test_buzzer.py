#!/usr/bin/env python3

from gpiozero import PWMOutputDevice
from time import sleep

BUZZER_GPIO = 26
FREQ = 2000      # Hz
DUTY = 0.5       # 50 %

buzzer = PWMOutputDevice(
    pin=BUZZER_GPIO,
    frequency=FREQ,
    initial_value=0.0
)

try:
    # Buzzer ON 2 s
    buzzer.value = DUTY
    sleep(2.0)

    # OFF
    buzzer.off()
    sleep(0.5)

    # Bip-bip-bip
    for _ in range(3):
        buzzer.value = DUTY
        sleep(0.2)
        buzzer.off()
        sleep(0.2)

finally:
    buzzer.close()
