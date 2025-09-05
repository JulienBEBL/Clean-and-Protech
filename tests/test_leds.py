#!/usr/bin/python3
import RPi.GPIO as GPIO
import time

DATA, LATCH, CLOCK = 21, 20, 16

def send_led_mask(led_mask):
    # Dir=0x00 (aucun intérêt ici) + LED_MASK
    dir_mask = 0x00
    word = ((dir_mask & 0xFF) << 8) | ((led_mask & 0x0F) << 4)
    GPIO.output(LATCH, 0)
    for i in range(15, -1, -1):
        bit = (word >> i) & 1
        GPIO.output(CLOCK, 0)
        GPIO.output(DATA, bit)
        GPIO.output(CLOCK, 1)
    GPIO.output(LATCH, 1)

if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)
    GPIO.setup((DATA, LATCH, CLOCK), GPIO.OUT, initial=GPIO.LOW)
    try:
        print("[TEST] LED : une à la fois")
        for i in range(4):
            send_led_mask(1 << i)
            time.sleep(0.8)

        print("[TEST] LED : deux à la fois")
        combos = [(0,1), (1,2), (2,3), (0,3)]
        for a,b in combos:
            send_led_mask((1<<a) | (1<<b))
            time.sleep(0.8)

        print("[TEST] LED : cycle allumé/éteint pour toutes")
        for _ in range(5):
            send_led_mask(0x0F); time.sleep(0.5)
            send_led_mask(0x00); time.sleep(0.5)

        print("[OK] Tests LEDs terminés.")
    except KeyboardInterrupt:
        pass
    finally:
        send_led_mask(0x00)
        GPIO.cleanup()
