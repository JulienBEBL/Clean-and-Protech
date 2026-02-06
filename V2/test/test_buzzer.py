#!/usr/bin/env python3
import pigpio
import time

GPIO_BUZZ = 26
FREQ = 2000
DUTY = 500000   # pigpio duty: 0..1_000_000 (50% => 500000)

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon non connecté. Lance: sudo systemctl enable --now pigpiod")

try:
    pi.set_mode(GPIO_BUZZ, pigpio.OUTPUT)
    pi.set_PWM_frequency(GPIO_BUZZ, FREQ)
    pi.set_PWM_range(GPIO_BUZZ, 1000000)
    pi.set_PWM_dutycycle(GPIO_BUZZ, DUTY)

    time.sleep(2.0)

    pi.set_PWM_dutycycle(GPIO_BUZZ, 0)
    time.sleep(0.5)

    # Bip-bip-bip
    for _ in range(3):
        pi.set_PWM_dutycycle(GPIO_BUZZ, DUTY)
        time.sleep(0.2)
        pi.set_PWM_dutycycle(GPIO_BUZZ, 0)
        time.sleep(0.2)
finally:
    pi.stop()
