#!/usr/bin/python3
import time
import RPi.GPIO as GPIO

BUZZER_PIN = 21
FREQ = 1000  # Hz

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

pwm = GPIO.PWM(BUZZER_PIN, FREQ)
pwm.start(0)  # duty cycle initial

try:
    while True:
        print("Buzzer ON")
        pwm.ChangeDutyCycle(50)  # 50% duty
        time.sleep(1)

        print("Buzzer OFF")
        pwm.ChangeDutyCycle(0)
        time.sleep(1)

except KeyboardInterrupt:
    pass

pwm.stop()
GPIO.cleanup()
print("Test buzzer terminé.")
