#!/usr/bin/python3
import RPi.GPIO as GPIO
import time

AIR_PIN = 15
PULSE_MS = 200

def air_pulse(duration_ms=PULSE_MS):
    GPIO.output(AIR_PIN, GPIO.HIGH)
    time.sleep(duration_ms/1000.0)
    GPIO.output(AIR_PIN, GPIO.LOW)
    print(f"[VFD] Impulsion {duration_ms} ms")

if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(AIR_PIN, GPIO.OUT, initial=GPIO.LOW)
    try:
        print("[TEST] AIR ON 2s / OFF 2s x3")
        for _ in range(3):
            GPIO.output(AIR_PIN, GPIO.HIGH); print("AIR=ON"); time.sleep(2)
            GPIO.output(AIR_PIN, GPIO.LOW);  print("AIR=OFF"); time.sleep(2)

        print("[TEST] AIR : 3 impulsions espacées de 3s")
        for _ in range(3):
            air_pulse()
            time.sleep(3)

        print("[OK] Tests relais terminés.")
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.output(AIR_PIN, GPIO.LOW)
        GPIO.output(VFD_PIN, GPIO.LOW)
        GPIO.cleanup()
