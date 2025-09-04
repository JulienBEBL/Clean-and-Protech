#!/usr/bin/python3
import RPi.GPIO as GPIO
import time

# === Mapping moteurs (PUL) ===
motor_map = {
    "V4V": 19, "clientG": 18, "clientD": 15, "egout": 14,
    "boue": 13, "pompeOUT": 12, "cuve": 6, "eau": 5
}
BIT_INDEX = { "V4V":0, "clientG":1, "clientD":2, "egout":3,
              "boue":4, "pompeOUT":5, "cuve":6, "eau":7 }

# === 74HC595 ===
DATA, LATCH, CLOCK = 21, 20, 16

# === Sens (via 74HC595) ===
OUVERTURE = "0"
FERMETURE = "1"
DIR_MASK = 0x00  # bit=1 => fermeture
LED_MASK = 0x00  # LEDs non utilisées ici

# === Timings ===
t_step = 0.001
t_maz  = 0.002
NB_PAS_O_F = 800

def _shift_send_masks(dir_mask: int, led_mask: int):
    word = ((dir_mask & 0xFF) << 8) | ((led_mask & 0x0F) << 4)
    GPIO.output(LATCH, 0)
    for i in range(15, -1, -1):
        bit = (word >> i) & 1
        GPIO.output(CLOCK, 0)
        GPIO.output(DATA, bit)
        GPIO.output(CLOCK, 1)
    GPIO.output(LATCH, 1)

def set_dir(nom_moteur: str, sens: str):
    global DIR_MASK
    bit = 1 << BIT_INDEX[nom_moteur]
    if sens == OUVERTURE:
        DIR_MASK &= ~bit
    else:
        DIR_MASK |= bit

def move(step_count, nom_moteur, tempo):
    pin = motor_map[nom_moteur]
    out = GPIO.output; hi, lo = GPIO.HIGH, GPIO.LOW; sleep = time.sleep
    for _ in range(step_count):
        out(pin, hi); sleep(tempo)
        out(pin, lo); sleep(tempo)

def test_ouverture_fermeture_all():
    print("[TEST] Ouverture de toutes les vannes…")
    for v in motor_map:
        set_dir(v, OUVERTURE)
    _shift_send_masks(DIR_MASK, LED_MASK)
    for v in motor_map:
        move(NB_PAS_O_F, v, t_step)
    time.sleep(1)

    print("[TEST] Fermeture de toutes les vannes…")
    for v in motor_map:
        set_dir(v, FERMETURE)
    _shift_send_masks(DIR_MASK, LED_MASK)
    for v in motor_map:
        move(NB_PAS_O_F, v, t_step)
    time.sleep(1)

def test_v4v_positions():
    print("[TEST] V4V : 3 positions en ouverture (3*800 pas)…")
    set_dir("V4V", OUVERTURE); _shift_send_masks(DIR_MASK, LED_MASK)
    move(800, "V4V", t_step); time.sleep(0.4)
    move(800, "V4V", t_step); time.sleep(0.4)
    move(800, "V4V", t_step); time.sleep(0.4)

    print("[TEST] V4V : retour en fermeture (3*800 pas)…")
    set_dir("V4V", FERMETURE); _shift_send_masks(DIR_MASK, LED_MASK)
    move(800, "V4V", t_step); time.sleep(0.4)
    move(800, "V4V", t_step); time.sleep(0.4)
    move(800, "V4V", t_step); time.sleep(0.4)

    print("[TEST] V4V : plusieurs tours rapides (2*1600 pas) ouverture puis fermeture…")
    set_dir("V4V", OUVERTURE); _shift_send_masks(DIR_MASK, LED_MASK)
    move(1600, "V4V", t_step)
    set_dir("V4V", FERMETURE); _shift_send_masks(DIR_MASK, LED_MASK)
    move(1600, "V4V", t_step)

if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(list(motor_map.values()), GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup((DATA, LATCH, CLOCK), GPIO.OUT, initial=GPIO.LOW)
    try:
        test_ouverture_fermeture_all()
        test_v4v_positions()
        print("[OK] Tests moteurs terminés.")
    except KeyboardInterrupt:
        pass
    finally:
        _shift_send_masks(0x00, 0x00)  # directions + leds à 0
        GPIO.cleanup()
