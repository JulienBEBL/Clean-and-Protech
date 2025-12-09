#!/usr/bin/env python3
from gpiozero import LED
from gpiozero.pins.lgpio import LGPIOFactory
import time

factory = LGPIOFactory()  # backend lgpio
pin = 21  # BCM

led = LED(pin, pin_factory=factory)

try:
    led.on()
    print("ON")
    time.sleep(2)
    led.off()
    print("OFF")
    time.sleep(1)

    # clignotement
    for i in range(5):
        led.on()
        time.sleep(0.3)
        led.off()
        time.sleep(0.3)

finally:
    led.close()
