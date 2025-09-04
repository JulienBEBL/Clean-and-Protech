#!/usr/bin/python3

# === Import ===
import RPi.GPIO as GPIO
import time
from time import monotonic
import os
import logging
from datetime import datetime
from _lib.MCP3008_0 import MCP3008_0
from _lib.MCP3008_1 import MCP3008_1
from _lib.LCDI2C_backpack import LCDI2C_backpack

# === Logger ===
os.makedirs("logs", exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = os.path.join("logs", f"{timestamp}.log")
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s;%(message)s")
log = logging.getLogger("log_prog")
log.info("LOG STARTED")

# === Constantes directions moteur ===
OUVERTURE = "0"
FERMETURE = "1"

# === Variables globales (timings généraux) ===
wait = 0.001
t_step = 0.001
t_maz = 0.002
seuil_mcp = 1000
volume_total_litres = 0.0
btn_state = [0] * 8
selec_state = [0] * 5   # 5 entrées physiques -> positions 1..5 ; 0 == aucune sélection
num_prg = 0
num_selec = 0          # 0..5 (0 = aucune sélection -> position 0)
air_state = 0
pos_V4V_steps = 0      # position actuelle de la V4V en pas depuis le 0 mécanique (après homing)
NB_PAS_O_F = 800

# --- Flag d'état LCD (idle) ---
_idle_prompt_shown = False

# === Paramètres MAZ (Mise A Zéro) ===
NB_PAS_MAZ = 800
NB_PAS_SUR_MAZ = 20

# === V4V : positions (0..5) en pas depuis le 0 mécanique (FERMETURE) ===
# Ajuste ces valeurs selon tes essais (90° répartis sur 6 positions).
# Par défaut: 0 = home, 5 autres positions espacées de manière indicative.
V4V_POS_STEPS = [0, 160, 320, 480, 640, 800]  # <-- à calibrer sur ta machine

# === Air comprimé : modes, état et timings ===
AIR_MODES = [
    {"label": "OFF",     "pulse_s": 0.0, "period_s": 0.0},  # led bit 0
    {"label": "2s",      "pulse_s": 2.0, "period_s": 2.0},  # led bit 1
    {"label": "4s",      "pulse_s": 2.0, "period_s": 4.0},  # led bit 2
    {"label": "CONTINU", "pulse_s": 0.0, "period_s": 0.0},  # led bit 3
]
air_mode = 0
_last_air_button = 0
AIR_FROZEN = False  # gel temporaire pendant mouvements vannes

# === Débitmètre ===
FLOW_SENSOR = 26
pulse_count = 0
last_pulse_count = 0
last_debit_timestamp = monotonic()

# === Moteurs et GPIO ===
GPIO.setmode(GPIO.BCM)

# Mapping et index bitmask (ordre identique à l’ancien m_dir)
motor_map = {
    "V4V": 19, "clientG": 18, "clientD": 15, "egout": 14,
    "boue": 13, "pompeOUT": 12, "cuve": 6, "eau": 5
}
# index de bit (0..7) pour DIR_MASK
BIT_INDEX = { "V4V":0, "clientG":1, "clientD":2, "egout":3,
              "boue":4, "pompeOUT":5, "cuve":6, "eau":7 }

motor = list(motor_map.values())
dataPIN, latchPIN, clockPIN = 21, 20, 16

# --- GPIO pour Air uniquement ---
electrovannePIN = 23   # Air comprimé

GPIO.setup(motor, GPIO.OUT)
GPIO.output(motor, GPIO.LOW)
GPIO.setup((dataPIN, latchPIN, clockPIN, electrovannePIN), GPIO.OUT)
GPIO.output(electrovannePIN, GPIO.LOW)

# === Bitmasks globaux ===
# DIR_MASK: 8 bits de directions (1 = FERMETURE, 0 = OUVERTURE) suivant BIT_INDEX
# LED_MASK: 4 bits (bit = air_mode)
DIR_MASK = 0x00
LED_MASK = 0x01  # air_mode=0 -> bit0 = 1

# === LCD et MCP ===
lcd = LCDI2C_backpack(0x27)
lcd.clear()
lcd.lcd_string("Initialisation", lcd.LCD_LINE_1)
lcd.lcd_string("En cours...",     lcd.LCD_LINE_2)
MCP_1 = MCP3008_0()
MCP_2 = MCP3008_1()

# === Débitmètre callback ===
def countPulse(channel):
    global pulse_count
    pulse_count += 1

GPIO.setup(FLOW_SENSOR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(FLOW_SENSOR, GPIO.FALLING, callback=countPulse)

def calcul_debit_et_volume():
    """Calcul sur l’intervalle depuis la dernière lecture (monotonic)."""
    global last_debit_timestamp, last_pulse_count, pulse_count

    now = monotonic()
    interval = now - last_debit_timestamp
    if interval <= 0:
        return 0.0, 0.0, 0.0

    pulses = pulse_count - last_pulse_count
    frequency = pulses / interval           # Hz
    debit_L_min = frequency / 0.2           # Q[L/min] = f[Hz]/0.2 (datasheet)
    volume = debit_L_min * (interval / 60)  # L

    last_debit_timestamp = now
    last_pulse_count = pulse_count

    log.info(f"[DEBIT] {interval:.1f}s — {volume:.3f} L — {debit_L_min:.2f} L/min — {pulses} pulses")
    return volume, debit_L_min, interval

# === Utilitaires LCD ===
def show_idle_prompt():
    """Affiche une seule fois le prompt 'Choisissez un programme :' quand on est au repos."""
    global _idle_prompt_shown
    if not _idle_prompt_shown:
        lcd.lcd_string("Choisissez un", lcd.LCD_LINE_1)
        lcd.lcd_string("programme :",   lcd.LCD_LINE_2)
        _idle_prompt_shown = True

def afficher_volume_total():
    lcd.lcd_string("Volume total :",        lcd.LCD_LINE_1)
    lcd.lcd_string(f"{volume_total_litres:.2f} L", lcd.LCD_LINE_2)

# === 74HC595 bit-bang (masques) ===
def _shift_send_masks(dir_mask: int, led_mask: int):
    """Envoie 16 bits: [DIR7..DIR0][LED3..LED0][0000], MSB first."""
    word = ((dir_mask & 0xFF) << 8) | ((led_mask & 0x0F) << 4)
    GPIO.output(latchPIN, 0)
    for i in range(15, -1, -1):  # MSB first
        bit = (word >> i) & 1
        GPIO.output(clockPIN, 0)
        GPIO.output(dataPIN, bit)
        GPIO.output(clockPIN, 1)
    GPIO.output(latchPIN, 1)

def _push_595():
    _shift_send_masks(DIR_MASK, LED_MASK)

# === Fonctions air ===
def _apply_air_mode():
    """Applique l'air_mode courant -> met à jour LED_MASK + pousse 595."""
    global LED_MASK
    LED_MASK = (1 << air_mode)
    log.info(f"[AIR] Mode -> {AIR_MODES[air_mode]['label']} "
             f"(pulse={AIR_MODES[air_mode]['pulse_s']}s, period={AIR_MODES[air_mode]['period_s']}s)")
    _push_595()

_ev_on = False  # état interne EV
def updateElectrovanne(state: bool):
    global _ev_on
    GPIO.output(electrovannePIN, GPIO.HIGH if state else GPIO.LOW)
    _ev_on = bool(state)

def _update_air_mode_from_button():
    """Incrémente le mode d'air sur front montant du bouton air_state."""
    global _last_air_button, air_mode
    if air_state == 1 and _last_air_button == 0:
        air_mode = (air_mode + 1) % 4
        _apply_air_mode()
    _last_air_button = air_state

def pulse_air():
    """Injection unique en fonction du mode courant."""
    pulse_s = AIR_MODES[air_mode]["pulse_s"]
    if pulse_s <= 0:
        return
    log.info(f"[AIR] Pulse {pulse_s:.2f}s")
    updateElectrovanne(True)
    time.sleep(pulse_s)
    updateElectrovanne(False)

def freeze_air(enable: bool):
    """Fige l’air pendant manœuvres vannes, puis restaure si nécessaire."""
    global AIR_FROZEN
    if enable:
        if _ev_on:
            updateElectrovanne(False)
        AIR_FROZEN = True
    else:
        AIR_FROZEN = False
        # Restaure le continu si mode=CONTINU
        if air_mode == 3:
            updateElectrovanne(True)

# === Fonctions bas niveau ===
def set_dir(nom_moteur: str, sens: str):
    """Met à jour DIR_MASK pour 'nom_moteur' sans envoyer au 595."""
    global DIR_MASK
    bit = 1 << BIT_INDEX[nom_moteur]
    if sens == OUVERTURE:
        DIR_MASK &= ~bit
    else:
        DIR_MASK |= bit

def move(step_count, nom_moteur, tempo):
    pin = motor_map[nom_moteur]
    out = GPIO.output
    hi, lo = GPIO.HIGH, GPIO.LOW
    sleep = time.sleep
    for _ in range(step_count):
        out(pin, hi); sleep(tempo)
        out(pin, lo); sleep(tempo)

# --- Nouvelles fonctions V4V : homing + positions absolues (0..5) ---
def home_V4V():
    """Homing V4V sur butée mécanique (FERMETURE) -> position 0 pas."""
    global pos_V4V_steps
    freeze_air(True)
    lcd.lcd_string("Vanne 4V:",       lcd.LCD_LINE_1)
    lcd.lcd_string("HOMING...",       lcd.LCD_LINE_2)
    set_dir("V4V", FERMETURE)
    _push_595()
    move(NB_PAS_MAZ, "V4V", t_maz)
    time.sleep(2 * wait)
    move(NB_PAS_SUR_MAZ, "V4V", t_maz)
    pos_V4V_steps = 0
    log.info(f"[V4V] Homing OK -> pos = 0 pas")
    freeze_air(False)

def goto_V4V_position(index: int):
    """Déplacement V4V vers position index (0..5) en pas absolus via V4V_POS_STEPS."""
    global pos_V4V_steps
    if index < 0: index = 0
    if index > 5: index = 5
    target = V4V_POS_STEPS[index]
    delta = target - pos_V4V_steps
    if delta == 0:
        lcd.lcd_string("Vanne 4V:",      lcd.LCD_LINE_1)
        lcd.lcd_string(f"Pos {index} OK", lcd.LCD_LINE_2)
        log.info(f"[V4V] Déjà à la position {index} ({target} pas)")
        return
    sens = OUVERTURE if delta > 0 else FERMETURE
    steps = abs(delta)
    freeze_air(True)
    lcd.lcd_string("Vanne 4V:",        lcd.LCD_LINE_1)
    lcd.lcd_string(f"-> Pos {index}",   lcd.LCD_LINE_2)
    set_dir("V4V", sens)
    _push_595()
    log.info(f"[V4V] Move {pos_V4V_steps} -> {target} ({steps} pas, sens={sens})")
    move(steps, "V4V", t_step)
    pos_V4V_steps = target
    freeze_air(False)
    log.info(f"[V4V] Position {index} atteinte")

# === Groupes de vannes ===
def fermer_toutes_les_vannes_sauf_v4v():
    freeze_air(True)
    for nom in motor_map.keys():
        if nom == "V4V":
            continue
        set_dir(nom, FERMETURE)
    _push_595()
    for nom in motor_map.keys():
        if nom == "V4V":
            continue
        move(NB_PAS_O_F, nom, t_step)
    freeze_air(False)
    log.info("Fermeture de toutes les vannes (sauf V4V) effectuée.")

def transaction_vannes(vannes_ouvertes, vannes_fermees):
    """Fige l’air, pose toutes les directions, push 595 une fois, puis effectue les pas."""
    freeze_air(True)
    # directions groupées
    for v in vannes_ouvertes:
        set_dir(v, OUVERTURE)
    for v in vannes_fermees:
        set_dir(v, FERMETURE)
    _push_595()
    # déplacements
    for v in vannes_ouvertes:
        move(NB_PAS_O_F, v, t_step)
    for v in vannes_fermees:
        move(NB_PAS_O_F, v, t_step)
    freeze_air(False)

# === MCP & IHM ===
def MCP_update():
    global btn_state, num_prg, selec_state, num_selec, air_state
    btn_state  = [1 if MCP_2.read(i) > seuil_mcp else 0 for i in range(8)]
    num_prg    = btn_state.index(1)+1 if sum(btn_state) == 1 else 0
    selec_state= [1 if MCP_1.read(i) > seuil_mcp else 0 for i in range(5)]
    num_selec  = selec_state.index(1) if sum(selec_state) == 1 else 0  # -> 0..5 (0 = aucune)
    air_state  = 1 if MCP_1.read(5) > seuil_mcp else 0
    _update_air_mode_from_button()

def attendre_relachement_boutons():
    lcd.lcd_string("Attente:",        lcd.LCD_LINE_1)
    lcd.lcd_string("Relâcher bouton", lcd.LCD_LINE_2)
    while any(MCP_2.read(i) > seuil_mcp for i in range(8)):
        time.sleep(0.1)

def confirmer_programme(numero):
    lcd.lcd_string(f"Lancer prog {numero} ?", lcd.LCD_LINE_1)
    lcd.lcd_string("Appuyer a nouveau",       lcd.LCD_LINE_2)
    log.info(f"[CONFIRM] Attente confirmation prog {numero}")
    t0 = monotonic()
    while monotonic() - t0 < 10:
        MCP_update()
        if num_prg == numero:
            lcd.lcd_string(f"Programme {numero}", lcd.LCD_LINE_1)
            lcd.lcd_string("CONFIRME",           lcd.LCD_LINE_2)
            log.info(f"[CONFIRM] Programme {numero} confirmé")
            return True
        elif num_prg != 0:
            lcd.lcd_string(f"Programme {numero}", lcd.LCD_LINE_1)
            lcd.lcd_string("ANNULE",             lcd.LCD_LINE_2)
            log.info(f"[CONFIRM] Mauvais bouton — programme {numero} annulé")
            time.sleep(2)
            return False
        time.sleep(0.1)
    lcd.lcd_string(f"Programme {numero}", lcd.LCD_LINE_1)
    lcd.lcd_string("ANNULE",             lcd.LCD_LINE_2)
    log.info(f"[CONFIRM] Timeout — programme {numero} annulé")
    time.sleep(2)
    return False

# === Fonction générique programme (durée forcée à 5 minutes) ===
PROGRAM_DURATION_SEC = 5 * 60

def executer_programme(num, vannes_ouvertes, vannes_fermees):
    global volume_total_litres, _idle_prompt_shown
    _idle_prompt_shown = False
    log.info(f"=== Début du programme {num} ===")
    lcd.lcd_string(f"Programme {num}", lcd.LCD_LINE_1)
    lcd.lcd_string("EN COURS",         lcd.LCD_LINE_2)

    attendre_relachement_boutons()
    MCP_update()  # rafraîchir num_selec juste avant
    # 1) Homing V4V puis 2) aller à la position demandée (0..5)
    home_V4V()
    goto_V4V_position(num_selec)

    # Transaction vannes (air gelé, push unique)
    transaction_vannes(vannes_ouvertes, vannes_fermees)

    t0 = monotonic()
    t_last_pulse = t0
    electrovanne_on_continu = False
    last_mode_seen = air_mode

    try:
        while monotonic() - t0 < PROGRAM_DURATION_SEC:
            MCP_update()

            if not AIR_FROZEN:
                # Changement de mode
                if air_mode != last_mode_seen:
                    log.info(f"[AIR] {AIR_MODES[last_mode_seen]['label']} -> {AIR_MODES[air_mode]['label']}")
                    last_mode_seen = air_mode
                    if electrovanne_on_continu and air_mode != 3:
                        updateElectrovanne(False)
                        electrovanne_on_continu = False
                    t_last_pulse = monotonic()

                # Continu
                if air_mode == 3 and not electrovanne_on_continu:
                    updateElectrovanne(True)
                    electrovanne_on_continu = True

                # Pulsé (2s / 4s)
                if air_mode in (1, 2):
                    period = AIR_MODES[air_mode]["period_s"]
                    if period > 0 and (monotonic() - t_last_pulse) >= period:
                        pulse_air()
                        t_last_pulse = monotonic()

            time.sleep(0.05)

    finally:
        # Stop air continu si actif
        if electrovanne_on_continu:
            updateElectrovanne(False)
        log.info(f"[PRG {num}] Temporisation 1s avant fermeture vannes")
        time.sleep(1)
        fermer_toutes_les_vannes_sauf_v4v()

    volume, debit, interval = calcul_debit_et_volume()
    log.info(f"[PRG {num}] Eau utilisée : {volume:.2f} L en {interval:.1f}s (débit moyen : {debit:.2f} L/min)")
    volume_total_litres += volume
    log.info(f"[PRG {num}] Volume total cumulé = {volume_total_litres:.2f} L")
    afficher_volume_total()
    time.sleep(2)
    log.info(f"=== Fin du programme {num} ===")

# === Programmes (la durée est désormais fixée dans executer_programme) ===
def prg_1(): executer_programme(1, ["eau", "cuve", "pompeOUT", "clientD", "egout"], ["clientG", "boue"])
def prg_2(): executer_programme(2, ["clientD", "boue", "egout"], ["eau", "cuve", "pompeOUT", "clientG"])
def prg_3(): executer_programme(3, ["eau", "clientD", "boue"], ["pompeOUT", "clientG", "egout", "cuve"])
def prg_4(): executer_programme(4, ["cuve", "pompeOUT", "egout"], ["eau", "clientG", "clientD", "boue"])
def prg_5(): executer_programme(5, ["clientG", "cuve", "eau", "egout"], ["pompeOUT", "clientD", "boue"])
def prg_6(): executer_programme(6, ["eau", "cuve"], ["pompeOUT", "clientD", "clientG", "boue", "egout"])

# === Initialisation ===
log.info("Initialisation")
_apply_air_mode()  # met LED_MASK + push 595 (état initial)
updateElectrovanne(False)

lcd.lcd_string("Direction moteur", lcd.LCD_LINE_1)
lcd.lcd_string("RESET",            lcd.LCD_LINE_2)
_push_595()
time.sleep(0.5)

# MAZ de tous les moteurs (y compris V4V pour un 0 « global » à l’allumage)
for nom in motor_map:
    lcd.lcd_string("MAZ moteur :", lcd.LCD_LINE_1)
    lcd.lcd_string(nom,            lcd.LCD_LINE_2)
    # Pour V4V, on remettra de toute façon un homing au début de chaque programme.
    set_dir(nom, FERMETURE)
    _push_595()
    move(NB_PAS_MAZ, nom, t_maz)
    time.sleep(2 * wait)
    move(NB_PAS_SUR_MAZ, nom, t_maz)
    time.sleep(wait)
# Position absolue V4V = 0 pas après MAZ global
pos_V4V_steps = 0

lcd.lcd_string("Initialisation", lcd.LCD_LINE_1)
lcd.lcd_string("OK",             lcd.LCD_LINE_2)
log.info("Initialisation OK")
time.sleep(1)

show_idle_prompt()  # Affiche l’invite d’attente au repos

# === Séquence de sécurité de fin de machine ===
def safe_shutdown():
    """
    Sécurité avant arrêt machine :
      - Electrovanne OFF
      - Fermeture de toutes les vannes (sauf V4V)
      - Affichage du volume total
    """
    try:
        log.info("[SHUTDOWN] Séquence de sécurité : EV OFF, fermeture vannes (sauf V4V)")
        updateElectrovanne(False)
        time.sleep(1)
        fermer_toutes_les_vannes_sauf_v4v()
        afficher_volume_total()
        log.info(f"[SHUTDOWN] Volume total cumulé = {volume_total_litres:.2f} L")
    except Exception as e:
        log.error(f"[SHUTDOWN] Erreur durant la séquence de sécurité: {e}")

# === Boucle principale ===
try:
    while True:
        MCP_update()
        _push_595()

        if num_prg == 0:
            show_idle_prompt()
        else:
            _idle_prompt_shown = False

        if   num_prg == 1 and confirmer_programme(1): prg_1()
        elif num_prg == 2 and confirmer_programme(2): prg_2()
        elif num_prg == 3 and confirmer_programme(3): prg_3()
        elif num_prg == 4 and confirmer_programme(4): prg_4()
        elif num_prg == 5 and confirmer_programme(5): prg_5()
        elif num_prg == 6 and confirmer_programme(6): prg_6()

        time.sleep(0.1)

except KeyboardInterrupt:
    log.warning("EXIT BY CTRL-C")
except Exception as e:
    log.error(f"EXIT BY ERROR: {e}")
finally:
    # Sécurité complète avant extinction + affichage total
    safe_shutdown()
    time.sleep(10)  # laisser l’opérateur lire l’écran
    # Remise à 0 des registres (éteindre les LEDs air)
    _shift_send_masks(0x00, 0x00)
    MCP_1.close()
    MCP_2.close()
    GPIO.cleanup()
    # Ne pas effacer l'écran immédiatement pour laisser le volume affiché
    log.info("END OF PRG")
    time.sleep(wait)
