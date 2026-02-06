#!/usr/bin/python3
import RPi.GPIO as GPIO
import time

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# --- GPIO (BCM) ---
PUL = 16
DIR = 20
ENA = 21

# --- Polarit é ENA ---
# Beaucoup de drivers : ENA=0 => ENABLED
ENA_ACTIVE_LOW = True

ON = GPIO.HIGH
OFF = GPIO.LOW

GPIO.setup(PUL, GPIO.OUT, initial=OFF)
GPIO.setup(DIR, GPIO.OUT, initial=OFF)
GPIO.setup(ENA, GPIO.OUT)

def enable_driver():
    GPIO.output(ENA, OFF if ENA_ACTIVE_LOW else ON)

def disable_driver():
    GPIO.output(ENA, ON if ENA_ACTIVE_LOW else OFF)

def move_steps(steps: int, step_hz: float, clockwise: bool = True):
    """
    steps    : nombre d'impulsions STEP
    step_hz  : fréquence des pas (pas/s). Exemple 1000 => 1000 pas/s
    clockwise: sens (à adapter selon ton câblage)
    """
    if steps <= 0:
        return
    if step_hz <= 0:
        raise ValueError("step_hz doit être > 0")

    GPIO.output(DIR, OFF if clockwise else ON)
    time.sleep(0.00005)  # petit temps de setup dir

    # Une période = 1/step_hz. On fait HIGH puis LOW => demi-période
    half_period = 0.5 / float(step_hz)

    for _ in range(int(steps)):
        GPIO.output(PUL, ON)
        time.sleep(half_period)
        GPIO.output(PUL, OFF)
        time.sleep(half_period)

def main():
    enable_driver()
    time.sleep(0.05)

    howmany = int(input("Nombre de pas (ex: 3200 = 1 tour si 3200 pas/tour) : "))
    speed_hz = float(input("Vitesse (pas/s, ex: 800) : "))

    print("Mouvement dans le sens horaire...") 
    move_steps(howmany, speed_hz, clockwise=True)
    time.sleep(0.2)
    print("Mouvement dans le sens anti-horaire...")
    move_steps(howmany, speed_hz, clockwise=False)

    disable_driver()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        # Sécurité
        try:
            disable_driver()
        except Exception:
            pass
        GPIO.cleanup()
