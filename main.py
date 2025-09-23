#!/usr/bin/python3
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
import time 
import sys
import os
import logging
from datetime import datetime
from threading import Thread
from libs.MCP3008_0 import MCP3008_0
from libs.MCP3008_1 import MCP3008_1
from libs.LCDI2C_backpack import LCDI2C_backpack

# -----------------------------
# Logging
# -----------------------------

os.makedirs("logs", exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = os.path.join("logs", f"{timestamp}.log")
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s;%(message)s")
log = logging.getLogger("log_prog")
log.info("LOG STARTED")

# -----------------------------
# Constants / Configuration
# -----------------------------

STEP_MOVE = 1200
PROGRAM_DURATION_SEC = 5 * 60
V4V_POS_STEPS = [0, 160, 320, 480, 640, 800]

# 74HC595 pins (BCM)
dataPIN  = 16   # DS
latchPIN = 20   # ST_CP / Latch
clockPIN = 21   # SH_CP / Clock

FLOW_PIN = 14
electrovannePIN = 15
BUTTON_PIN = 18

btn_raw = [0,0,0,0,0,0]
btn_state = [0,0,0,0,0,0]
num_prg = 0
selec_raw = [0,0,0,0,0]
selec_state = [0,0,0,0,0]
num_selec = 0
air_raw =0
seuil_mcp = 1010

count = 0
last_flow_time = 0

motor_map = {
    "V4V": 17, "clientG": 27, "clientD": 22, "egout": 5,
    "boue": 6, "pompeOUT": 13, "cuve": 19, "eau": 26
}
motor_order = ["V4V", "clientG", "clientD", "egout", "boue", "pompeOUT", "cuve", "eau"]
DIR_OPEN = 0
DIR_CLOSE = 1

v4v_curr_index = 0        # index courant (0..len(V4V_POS_STEPS)-1)
v4v_last_selec = None     # dernier num_selec vu

# Bits for the two cascaded 74HC595: 16 outputs total
# Layout expected by the original code: [bits_leds (4)] + [bits_blank (4)] + [bits_dir (8)]
bits_leds = [0,0,0,0]
bits_blank = [0,0,0,0]
bits_dir = [0,0,0,0,0,0,0,0]

air_mode = 1 
air_on = False 
last_switch = time.time()

last_idle_msg = ("", "")

# -----------------------------
# 74HC595 helpers (replacement for pi74HC595.set_by_list)
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

# -----------------------------
# MCP / IO helpers
# -----------------------------

def MCP_update():
    global btn_state, num_prg, selec_state, num_selec
    btn_state   = [1 if MCP_2.read(i) > seuil_mcp else 0 for i in range(8)]
    num_prg     = btn_state.index(1)+1 if sum(btn_state) == 1 else 0
    selec_state = [1 if MCP_1.read(i) > seuil_mcp else 0 for i in range(5)]
    num_selec   = selec_state.index(1) if sum(selec_state) == 1 else 0

def countPulse(channel):
    global count
    count += 1

def update_lcd_timer(start_time, duration_s):
    elapsed = int(time.time() - start_time)
    remaining = max(0, duration_s - elapsed)
    lcd.lcd_string(f"Prg 1, Reste: {remaining:03d}s", lcd.LCD_LINE_1)

def update_lcd_flow():
    global count, last_flow_time
    now = time.time()
    if last_flow_time == 0:
        last_flow_time = now
        lcd.lcd_string("Debit: --.- L/m", lcd.LCD_LINE_2)
        return 0.0
    interval = now - last_flow_time
    last_flow_time = now
    if interval <= 0:
        return 0.0
    pulses = count; count = 0
    flow = (pulses / interval) * 5
    lcd.lcd_string(f"Debit: {flow:.1f} L/m", lcd.LCD_LINE_2)
    return flow

def set_air_mode(mode: int):
    global air_mode, air_on, last_switch
    air_mode = max(1, min(4, int(mode)))
    for i in range(4):
        bits_leds[i] = 1 if (i == air_mode - 1) else 0
    set_shift(bits_leds + bits_blank + bits_dir)
    air_on = False
    last_switch = time.time()

def on_button_press(channel):
    set_air_mode(air_mode + 1 if air_mode < 4 else 1)

def air_loop_tick():

    global air_on, last_switch
    now = time.time()

    if air_mode == 1: # Pas d'injection
        if GPIO.input(electrovannePIN) != GPIO.LOW:
            GPIO.output(electrovannePIN, GPIO.LOW)
        air_on = False

    elif air_mode == 2: # 2s ON / 2s OFF
        period_on, period_off = 2.0, 2.0
        if air_on:
            if now - last_switch >= period_on:
                GPIO.output(electrovannePIN, GPIO.LOW)
                air_on = False
                last_switch = now
        else:
            if now - last_switch >= period_off:
                GPIO.output(electrovannePIN, GPIO.HIGH)
                air_on = True
                last_switch = now

    elif air_mode == 3: # 2s ON / 4s OFF
        period_on, period_off = 2.0, 4.0
        if air_on:
            if now - last_switch >= period_on:
                GPIO.output(electrovannePIN, GPIO.LOW)
                air_on = False
                last_switch = now
        else:
            if now - last_switch >= period_off:
                GPIO.output(electrovannePIN, GPIO.HIGH) 
                air_on = True
                last_switch = now

    elif air_mode == 4: # Continu
        if GPIO.input(electrovannePIN) != GPIO.HIGH:
            GPIO.output(electrovannePIN, GPIO.HIGH) 
        air_on = True

def move(motor, STEP):
    for i in range(STEP):
        GPIO.output(motor,GPIO.HIGH)
        time.sleep(.001)
        GPIO.output(motor,GPIO.LOW)
        time.sleep(.001)

def v4v_select_tick():
    global v4v_curr_index, v4v_last_selec, bits_dir

    sel = num_selec
    if sel is None:
        return

    sel = max(0, min(sel, len(V4V_POS_STEPS) - 1))

    if v4v_last_selec is None:
        v4v_last_selec = sel
        v4v_curr_index = sel
        return

    if sel == v4v_curr_index:
        v4v_last_selec = sel
        return

    target_idx = sel
    delta = V4V_POS_STEPS[target_idx] - V4V_POS_STEPS[v4v_curr_index]
    if delta == 0:
        v4v_curr_index = target_idx
        v4v_last_selec = sel
        return

    v4v_dir_idx = motor_order.index("V4V")           # index dans bits_dir
    bits_dir[v4v_dir_idx] = (DIR_OPEN if delta > 0 else DIR_CLOSE)
    set_shift(bits_leds + bits_blank + bits_dir)

    move(motor_map["V4V"], abs(delta))

    v4v_curr_index = target_idx
    v4v_last_selec = sel

def init_valves(step_open=STEP_MOVE):

    move(motor_map["V4V"], STEP_MOVE)
    
    for name in motor_order:
        bits_dir[motor_order.index(name)] = DIR_OPEN
    set_shift(bits_leds + bits_blank + bits_dir)

    pins = [motor_map[n] for n in motor_order]
    threads = [Thread(target=move, args=(pin, step_open), daemon=True) for pin in pins]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

def start_programme(num, to_close, to_open, duration_s):
    #SETUP PRG
    lcd.clear()
    lcd.lcd_string(f"Programme {num}", lcd.LCD_LINE_1)
    lcd.lcd_string("Total 05:00", lcd.LCD_LINE_2)
    time.sleep(2)
    lcd.lcd_string("Préparation moteurs", lcd.LCD_LINE_2)
    time.sleep(2)
    
    for name in motor_order:
        if name in to_close:
            bits_dir[motor_order.index(name)] = DIR_CLOSE
        elif name in to_open:
            bits_dir[motor_order.index(name)] = DIR_OPEN
    
    set_shift(bits_leds + bits_blank + bits_dir)

    pins = [motor_map[n] for n in (set(to_close) | set(to_open))]
    threads = [Thread(target=move, args=(pin, STEP_MOVE), daemon=True) for pin in pins]
    for t in threads: t.start()
    for t in threads: t.join()
    
     # BOUCLE PRINCIPALE
    lcd.clear()
    start = time.time()
    while time.time() - start < duration_s:
        air_loop_tick()
        update_lcd_timer(start, duration_s)
        update_lcd_flow()
        time.sleep(0.2)
    
    #END PRG
    global num_prg
    num_prg = 0
    lcd.clear()
    lcd.lcd_string(f"Programme {num}", lcd.LCD_LINE_1)
    lcd.lcd_string("terminé !", lcd.LCD_LINE_2)
    time.sleep(3)

def prg_1(): start_programme(1, ["eau", "cuve", "pompeOUT", "clientD", "egout"], ["clientG", "boue"], PROGRAM_DURATION_SEC)
def prg_2(): start_programme(2, ["clientD", "boue", "egout"], ["eau", "cuve", "pompeOUT", "clientG"], PROGRAM_DURATION_SEC)
def prg_3(): start_programme(3, ["eau", "clientD", "boue"], ["pompeOUT", "clientG", "egout", "cuve"], PROGRAM_DURATION_SEC)
def prg_4(): start_programme(4, ["cuve", "pompeOUT", "egout"], ["eau", "clientG", "clientD", "boue"], PROGRAM_DURATION_SEC)
def prg_5(): start_programme(5, ["clientG", "cuve", "eau", "egout"], ["pompeOUT", "clientD", "boue"], PROGRAM_DURATION_SEC)
def prg_6(): start_programme(6, ["eau", "cuve"], ["pompeOUT", "clientD", "clientG", "boue", "egout"], PROGRAM_DURATION_SEC)

try:
    log.info("Initialisation")
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Setup 74HC595 control pins
    GPIO.setup((dataPIN, latchPIN, clockPIN), GPIO.OUT, initial=GPIO.LOW)
    
    lcd = LCDI2C_backpack(0x27)
    lcd.clear()
    lcd.lcd_string("Initialisation", lcd.LCD_LINE_1)
    lcd.lcd_string("En cours...",     lcd.LCD_LINE_2)
    
    motor = list(motor_map.values())
    GPIO.setup(motor, GPIO.OUT)
    GPIO.output(motor, GPIO.LOW)
    
    GPIO.setup(FLOW_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.add_event_detect(FLOW_PIN, GPIO.FALLING, callback=countPulse)
    
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(electrovannePIN, GPIO.OUT, initial=GPIO.LOW)
    GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=on_button_press, bouncetime=250)
    
    MCP_1 = MCP3008_0()
    time.sleep(.001)
    MCP_2 = MCP3008_1()
    time.sleep(.001)
    
    # Clear outputs then set initial air mode LEDs
    set_shift([0]*16)
    time.sleep(.001)
    set_air_mode(1)
    
    init_valves()
    time.sleep(.1)
    
    last_flow_time = time.time()
    
    lcd.clear()
    lcd.lcd_string("Initialisation", lcd.LCD_LINE_1)
    lcd.lcd_string("OK",             lcd.LCD_LINE_2)
    log.info("Initialisation OK")
    time.sleep(2)
    
    while True:
        line1 = "Choisissez un programme :"
        line2 = "Appuyer sur un bouton"
        if (line1, line2) != last_idle_msg:
            lcd.lcd_string(line1, lcd.LCD_LINE_1)
            lcd.lcd_string(line2, lcd.LCD_LINE_2)
            last_idle_msg = (line1, line2)
        
        MCP_update()
        v4v_select_tick()

        if   num_prg == 1 : prg_1()
        elif num_prg == 2 : prg_2()
        elif num_prg == 3 : prg_3()
        elif num_prg == 4 : prg_4()
        elif num_prg == 5 : prg_5()
        elif num_prg == 6 : prg_6()

        time.sleep(0.1)
        
    pass

except KeyboardInterrupt:
    log.info("SIGINT reçu (CTRL+C)")

except Exception as e:
    log.info(f"EXCEPTION;{e}")

finally:
    try: MCP_1 and MCP_1.close()
    except: pass
    try: MCP_2 and MCP_2.close()
    except: pass
    try: set_shift([0]*16)
    except: pass
    try: GPIO.output(electrovannePIN, GPIO.LOW)
    except: pass
    GPIO.cleanup()
    log.info("END OF PRG")
    time.sleep(0.01)
    pass
