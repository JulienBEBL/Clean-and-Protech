#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
CleanProtect_v4.py — Version Professionnelle (Niveau 2)

Optimisations incluses :
- Mise en forme propre
- Renommages cohérents
- Structure logique par sections
- Filtres anti-bruit robustes
- Aucun changement fonctionnel
"""

# ============================================================
# =============== IMPORTATIONS & CHARGEMENT ===================
# ============================================================

import os
import sys
import time
import logging
from datetime import datetime

import RPi.GPIO as GPIO

from libs_tests.MCP3008_0 import MCP3008_0
from libs_tests.MCP3008_1 import MCP3008_1
from libs_tests.LCDI2C_backpack import LCDI2C_backpack


# ============================================================
# =============== MODULE FILTRE BOUTONS MCP ===================
# ============================================================

class MCPButtonFilter:
    def __init__(self, mcp, channel_count=8,
                 seuil_haut=1000, seuil_bas=700,
                 samples=15, stable_ms=300):

        self.mcp = mcp
        self.N = channel_count
        self.samples = samples
        self.seuil_haut = seuil_haut
        self.seuil_bas = seuil_bas
        self.stable_ms = stable_ms / 1000.0

        self.raw_values = [0] * self.N
        self.state = [0] * self.N
        self.last_change_ts = [0] * self.N

    def read_raw_avg(self, ch):
        total = 0
        for _ in range(self.samples):
            total += self.mcp.read(ch)
        return total // self.samples

    def update(self):
        now = time.monotonic()

        for ch in range(self.N):

            v = self.read_raw_avg(ch)
            self.raw_values[ch] = v

            target_state = self.state[ch]
            if v > self.seuil_haut:
                target_state = 1
            elif v < self.seuil_bas:
                target_state = 0

            if target_state != self.state[ch]:
                if self.last_change_ts[ch] == 0:
                    self.last_change_ts[ch] = now
                elif now - self.last_change_ts[ch] >= self.stable_ms:
                    self.state[ch] = target_state
                    self.last_change_ts[ch] = 0
            else:
                self.last_change_ts[ch] = 0

        return self.state

    def get_single_pressed(self):
        st = self.update()
        if st.count(1) == 1:
            return st.index(1) + 1
        return 0


# ============================================================
# =============== MODULE FILTRE SELECTEUR V4V =================
# ============================================================

class MCPSelectorFilter:
    def __init__(self, mcp, channel_count=5,
                 seuil_haut=1000, seuil_bas=700,
                 samples=15, stable_ms=300):

        self.mcp = mcp
        self.N = channel_count
        self.samples = samples
        self.seuil_haut = seuil_haut
        self.seuil_bas = seuil_bas
        self.stable_ms = stable_ms / 1000.0

        self.raw_values = [0] * self.N
        self.state = [0] * self.N
        self.last_change_ts = [0] * self.N

    def read_raw_avg(self, ch):
        total = 0
        for _ in range(self.samples):
            total += self.mcp.read(ch)
        return total // self.samples

    def update(self):
        now = time.monotonic()

        for ch in range(self.N):

            v = self.read_raw_avg(ch)
            self.raw_values[ch] = v

            target_state = self.state[ch]
            if v > self.seuil_haut:
                target_state = 1
            elif v < self.seuil_bas:
                target_state = 0

            if target_state != self.state[ch]:
                if self.last_change_ts[ch] == 0:
                    self.last_change_ts[ch] = now
                elif now - self.last_change_ts[ch] >= self.stable_ms:
                    self.state[ch] = target_state
                    self.last_change_ts[ch] = 0
            else:
                self.last_change_ts[ch] = 0

        if self.state.count(1) == 1:
            return self.state.index(1)

        return None


# ============================================================
# ======================== LOGGING ============================
# ============================================================

os.makedirs("logs", exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = os.path.join("logs", f"{timestamp}.log")

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s;%(message)s"
)

log = logging.getLogger("log_prog")
log.info("[INFO] Log started.")


# ============================================================
# ===================== CONSTANTES ============================
# ============================================================

STEPS = 1100
STEPS_HOME_V4V = 1200
STEP_DELAY = 0.005

DIR_CLOSE = 1
DIR_OPEN = 0

AIR_ON = True
AIR_OFF = False
V4V_ON = True
V4V_OFF = False

LCD_WIDTH = 16

V4V_MANUAL_WINDOW_SECONDS = 5

exit_code = 0

prev_selector_index = None
current_v4v_pos = None


# ============================================================
# ===================== PINOUT HARDWARE =======================
# ============================================================

DATA_PIN = 21
LATCH_PIN = 20
CLOCK_PIN = 16

bits_dir = [0] * 8
bits_blank = [0] * 4
bits_leds = [0] * 4

motor_map = {
    "V4V": 26,
    "clientG": 17,
    "clientD": 6,
    "egout": 13,
    "boue": 27,
    "pompeOUT": 22,
    "cuve": 5,
    "eau": 19
}

SELECT_TO_STEPS = {
    0: 0,
    1: 200,
    2: 400,
    3: 600,
    4: 800
}

PROGRAM_NAMES = {
    1: "Premiere vidange",
    2: "Vidange cuve",
    3: "Sechage",
    4: "Remplissage cuve",
    5: "Desembouage",
}

POS_V4V_PRG = {
    1: 0,
    2: 400,
    3: 0,
    4: 400,
}

# ============================================================

# ============================================================
# ======================= UTILITAIRES LCD =====================
# ============================================================

def write_line(lcd, line, text):
    """Écrit une ligne formatée sur le LCD."""
    lcd.lcd_string(str(text).ljust(LCD_WIDTH)[:LCD_WIDTH], line)


# ============================================================
# ==================== SHIFT REGISTER 74HC595 =================
# ============================================================

def _bits_to_str(bits16):
    if len(bits16) != 16:
        raise ValueError(f"Expected 16 bits, got {len(bits16)}")
    return "".join("1" if int(b) else "0" for b in bits16)

def shift_update(bits_str, data_pin, clock_pin, latch_pin):
    """Envoie 16 bits au registre 74HC595."""
    GPIO.output(clock_pin, 0)
    GPIO.output(latch_pin, 0)
    GPIO.output(clock_pin, 1)

    for i in range(15, -1, -1):
        GPIO.output(clock_pin, 0)
        GPIO.output(data_pin, int(bits_str[i]))
        GPIO.output(clock_pin, 1)

    GPIO.output(clock_pin, 0)
    GPIO.output(latch_pin, 1)
    GPIO.output(clock_pin, 1)

    log.info(f"[74HC595] SHIFT SENT : {bits_str}")

def push_shift():
    bits_str = _bits_to_str(bits_dir + bits_blank + bits_leds)
    shift_update(bits_str, DATA_PIN, CLOCK_PIN, LATCH_PIN)

def clear_all_shift():
    """Éteint LEDs et réinitialise DIR/BLANK."""
    for i in range(8):
        bits_dir[i] = 0
    for i in range(4):
        bits_blank[i] = 0
        bits_leds[i] = 0
    push_shift()

def set_all_leds(val):
    """Allume ou éteint toutes les LEDs."""
    for i in range(4):
        bits_leds[i] = 1 if val else 0
    push_shift()

def set_all_dir(value):
    """Fixe la direction de tous les moteurs."""
    bits_dir[:] = [value] * 8
    push_shift()

# ============================================================
# ======================= MOTEURS PAS À PAS ===================
# ============================================================

def pulse_steps(pul_pin, steps, delay_s):
    """Génère 'steps' impulsions sur un pin PUL."""
    for _ in range(steps):
        GPIO.output(pul_pin, GPIO.HIGH)
        time.sleep(delay_s)
        GPIO.output(pul_pin, GPIO.LOW)
        time.sleep(delay_s)

def move_motor(name, steps, delay_s):
    """Fait bouger un moteur identifié par son nom."""
    pul = motor_map[name]
    print(f"[MOTOR] {name:8s} | DIR={bits_dir} | PUL GPIO {pul} | {steps} pas")

    pulse_steps(pul, steps, delay_s)
    log.info(f"[MOTOR] {name};{steps};{delay_s}")

def home_v4v():
    """Ramène la V4V en position 0 (fermeture)."""
    global current_v4v_pos
    set_all_dir(DIR_CLOSE)
    move_motor("V4V", STEPS_HOME_V4V, STEP_DELAY)
    current_v4v_pos = 0


def _pulse_steps(pul_pin, steps):
    """Version interne avec STEP_DELAY global."""
    for _ in range(steps):
        GPIO.output(pul_pin, 1)
        time.sleep(STEP_DELAY)
        GPIO.output(pul_pin, 0)
        time.sleep(STEP_DELAY)


def goto_v4v_steps(target_steps):
    """Atteint une position absolue V4V."""
    global current_v4v_pos

    if current_v4v_pos is None:
        raise RuntimeError("V4V non référencée. Appeler home_v4v() d’abord.")

    delta = target_steps - current_v4v_pos
    if delta == 0:
        return

    if delta > 0:
        set_all_dir(DIR_OPEN)
        _pulse_steps(motor_map["V4V"], delta)
        log.info(f"V4V moved {delta} steps (OPEN)")
    else:
        set_all_dir(DIR_CLOSE)
        _pulse_steps(motor_map["V4V"], -delta)
        log.info(f"V4V moved {delta} steps (CLOSE)")

    current_v4v_pos = target_steps


# ============================================================
# ======================= BOUTONS PROGRAMMES ==================
# ============================================================

def MCP_update_btn():
    """Lit les boutons via filtre anti-bruit."""
    global num_prg
    num_prg = btn_filter.get_single_pressed()
    log.debug(f"[BTN] num_prg={num_prg}; raw={btn_filter.raw_values}")


# ============================================================
# ======================= SÉLECTEUR V4V ========================
# ============================================================

def update_v4v_from_selector():
    """Met à jour la V4V selon la position du sélecteur."""
    global prev_selector_index

    idx = selector_filter.update()
    if idx is None:
        return

    if idx == prev_selector_index:
        return

    target = SELECT_TO_STEPS[idx]
    print(f"[V4V] Sélecteur -> index {idx}, target={target} pas")
    log.info(f"[V4V] SELECT_STABLE idx={idx}, target={target}")

    goto_v4v_steps(target)
    prev_selector_index = idx

# ============================================================
# ======================== PROGRAMMES =========================
# ============================================================

def start_programme(num: int, to_open: list, to_close: list,
                    air_mode: bool, v4v_manual_mode: bool):
    """
    Lance un programme CleanProtect :
    - Affichage LCD
    - Séquence ouverture/fermeture moteurs
    - Positionnement auto/manu V4V
    - Boucle principale avec chrono & arrêt utilisateur
    """

    def mmss(seconds):
        """Format mm:ss."""
        seconds = max(0, int(seconds))
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    # Écran d’accueil
    print(f"[PRG START] Programme {num}")
    log.info(f"PRG_START;{num};to_open={to_open};to_close={to_close};air_mode={air_mode};v4v_manual={v4v_manual_mode}")

    lcd.clear()
    prg_name = PROGRAM_NAMES.get(num, f"Programme {num}")

    write_line(lcd, lcd.LCD_LINE_1, f"Programme {num}")
    write_line(lcd, lcd.LCD_LINE_2, prg_name)
    time.sleep(5)

    # ------------------------------------------------------------
    #                1) PHASE D’OUVERTURE DES MOTEURS
    # ------------------------------------------------------------
    write_line(lcd, lcd.LCD_LINE_2, "Ouverture...")
    print("[SEQUENCE] OUVERTURE")
    log.info(f"PRG_OPEN;{num};targets={to_open}")

    for name in to_open:
        set_all_dir(DIR_OPEN)
        move_motor(name, STEPS, STEP_DELAY)

    # ------------------------------------------------------------
    #                2) PHASE DE FERMETURE DES MOTEURS
    # ------------------------------------------------------------
    write_line(lcd, lcd.LCD_LINE_2, "Fermeture...")
    print("[SEQUENCE] FERMETURE")
    log.info(f"PRG_CLOSE;{num};targets={to_close}")

    for name in to_close:
        set_all_dir(DIR_CLOSE)
        move_motor(name, STEPS, STEP_DELAY)

    # ------------------------------------------------------------
    #                3) POSITIONNEMENT DE LA V4V
    # ------------------------------------------------------------
    lcd.clear()

    if not v4v_manual_mode:
        # Mode auto : position V4V basée sur tableau
        write_line(lcd, lcd.LCD_LINE_1, "V4V : mode auto")
        target = POS_V4V_PRG.get(num)

        if target is None:
            print(f"[V4V] Pas de consigne pour programme {num}")
        else:
            write_line(lcd, lcd.LCD_LINE_2, "Référence V4V...")
            home_v4v()

            write_line(lcd, lcd.LCD_LINE_2, f"V4V -> {target} pas")
            try:
                goto_v4v_steps(target)
                write_line(lcd, lcd.LCD_LINE_2, "V4V Prete")
            except Exception as e:
                print(f"[V4V] ERREUR : {e}")

    else:
        # Mode manuel V4V
        write_line(lcd, lcd.LCD_LINE_1, "V4V : mode manuel")
        time.sleep(2)

        write_line(lcd, lcd.LCD_LINE_1, "Choisissez une")
        write_line(lcd, lcd.LCD_LINE_2, f"position ({V4V_MANUAL_WINDOW_SECONDS}s)")
        time.sleep(V4V_MANUAL_WINDOW_SECONDS)

        # Référence physique
        print("[V4V] Référencement...")
        home_v4v()
        print("[V4V] Référence OK")

        write_line(lcd, lcd.LCD_LINE_1, "Déplacement...")
        write_line(lcd, lcd.LCD_LINE_2, "V4V en cours")

        update_v4v_from_selector()
        print("[V4V] Position manuelle figée")

        # ------------------------------------------------------------
    #                4) BOUCLE PRINCIPALE / CHRONO
    # ------------------------------------------------------------
    start_ts = time.monotonic()
    last_sec_display = -1
    next_v4v_update = start_ts + 5  # mise à jour périodique

    # IMPORTANT : on initialise l'état précédent du bouton
    MCP_update_btn()
    prev_btn_state = (num_prg == num)

    log.info(f"PRG_RUN;{num}")

    write_line(lcd, lcd.LCD_LINE_1, f"Programme {num}")

    while True:
        now = time.monotonic()
        elapsed = int(now - start_ts)

        # Affichage
        if elapsed != last_sec_display:
            write_line(lcd, lcd.LCD_LINE_1, f"Programme {num}")
            write_line(lcd, lcd.LCD_LINE_2, f"{mmss(elapsed)} X L/m")
            last_sec_display = elapsed

        # V4V auto...
        if not v4v_manual_mode and now >= next_v4v_update:
            try:
                update_v4v_from_selector()
                log.info(f"V4V_AUTO_UPDATE;{num};elapsed={elapsed}")
                next_v4v_update += 5
            except Exception as e:
                print("Erreur V4V auto : ", e)
                log.exception("V4V_UPDATE_ERROR", exc_info=e)
                global exit_code
                exit_code = 1

        # Bouton d'arrêt
        MCP_update_btn()
        is_pressed = (num_prg == num)

        if is_pressed and not prev_btn_state:
            lcd.lcd_string(f"Programme {num}", lcd.LCD_LINE_1)
            lcd.lcd_string("Arret demande", lcd.LCD_LINE_2)
            log.info(f"PRG_STOP;{num};elapsed={elapsed}")
            print(f"[PRG] Arrêt demandé après {elapsed}s")
            time.sleep(2)
            break

        prev_btn_state = is_pressed
        time.sleep(0.1)



# ============================================================
# ======================= PROGRAMMES 1 À 5 ====================
# ============================================================

def prg_1():
    start_programme(
        1,
        ["clientG", "clientD", "boue"],
        ["eau", "cuve", "egout", "pompeOUT"],
        air_mode=AIR_ON,
        v4v_manual_mode=V4V_OFF
    )


def prg_2():
    start_programme(
        2,
        ["cuve", "egout", "pompeOUT"],
        ["clientG", "boue", "clientD", "eau"],
        air_mode=AIR_OFF,
        v4v_manual_mode=V4V_OFF
    )


def prg_3():
    start_programme(
        3,
        ["clientD", "clientG", "egout"],
        ["pompeOUT", "eau", "cuve", "boue"],
        air_mode=AIR_ON,
        v4v_manual_mode=V4V_OFF
    )


def prg_4():
    start_programme(
        4,
        ["eau", "pompeOUT", "boue"],
        ["cuve", "egout", "clientG", "clientD"],
        air_mode=AIR_OFF,
        v4v_manual_mode=V4V_OFF
    )


def prg_5():
    start_programme(
        5,
        ["cuve", "pompeOUT", "clientG", "clientD", "boue"],
        ["egout", "eau"],
        air_mode=AIR_ON,
        v4v_manual_mode=V4V_ON
    )


# ============================================================
# ===================== INITIALISATIONS =======================
# ============================================================

log.info("[INFO] Initialisation hardware...")
print("Initialisation hardware...")

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# MCP
mcp1 = MCP3008_0()
mcp2 = MCP3008_1()

btn_filter = MCPButtonFilter(mcp2, 8, 1000, 400, 8, 120)
selector_filter = MCPSelectorFilter(mcp1, 5, 1000, 400, 8, 120)

log.info("[INFO] Filtres MCP initialisés.")

# LCD
lcd = LCDI2C_backpack(0x27)

# Shift register
GPIO.setup((DATA_PIN, LATCH_PIN, CLOCK_PIN), GPIO.OUT, initial=GPIO.LOW)

# Moteurs
for pin in motor_map.values():
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

print("Init terminée.")
log.info("[INFO] Init terminée.")

time.sleep(0.5)


# ============================================================
# ========================= MAIN LOOP =========================
# ============================================================

try:
    print("Lancement du programme principal...")
    log.info("[INFO] Programme main démarré.")

    clear_all_shift()

    last_num_prg = 0  # mémorise le dernier programme vu (pour détecter le front)

    while True:
        MCP_update_btn()

        # Aucun bouton appuyé : on est en attente, on réarme la détection
        if num_prg == 0:
            if last_num_prg != 0:
                log.debug(f"[MAIN] Retour en attente, last_num_prg={last_num_prg} -> 0")
            last_num_prg = 0

            write_line(lcd, lcd.LCD_LINE_1, "Attente PRG")
            write_line(lcd, lcd.LCD_LINE_2, "Choix 1..5")
            time.sleep(0.1)
            continue

        # Ici, num_prg != 0
        # Tant que le même bouton reste appuyé, on NE relance PAS de programme.
        if num_prg == last_num_prg:
            # Pas de nouveau front, on ignore
            time.sleep(0.1)
            continue

        # Nouveau front montant global : un nouveau programme vient d'être choisi
        log.info(f"[MAIN] Nouveau programme sélectionné : {num_prg}")
        last_num_prg = num_prg

        time.sleep(0.05)  # petite pause avant le lancement

        if num_prg == 1:
            prg_1()
        elif num_prg == 2:
            prg_2()
        elif num_prg == 3:
            prg_3()
        elif num_prg == 4:
            prg_4()
        elif num_prg == 5:
            prg_5()


except KeyboardInterrupt:
    log.info("[INFO] Interruption utilisateur.")
    print("\n[STOP] CTRL-C détecté.")
    write_line(lcd, lcd.LCD_LINE_1, "PRG arrêté")
    write_line(lcd, lcd.LCD_LINE_2, "CTRL-C détecté")
    exit_code = 0
    time.sleep(2)

except Exception as e:
    log.exception("MAIN ERROR", exc_info=e)
    print("ERREUR FATALE :", e)
    exit_code = 1

finally:
    lcd.clear()
    write_line(lcd, lcd.LCD_LINE_1, "Programme fini")
    write_line(lcd, lcd.LCD_LINE_2, "Arrêt dans 5s")
    time.sleep(3)

    clear_all_shift()
    mcp1.close()
    mcp2.close()
    lcd.clear()
    GPIO.cleanup()

    log.info("[INFO] Log ended.")
    print("Log ended.")
    sys.exit(exit_code)
