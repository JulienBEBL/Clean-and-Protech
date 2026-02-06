#!/usr/bin/python3
import RPi.GPIO as GPIO
import time

# 74HC595 pins (BCM)
dataPIN  = 21   # DS
latchPIN = 20   # ST_CP / Latch
clockPIN = 16   # SH_CP / Clock

# Bits for the two cascaded 74HC595: 16 outputs total
# Layout expected by the original code: [bits_leds (4)] + [bits_blank (4)] + [bits_dir (8)]
bits_leds = [0,0,0,0]
bits_blank = [0,0,0,0]
bits_dir = [0,0,0,0,0,0,0,0]

# -----------------------------
# 74HC595 helpers (replacement pi74HC595.set_by_list)
# -----------------------------

def shift_update(input_str, data, clock, latch):
    """Send 16-bit string like '0000000011111111' to two daisy-chained 74HC595.
    Bits are clocked MSB-first as in the user's reference function.
    """
    # put latch down to start data sending
    GPIO.output(clock, 0)
    GPIO.output(latch, 0)
    GPIO.output(clock, 1)

    # load data in reverse order
    for i in range(15, -1, -1):
        GPIO.output(clock, 0)
        GPIO.output(data, int(input_str[i]))
        GPIO.output(clock, 1)

    # put latch up to store data on register
    GPIO.output(clock, 0)
    GPIO.output(latch, 1)
    GPIO.output(clock, 1)

def _bits_to_str(bits16):
    """Convert a list/iterable of 16 ints (0/1) to a '0'/'1' string."""
    if len(bits16) != 16:
        raise ValueError(f"Expected 16 bits, got {len(bits16)}")
    return "".join("1" if int(b) else "0" for b in bits16)

def set_shift(bits16):
    """Drop-in replacement for shift_register.set_by_list(bits16)."""
    s = _bits_to_str(bits16)
    shift_update(s, dataPIN, clockPIN, latchPIN)

if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)
    GPIO.setup((dataPIN, latchPIN, clockPIN), GPIO.OUT, initial=GPIO.LOW)
    try:
        print("lancement")
        set_shift([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
        time.sleep(1)
        set_shift([1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1])
        time.sleep(2)
        set_shift(bits_dir + bits_blank + bits_leds)
        
        print("test pour le sens")
        time.sleep(1)
        bits_leds=[1,0,1,0]
        set_shift(bits_dir + bits_blank + bits_leds)
        time.sleep(5)
        set_shift([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
        time.sleep(1)
        
        print(" test fini")
        set_shift([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
        time.sleep(1)
        print("test2")
        
        bits_leds = [1,0,0,0]
        set_shift(bits_dir + bits_blank + bits_leds)
        time.sleep(1)
        bits_leds = [0,1,0,0]
        set_shift(bits_dir + bits_blank + bits_leds)
        time.sleep(1)
        bits_leds = [0,0,1,0]
        set_shift(bits_dir + bits_blank + bits_leds)
        time.sleep(1)
        bits_leds = [0,0,0,1]
        set_shift(bits_dir + bits_blank + bits_leds)
        time.sleep(1)
        set_shift([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
        print("[OK] Tests LEDs terminés.")
    except KeyboardInterrupt:
        pass
    finally:
        set_shift([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
        GPIO.cleanup()
