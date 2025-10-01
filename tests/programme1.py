#!/usr/bin/python3
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
import time
import sys
import os
import logging
from datetime import datetime
from libs_tests.MCP3008_0 import MCP3008_0
from libs_tests.MCP3008_1 import MCP3008_1
from libs_tests.LCDI2C_backpack import LCDI2C_backpack

# -----------------------------
# Logging
# -----------------------------

os.makedirs("logs", exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = os.path.join("logs", f"{timestamp}.log")
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s;%(message)s")
log = logging.getLogger("log_prog")
log.info("[INFO] Log started.")

STEPS       = 1200         # nombre de pas par mouvement
STEP_DELAY  = 0.003       # secondes entre niveaux (1 kHz approx)
DIR_CLOSE   = 1           # sens "fermeture" (à inverser si besoin)
DIR_OPEN    = 0           # sens "ouverture" (à inverser si besoin)

AIR_ON = True 
AIR_OFF = False
V4V_ON = True
V4V_OFF = False

SEUIL = 1000  # sur 0..1023

V4V_MANUAL_WINDOW_SEC = 10  # temps d'écoute du sélecteur (à ajuster)

LCD_W = 16 # largeur du LCD

_prev_idx = None

_current_v4v_pos = None  # position actuelle de la V4V en pas (None = non référencée)

dataPIN  = 21   # DS
latchPIN = 20   # ST_CP / Latch
clockPIN = 16   # SH_CP / Clock

bits_dir   = [0]*8
bits_blank = [0]*4
bits_leds  = [0]*4

motor_map = {   
    "V4V": 5, "clientG": 27, "clientD": 26, "egout": 22,
    "boue": 13, "pompeOUT": 17, "cuve": 6, "eau": 19
}   

# index 0..4 (exactement un seul '1' attendu)
SELECT_TO_STEPS = {
    0: 0,     # 1.0.0.0.0  => origine fermeture
    1: 300,   # 0.1.0.0.0 
    2: 500,   # 0.0.1.0.0 => milieu
    3: 700,   # 0.0.0.1.0 
    4: 1000,   # 0.0.0.0.1  => butée ouverture
}

# --- Tableau noms de programmes ---
PROGRAM_NAMES = {
    1: "Premiere vidange",
    2: "Vidange cuve",
    3: "Sechage",
    4: "Remplissage cuve",
    5: "Desembouage",
}

# --- Tableau positions V4V ---
POS_V4V_PRG = {
    1: 0,
    2: 500,
    3: 0,
    4: 0,
}

# Définitions globales

def write_line(lcd, line, text):
    lcd.lcd_string(str(text).ljust(LCD_W)[:LCD_W], line)

def MCP_update_btn():
    global btn_state, num_prg
    btn_state   = [1 if mcp2.read(i) > SEUIL else 0 for i in range(8)]
    num_prg     = btn_state.index(1)+1 if sum(btn_state) == 1 else 0

def _bits_to_str(bits16):
    if len(bits16) != 16:
        raise ValueError(f"Expected 16 bits, got {len(bits16)}")
    return "".join("1" if int(b) else "0" for b in bits16)

def shift_update(input_str, data, clock, latch):
    """Envoie une chaîne 16 bits MSB-first vers 2x 74HC595 en cascade."""
    GPIO.output(clock, 0)
    GPIO.output(latch, 0)
    GPIO.output(clock, 1)

    for i in range(15, -1, -1):
        GPIO.output(clock, 0)
        GPIO.output(data, int(input_str[i]))
        GPIO.output(clock, 1)

    GPIO.output(clock, 0)
    GPIO.output(latch, 1)
    GPIO.output(clock, 1)

def push_shift():
    s = _bits_to_str(bits_dir + bits_blank + bits_leds)
    shift_update(s, dataPIN, clockPIN, latchPIN)

def set_all_leds(val):
    for i in range(4):
        bits_leds[i] = 1 if val else 0
    push_shift()

def clear_all_shift():
    for i in range(8): bits_dir[i] = 0
    for i in range(4): bits_blank[i] = 0
    for i in range(4): bits_leds[i] = 0
    push_shift()

def set_all_dir(value):
    bits_dir[:] = [value]*8
    push_shift()

def pulse_steps(pul_pin, steps, delay_s):
    for _ in range(steps):
        GPIO.output(pul_pin, GPIO.HIGH)
        time.sleep(delay_s)
        GPIO.output(pul_pin, GPIO.LOW)
        time.sleep(delay_s)

def move_motor(name, steps, delay_s):
    pul = motor_map[name]
    print(f"[MOTOR] {name:8s} | DIR = {bits_dir} | PUL GPIO {pul} | {steps} pas")
    pulse_steps(pul, steps, delay_s)

def home_v4v():
    global _current_v4v_pos
    set_all_dir(DIR_CLOSE)
    move_motor("V4V", 1000, STEP_DELAY)
    _current_v4v_pos = 0

def _pulse_steps(pul_pin, steps):
    for _ in range(steps):
        GPIO.output(pul_pin, 1)
        time.sleep(STEP_DELAY)
        GPIO.output(pul_pin, 0)
        time.sleep(STEP_DELAY)

def goto_v4v_steps(target_steps):
    global _current_v4v_pos
    if _current_v4v_pos is None:
        raise RuntimeError("V4V non référencée : appeler home_v4v() d’abord.")
    delta = target_steps - _current_v4v_pos
    if delta == 0:
        return
    if delta > 0:
        set_all_dir(DIR_OPEN)
        _pulse_steps(motor_map["V4V"], delta)
    else:
        set_all_dir(DIR_CLOSE)
        _pulse_steps(motor_map["V4V"], -delta)
    _current_v4v_pos = target_steps

def update_v4v_from_selector(mcp1, seuil=SEUIL):

    global _prev_idx

    selec_raw = [mcp1.read(i) for i in range(5)]
    selec_state = [1 if v > seuil else 0 for v in selec_raw]

    # On ne réagit que si exactement 1 entrée est active.
    if selec_state.count(1) != 1:
        return  # ignore bruit / 0 ou multi-sélections

    idx = selec_state.index(1)  # 0..4
    if idx == _prev_idx:
        return  # pas de changement

    # Nouvelle commande : aller à la position demandée
    target = SELECT_TO_STEPS[idx]
    print(f"[V4V] sélecteur={selec_state} -> target={target} pas")
    goto_v4v_steps(target)
    _prev_idx = idx

def start_programme(num:int, to_open:list, to_close:list, airmode:bool,v4vmanu:bool):
    # petit formateur mm:ss
    def _mmss(t):
        t = max(0, int(t))
        m, s = divmod(t, 60)
        return f"{m:02d}:{s:02d}"

    # écran d'accueil (5s)
    print(f"[PRG LANCEMENT] Programme {num}")
    lcd.clear()
    prg_name = PROGRAM_NAMES.get(num, f"Programme {num}")
    write_line(lcd, lcd.LCD_LINE_1, f"Programme {num}")
    write_line(lcd, lcd.LCD_LINE_2, prg_name)
    time.sleep(5)

    # --- OUVERTURE ---
    write_line(lcd, lcd.LCD_LINE_2, "Ouverture...")
    print("[SEQUENCE] OUVERTURE")
    for name in to_open:
        set_all_dir(DIR_OPEN)
        move_motor(name, STEPS, STEP_DELAY)

    # --- FERMETURE ---
    write_line(lcd, lcd.LCD_LINE_2, "Fermeture...")
    print("[SEQUENCE] FERMETURE")
    for name in to_close:
        set_all_dir(DIR_CLOSE)
        move_motor(name, STEPS, STEP_DELAY)
        
    # --- SELECTEUR ---
    
    lcd.clear()
    if not v4vmanu: # --- V4V AUTO ---
        write_line(lcd, lcd.LCD_LINE_1, "V4V : mode auto")
        target = POS_V4V_PRG.get(num)
        if target is None:
            print(f"[V4V] Pas de consigne pour programme {num} dans POS_V4V_PRG")
        else:
            # Messages LCD (optionnels)
            write_line(lcd, lcd.LCD_LINE_2, "V4V : position 0")
            home_v4v()  # origine = fermeture
            write_line(lcd, lcd.LCD_LINE_2, f"V4V -> {target} pas")
            try:
                goto_v4v_steps(target)  # position absolue depuis l'origine
                write_line(lcd, lcd.LCD_LINE_2, "V4V Prete")
            except Exception as e:
                print(f"[V4V] Erreur positionnement : {e}")
    
    if v4vmanu: # --- V4V : MODE MANUEL ---
        write_line(lcd, lcd.LCD_LINE_1, "V4V : mode manu")
        time.sleep(2)
        write_line(lcd, lcd.LCD_LINE_1, "Choisissez une")
        write_line(lcd, lcd.LCD_LINE_2, "position V4V 10s")
        time.sleep(V4V_MANUAL_WINDOW_SEC)

        print("Référence V4V...")
        home_v4v()  # origine = fermeture (gère déjà DIR_CLOSE)
        print("Position initiale V4V OK.")

        write_line(lcd, lcd.LCD_LINE_1, "Déplacement de")
        write_line(lcd, lcd.LCD_LINE_2, "la V4V...")
        
        update_v4v_from_selector(mcp1, seuil=SEUIL)  # suit le sélecteur

        print("Position manuelle V4V figée.")


    # --- CHRONOMÈTRE PRINCIPAL AVEC ARRÊT PAR BOUTON DU PROGRAMME ---
    start_ts = time.monotonic()
    last_sec = -1                      # dernière seconde affichée
    next_v4v_update_ts = start_ts + 5  # MAJ V4V périodique (si v4vmanu)
    prev_prog_btn_pressed = False      # pour détecter l'appui (front montant)
    write_line(lcd, lcd.LCD_LINE_1, f"Programme {num}") # titre

    # --- Boucle principale --- 
    while True:
        now = time.monotonic()
        elapsed_sec = int(now - start_ts)
        
        if elapsed_sec != last_sec:
            write_line(lcd, lcd.LCD_LINE_2, f"Temps : {_mmss(elapsed_sec)}")
            last_sec = elapsed_sec

        # Affichage au plus 1×/s
        if elapsed_sec != last_sec:
            lcd.lcd_string(f"Temps : {_mmss(elapsed_sec)}", lcd.LCD_LINE_2)
            last_sec = elapsed_sec

        # MAJ V4V toutes les 5 s si mode auto
        if v4vmanu and now >= next_v4v_update_ts:
            try:
                update_v4v_from_selector(mcp1, seuil=SEUIL)
            except Exception as e:
                print(f"[V4V] update skipped: {e}")
            while next_v4v_update_ts <= now:
                next_v4v_update_ts += 5

        # --- CONDITION D'ARRÊT : appui sur le bouton du programme en cours ---
        MCP_update_btn()                  # met à jour num_prg en fonction des boutons
        pressed_now = (num_prg == num)    # vrai si exactement ce bouton-là est pressé
        if pressed_now and not prev_prog_btn_pressed:
            # Front montant: l'utilisateur demande l'arrêt de CE programme
            lcd.lcd_string(f"Programme {num}", lcd.LCD_LINE_1)
            lcd.lcd_string("Arret demande",    lcd.LCD_LINE_2)
            time.sleep(2)
            break
        prev_prog_btn_pressed = pressed_now
        time.sleep(0.1)  # évite de consommer 100% CPU



# =========================     #to_open                        #to_close
def prg_1(): start_programme(1, ["clientG", "clientD", "boue"], ["eau", "cuve", "egout", "pompeOUT"], #PREMIERE VIDANGE
                            AIR_ON, V4V_OFF) #V4V auto, AIR manuel

def prg_2(): start_programme(2, ["cuve", "egout", "pompeOUT"], ["clientG", "boue", "clientD", "eau"], #VIDANGE CUVE TRAVAIL
                             AIR_OFF, V4V_OFF) #V4V auto, AIR bloqué

def prg_3(): start_programme(3, ["clientD", "clientG", "egout"], ["pompeOUT", "eau", "cuve", "boue"], #SECHAGE
                             AIR_ON, V4V_OFF) #V4V auto, AIR manuel

def prg_4(): start_programme(4, ["clientG", "clientD", "eau", "pompeOUT", "boue"], ["cuve", "egout"], #REMPLISSAGE CUVE
                             AIR_OFF, V4V_OFF) #V4V auto, AIR bloqué

def prg_5(): start_programme(5, ["cuve", "pompeOUT", "clientG", "clientD", "boue"], ["egout", "eau"], #DESEMBOUAGE
                             AIR_ON, V4V_ON) #V4V manuel, AIR manuel

# Le circulateur est commandé manuellement par l'opérateur
# =========================
# Main
# =========================

#GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

#MCP
mcp1 = MCP3008_0()
mcp2 = MCP3008_1()

#LCD
lcd = LCDI2C_backpack(0x27)

#74HC595
GPIO.setup((dataPIN, latchPIN, clockPIN), GPIO.OUT, initial=GPIO.LOW)

#PUL moteurs
for pin in motor_map.values():
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

print("Init done.")
log.info("[INFO] Init done.")

time.sleep(0.1)

try:
    print("Lancement du programme")
    try:
        print("=== Programme test => main ===")
        clear_all_shift()
        while True:
            MCP_update_btn()
            if num_prg == 0:
                write_line(lcd, lcd.LCD_LINE_1, "Attente PRG")
                write_line(lcd, lcd.LCD_LINE_2, "Choix 1..5")
                time.sleep(0.5)
                continue
            
            if num_prg == 1:    prg_1()
            elif num_prg == 2:  prg_2()
            elif num_prg == 3:  prg_3()
            elif num_prg == 4:  prg_4()
            elif num_prg == 5:  prg_5()
            
    except KeyboardInterrupt:
        print("\n[STOP] Interruption par l'utilisateur.")
        write_line(lcd, lcd.LCD_LINE_1, "PRG arrete")
        write_line(lcd, lcd.LCD_LINE_2, "CTRL-C detecte")
        time.sleep(2)
        
    except Exception as e:
        log.info(f"EXCEPTION;{e}")
        write_line(lcd, lcd.LCD_LINE_1, "ERROR DETECTE")
        write_line(lcd, lcd.LCD_LINE_2, "FIN DU PROGRAMME")
        print(e)
        sys.exit(1)
    
    finally:
        lcd.clear()
        write_line(lcd, lcd.LCD_LINE_1, "Programme fini")
        write_line(lcd, lcd.LCD_LINE_2, "Arret dans 5s")
        time.sleep(3)
        clear_all_shift()
        mcp1.close(); mcp2.close()
        lcd.clear()
        GPIO.cleanup()

except Exception as e:
    log.info(f"EXCEPTION;{e}")
    print("INIT ERROR :")
    print(e)
    sys.exit(1)

finally:
    log.info("[INFO] Log ended.")
    sys.exit(0)