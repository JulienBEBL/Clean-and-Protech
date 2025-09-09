#!/usr/bin/python3
# -*- coding: utf-8 -*-

# =========================
# IMPORTS & LOGGING
# =========================
import RPi.GPIO as GPIO
import time
from time import monotonic
import os
import logging
from datetime import datetime
from enum import IntEnum 
from libs.MCP3008_0 import MCP3008_0
from libs.MCP3008_1 import MCP3008_1
from libs.LCDI2C_backpack import LCDI2C_backpack

os.makedirs("logs", exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = os.path.join("logs", f"{timestamp}.log")
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s;%(message)s")
log = logging.getLogger("log_prog")
log.info("LOG STARTED")

# =========================
# CONSTANTES & CONFIG GLOBALES
# =========================

# (6) Directions via Enum (évite les chaînes "0"/"1")
class Sens(IntEnum):
    OUVERTURE = 0
    FERMETURE = 1

# Timings généraux
wait   = 0.001
t_step = 0.001
t_maz  = 0.002
seuil_mcp = 1000

# Pas / déplacements
STEP_MAZ        = 800
STEP_MICRO_MAZ  = 20
STEP_MOVE       = 800

# Durée fixe des programmes (proto)
PROGRAM_DURATION_SEC = 5 * 60

# V4V : positions absolues (0..5) en pas depuis 0 mécanique
V4V_POS_STEPS = [0, 160, 320, 480, 640, 800]

# Air : modes / leds
AIR_MODES = [
    {"label": "OFF",     "pulse_s": 0.0, "period_s": 0.0},  # bit LED 0
    {"label": "2s",      "pulse_s": 2.0, "period_s": 2.0},  # bit LED 1
    {"label": "4s",      "pulse_s": 2.0, "period_s": 4.0},  # bit LED 2
    {"label": "CONTINU", "pulse_s": 0.0, "period_s": 0.0},  # bit LED 3
]

# États / variables globales
volume_total_litres = 0.0
btn_state   = [0] * 8
selec_state = [0] * 5
num_prg     = 0
num_selec   = 0         # 0..5 (0 = aucune sélection -> position 0)
air_state   = 0
pos_V4V_steps = 0       # position actuelle (pas depuis 0 mécanique)
_idle_prompt_shown = False
air_mode = 0
_last_air_button = 0
AIR_FROZEN = False

# Débitmètre
FLOW_SENSOR = 15
pulse_count = 0
last_pulse_count = 0
last_debit_timestamp = monotonic()

# (logger débit) — throttle temps/variation
FLOW_LOG_EVERY_S = 2.0       # log au moins toutes X secondes
FLOW_LOG_DELTA_FRAC = 0.05   # ≥ ±5%
_flow_log_last_t = 0.0
_flow_log_last_q = None

# LCD alternance pendant exécution
_display_toggle = False   # False -> écran A (prog + temps), True -> écran B (débit + volume)
_last_display_switch = 0.0
DISPLAY_PERIOD_S = 1.0    # alternance toutes les 1s
_last_instant_debit = 0.0 # L/min (pour affichage en cours)

# =========================
# GPIO PINS & SETUP
# =========================
GPIO.setmode(GPIO.BCM)

# Moteurs (STEP pins sur sorties directes)
motor_map = {
    "V4V": 17, "clientG": 27, "clientD": 22, "egout": 5,
    "boue": 6, "pompeOUT": 13, "cuve": 19, "eau": 26
}
BIT_INDEX = { "V4V":0, "clientG":1, "clientD":2, "egout":3,
              "boue":4, "pompeOUT":5, "cuve":6, "eau":7 }

motor = list(motor_map.values())
GPIO.setup(motor, GPIO.OUT)
GPIO.output(motor, GPIO.LOW)

# 74HC595 (data/latch/clock)
dataPIN, latchPIN, clockPIN = 21, 20, 16
GPIO.setup((dataPIN, latchPIN, clockPIN), GPIO.OUT)

# Air comprimé (relais)
electrovannePIN = 14
GPIO.setup(electrovannePIN, GPIO.OUT)
GPIO.output(electrovannePIN, GPIO.LOW)

# Débitmètre
def countPulse(channel):
    global pulse_count
    pulse_count += 1

GPIO.setup(FLOW_SENSOR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(FLOW_SENSOR, GPIO.FALLING, callback=countPulse)

# =========================
# ÉTATS 74HC595 (REGISTRE À DÉCALAGE)
# =========================

# DIR_MASK: 8 bits direction (1=FERMETURE, 0=OUVERTURE) selon l’ordre BIT_INDEX
# LED_MASK: 4 bits LED (exactement 1 bit actif: celui de air_mode)

DIR_MASK = 0x00
LED_MASK = 0x01  # air_mode=0

# (4) Version optimisée bit-banging (mêmes broches)
def update_shift_register(new_dir_mask=None, new_led_mask=None):

    global DIR_MASK, LED_MASK

    if new_dir_mask is not None:
        DIR_MASK = new_dir_mask & 0xFF
    if new_led_mask is not None:
        LED_MASK = new_led_mask & 0x0F

    word = (DIR_MASK << 8) | (LED_MASK << 4)

    out = GPIO.output
    d = dataPIN
    c = clockPIN
    l = latchPIN

    # LATCH bas pendant le shift
    out(l, 0)

    # MSB -> LSB
    for i in range(15, -1, -1):
        bit = (word >> i) & 1
        out(c, 0)
        out(d, bit)
        out(c, 1)

    # LATCH haut : validation d'un coup (glitch-free)
    out(l, 1)

# =========================
# LCD & MCP3008 INIT
# =========================

lcd = LCDI2C_backpack(0x27)
lcd.clear()
lcd.lcd_string("Initialisation", lcd.LCD_LINE_1)
lcd.lcd_string("En cours...",     lcd.LCD_LINE_2)

MCP_1 = MCP3008_0()
MCP_2 = MCP3008_1()

# =========================
# OUTILS LCD / AFFICHAGES
# =========================

def show_idle_prompt():
    """Affiche une seule fois le prompt d’attente."""
    global _idle_prompt_shown
    if not _idle_prompt_shown:
        lcd.clear()
        lcd.lcd_string("Choisissez un", lcd.LCD_LINE_1)
        lcd.lcd_string("programme :",   lcd.LCD_LINE_2)
        _idle_prompt_shown = True

def afficher_volume_total():
    lcd.clear()
    lcd.lcd_string("Volume total :", lcd.LCD_LINE_1)
    lcd.lcd_string(f"{volume_total_litres:.2f} L", lcd.LCD_LINE_2)

def _fmt_mmss(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"

def update_run_display(num_prog: int, start_t: float, now_t: float):
    
    # Affichage alterné pendant l’exécution d’un programme
    global _display_toggle, _last_display_switch
    if (now_t - _last_display_switch) >= DISPLAY_PERIOD_S:
        _display_toggle = not _display_toggle
        _last_display_switch = now_t
        lcd.clear()

    elapsed = int(now_t - start_t)
    remain  = max(0, PROGRAM_DURATION_SEC - elapsed)

    if not _display_toggle:
        # Écran A
        lcd.lcd_string(f"Programme {num_prog}", lcd.LCD_LINE_1)
        lcd.lcd_string(f"Total 05:00  R:{_fmt_mmss(remain)}", lcd.LCD_LINE_2)
    else:
        # Écran B
        lcd.lcd_string(f"Debit {_last_instant_debit:4.1f} L/min", lcd.LCD_LINE_1)
        lcd.lcd_string(f"Total {volume_total_litres:6.2f} L",     lcd.LCD_LINE_2)

# =========================
# AIR (RELAIS + LEDS)
# =========================

_ev_on = False

def _apply_air_mode():
    """Met à jour les LEDs d’air en fonction de air_mode."""
    new_led = (1 << air_mode)
    update_shift_register(new_led_mask=new_led)
    log.info(f"[AIR] Mode -> {AIR_MODES[air_mode]['label']} "
             f"(pulse={AIR_MODES[air_mode]['pulse_s']}s, period={AIR_MODES[air_mode]['period_s']}s)")

def updateElectrovanne(state: bool):
    global _ev_on
    GPIO.output(electrovannePIN, GPIO.HIGH if state else GPIO.LOW)
    _ev_on = bool(state)

def _update_air_mode_from_button():
    """Front montant sur air_state -> mode suivant."""
    global _last_air_button, air_mode
    if air_state == 1 and _last_air_button == 0:
        air_mode = (air_mode + 1) % 4
        _apply_air_mode()
    _last_air_button = air_state

# Air non bloquant : machine à états
_air_next_toggle = 0.0
_air_mode_prev = None

def air_tick_non_blocking(now):
    """
    Met à jour l'électrovanne (EV) selon air_mode sans blocage.
    Gère OFF / CONTINU / pulsatiles (2s, 4s).
    Respecte AIR_FROZEN (force OFF pendant gel).
    """
    global _air_next_toggle, _air_mode_prev, _ev_on

    if AIR_FROZEN:
        if _ev_on:
            updateElectrovanne(False)
        _air_next_toggle = now  # réarmement immédiat à la sortie du freeze
        _air_mode_prev = air_mode
        return

    # changement de mode -> RAZ état EV + échéance
    if _air_mode_prev != air_mode:
        _air_mode_prev = air_mode
        if _ev_on:
            updateElectrovanne(False)
        _air_next_toggle = now

    mode_label = AIR_MODES[air_mode]["label"]

    if mode_label == "OFF":
        if _ev_on:
            updateElectrovanne(False)
        return

    if mode_label == "CONTINU":
        if not _ev_on:
            updateElectrovanne(True)
        return

    on_s   = AIR_MODES[air_mode]["pulse_s"]
    period = AIR_MODES[air_mode]["period_s"]

    if now >= _air_next_toggle:
        if _ev_on:
            # ON -> OFF pour le repos (period - on_s)
            updateElectrovanne(False)
            _air_next_toggle = now + max(0.05, period - on_s)
        else:
            # OFF -> ON pour l'impulsion (on_s)
            updateElectrovanne(True)
            _air_next_toggle = now + on_s

def pulse_air():
    """(obsolète) Conservée pour compat. — l'air pulsé est géré par air_tick_non_blocking()."""
    pass

def freeze_air(enable: bool):
    """Gèle l’air durant manœuvres (sécurité), restaure le continu ensuite."""
    global AIR_FROZEN
    if enable:
        if _ev_on:
            updateElectrovanne(False)
        AIR_FROZEN = True
    else:
        AIR_FROZEN = False
        if AIR_MODES[air_mode]["label"] == "CONTINU":
            updateElectrovanne(True)

# =========================
# BAS NIVEAU MOTEURS
# =========================

def set_dir(nom_moteur: str, sens: Sens):
    """Ajuste DIR_MASK pour un moteur, sans envoyer (Enum Sens)."""
    bit = 1 << BIT_INDEX[nom_moteur]
    new_mask = DIR_MASK
    if sens == Sens.OUVERTURE:
        new_mask &= ~bit
    else:
        new_mask |= bit
    update_shift_register(new_dir_mask=new_mask)

def move(step_count, nom_moteur, tempo):
    """Génère des impulsions STEP sur le moteur ciblé (bloquant — OK pour proto)."""
    pin = motor_map[nom_moteur]
    out = GPIO.output
    hi, lo = GPIO.HIGH, GPIO.LOW
    sleep = time.sleep
    for _ in range(step_count):
        out(pin, hi); sleep(tempo)
        out(pin, lo); sleep(tempo)

# =========================
# V4V : HOMING & POSITIONS ABSOLUES
# =========================

def home_V4V():
    """
    Homing "soft" sans capteur:
      1) Approche lente vers FERMETURE par paquets,
      2) Sur-course courte (assure le contact),
      3) Backoff en OUVERTURE pour libérer la butée,
      4) pos_V4V_steps = 0.

    Ajuster BACKOFF_STEPS si nécessaire.
    """
    global pos_V4V_steps
    BACKOFF_STEPS = 40              # à ajuster (5..80)
    CHUNKS = 10                     # homing en CHUNKS parties
    tempo_approche = t_maz * 1.5    # plus lent que MAZ brut
    tempo_finition = t_maz * 2.0    # encore plus lent pour la touche finale

    freeze_air(True)
    lcd.clear()
    lcd.lcd_string("Vanne 4V:", lcd.LCD_LINE_1)
    lcd.lcd_string("HOMING soft...", lcd.LCD_LINE_2)

    # 1) Approche lente par paquets (réduit le risque de décrochage)
    set_dir("V4V", Sens.FERMETURE)
    pas_total = STEP_MAZ
    pas_chunk = max(1, pas_total // CHUNKS)
    for _ in range(CHUNKS):
        move(pas_chunk, "V4V", tempo_approche)
        time.sleep(0.05)  # micro repos mécanique

    # 2) Sur-course douce en micro-pas (assure la prise d'origine)
    move(STEP_MICRO_MAZ, "V4V", tempo_finition)
    time.sleep(0.05)

    # 3) Backoff pour libérer la butée
    set_dir("V4V", Sens.OUVERTURE)
    move(BACKOFF_STEPS, "V4V", tempo_finition)

    # 4) Zéro logique
    pos_V4V_steps = 0
    log.info(f"[V4V] Homing soft OK -> pos = 0 (backoff {BACKOFF_STEPS} pas)")
    freeze_air(False)

def goto_V4V_position(index: int):
    """Déplacement V4V vers position index (0..5) absolue."""
    global pos_V4V_steps
    if index < 0: index = 0
    if index > 5: index = 5
    target = V4V_POS_STEPS[index]
    delta  = target - pos_V4V_steps
    if delta == 0:
        lcd.clear()
        lcd.lcd_string("Vanne 4V:",      lcd.LCD_LINE_1)
        lcd.lcd_string(f"Pos {index} OK", lcd.LCD_LINE_2)
        log.info(f"[V4V] Déjà à la position {index} ({target} pas)")
        return
    sens  = Sens.OUVERTURE if delta > 0 else Sens.FERMETURE
    steps = abs(delta)
    freeze_air(True)
    lcd.clear()
    lcd.lcd_string("Vanne 4V:",      lcd.LCD_LINE_1)
    lcd.lcd_string(f"-> Pos {index}", lcd.LCD_LINE_2)
    set_dir("V4V", sens)
    log.info(f"[V4V] Move {pos_V4V_steps} -> {target} ({steps} pas, sens={sens})")
    move(steps, "V4V", t_step)
    pos_V4V_steps = target
    freeze_air(False)
    log.info(f"[V4V] Position {index} atteinte")

# =========================
# GROUPES / TRANSACTIONS DE VANNES
# =========================

def fermer_toutes_les_vannes_sauf_v4v():
    freeze_air(True)
    # poser directions fermetures en lot
    for nom in motor_map.keys():
        if nom == "V4V": continue
        set_dir(nom, Sens.FERMETURE)
    # déplacements
    for nom in motor_map.keys():
        if nom == "V4V": continue
        move(STEP_MOVE, nom, t_step)
    freeze_air(False)
    log.info("Fermeture de toutes les vannes (sauf V4V) effectuée.")

def transaction_vannes(vannes_ouvertes, vannes_fermees):
    freeze_air(True)
    for v in vannes_ouvertes:
        set_dir(v, Sens.OUVERTURE)
    for v in vannes_fermees:
        set_dir(v, Sens.FERMETURE)
    for v in vannes_ouvertes:
        move(STEP_MOVE, v, t_step)
    for v in vannes_fermees:
        move(STEP_MOVE, v, t_step)
    freeze_air(False)

# =========================
# LECTURES MCP / IHM BOUTONS
# =========================

def MCP_update():
    global btn_state, num_prg, selec_state, num_selec, air_state
    btn_state   = [1 if MCP_2.read(i) > seuil_mcp else 0 for i in range(8)]
    num_prg     = btn_state.index(1)+1 if sum(btn_state) == 1 else 0
    selec_state = [1 if MCP_1.read(i) > seuil_mcp else 0 for i in range(5)]
    num_selec   = selec_state.index(1) if sum(selec_state) == 1 else 0  # 0..5
    air_state   = 1 if MCP_1.read(5) > seuil_mcp else 0
    _update_air_mode_from_button()

def attendre_relachement_boutons():
    lcd.clear()
    lcd.lcd_string("Attente:",        lcd.LCD_LINE_1)
    lcd.lcd_string("Relâcher bouton", lcd.LCD_LINE_2)
    while any(MCP_2.read(i) > seuil_mcp for i in range(8)):
        time.sleep(0.1)

def confirmer_programme(numero):
    lcd.clear()
    lcd.lcd_string(f"Lancer prog {numero} ?", lcd.LCD_LINE_1)
    lcd.lcd_string("Appuyer a nouveau",       lcd.LCD_LINE_2)
    log.info(f"[CONFIRM] Attente confirmation prog {numero}")
    t0 = monotonic()
    while monotonic() - t0 < 10:
        MCP_update()
        if num_prg == numero:
            lcd.clear()
            lcd.lcd_string(f"Programme {numero}", lcd.LCD_LINE_1)
            lcd.lcd_string("CONFIRME",           lcd.LCD_LINE_2)
            log.info(f"[CONFIRM] Programme {numero} confirmé")
            return True
        elif num_prg != 0:
            lcd.clear()
            lcd.lcd_string(f"Programme {numero}", lcd.LCD_LINE_1)
            lcd.lcd_string("ANNULE",             lcd.LCD_LINE_2)
            log.info(f"[CONFIRM] Mauvais bouton — programme {numero} annulé")
            time.sleep(2)
            return False
        time.sleep(0.1)
    lcd.clear()
    lcd.lcd_string(f"Programme {numero}", lcd.LCD_LINE_1)
    lcd.lcd_string("ANNULE",             lcd.LCD_LINE_2)
    log.info(f"[CONFIRM] Timeout — programme {numero} annulé")
    time.sleep(2)
    return False

# =========================
# DÉBITMÈTRE (calcul incrémental)
# =========================

def calcul_debit_et_volume():

    global last_debit_timestamp, last_pulse_count, pulse_count
    global _flow_log_last_t, _flow_log_last_q

    now = monotonic()
    interval = now - last_debit_timestamp
    if interval <= 0:
        return 0.0, 0.0, 0.0

    pulses = pulse_count - last_pulse_count
    frequency = pulses / interval           # Hz
    debit_L_min = frequency / 0.2           # *** La formule restera revue plus tard ***
    volume = debit_L_min * (interval / 60)  # L

    last_debit_timestamp = now
    last_pulse_count = pulse_count

    # --- Journalisation throttlée ---
    should_log = False
    # 1) cadence mini
    if (now - _flow_log_last_t) >= FLOW_LOG_EVERY_S:
        should_log = True
    # 2) variation relative
    elif _flow_log_last_q is None:
        should_log = True
    else:
        prev = _flow_log_last_q
        if prev == 0.0:
            if debit_L_min > 0.0:
                should_log = True
        else:
            if abs(debit_L_min - prev) / abs(prev) >= FLOW_LOG_DELTA_FRAC:
                should_log = True

    if should_log:
        log.info(f"[DEBIT] {interval:.1f}s — {volume:.3f} L — {debit_L_min:.2f} L/min — {pulses} pulses")
        _flow_log_last_t = now
        _flow_log_last_q = debit_L_min

    return volume, debit_L_min, interval

# =========================
# EXÉCUTION D’UN PROGRAMME
# =========================

def executer_programme(num, vannes_ouvertes, vannes_fermees):
    global volume_total_litres, _idle_prompt_shown, _last_instant_debit, _last_display_switch, _display_toggle
    _idle_prompt_shown = False
    _display_toggle = False
    _last_display_switch = monotonic()

    log.info(f"=== Début du programme {num} ===")
    lcd.clear()
    lcd.lcd_string(f"Programme {num}", lcd.LCD_LINE_1)
    lcd.lcd_string("EN COURS",         lcd.LCD_LINE_2)

    attendre_relachement_boutons()
    MCP_update()  # rafraîchir num_selec juste avant
    # 1) Homing V4V (soft) puis 2) aller à la position demandée (0..5)
    home_V4V()
    goto_V4V_position(num_selec)

    # Transaction vannes (air gelé)
    transaction_vannes(vannes_ouvertes, vannes_fermees)

    t0 = monotonic()

    try:
        while (now := monotonic()) - t0 < PROGRAM_DURATION_SEC:
            # Alternance affichage (s’exécute à chaque tour)
            update_run_display(num, t0, now)

            # Débit / volume : mise à jour continue pour affichage du total en live
            vol_i, debit_i, _ = calcul_debit_et_volume()
            if vol_i > 0:
                volume_total_litres += vol_i
            _last_instant_debit = debit_i

            # Lecture boutons / Air
            MCP_update()
            air_tick_non_blocking(now)  # (2) pilotage EV sans blocage

            time.sleep(0.05)

    finally:
        # Stop air en fin de programme
        updateElectrovanne(False)
        log.info(f"[PRG {num}] Temporisation 1s avant fermeture vannes")
        time.sleep(1)
        fermer_toutes_les_vannes_sauf_v4v()

    # Affiche un écran de fin + volume
    lcd.clear()
    lcd.lcd_string(f"Prog {num} TERMINE", lcd.LCD_LINE_1)
    lcd.lcd_string(f"Total {volume_total_litres:.2f} L", lcd.LCD_LINE_2)
    log.info(f"=== Fin du programme {num} ===")

# =========================
# DÉCLARATION DES PROGRAMMES
# =========================
def prg_1(): executer_programme(1, ["eau", "cuve", "pompeOUT", "clientD", "egout"], ["clientG", "boue"])
def prg_2(): executer_programme(2, ["clientD", "boue", "egout"], ["eau", "cuve", "pompeOUT", "clientG"])
def prg_3(): executer_programme(3, ["eau", "clientD", "boue"], ["pompeOUT", "clientG", "egout", "cuve"])
def prg_4(): executer_programme(4, ["cuve", "pompeOUT", "egout"], ["eau", "clientG", "clientD", "boue"])
def prg_5(): executer_programme(5, ["clientG", "cuve", "eau", "egout"], ["pompeOUT", "clientD", "boue"])
def prg_6(): executer_programme(6, ["eau", "cuve"], ["pompeOUT", "clientD", "clientG", "boue", "egout"])

# =========================
# INITIALISATION
# =========================
log.info("Initialisation")
_apply_air_mode()          # LED_MASK initial
updateElectrovanne(False)  # EV OFF

lcd.clear()
lcd.lcd_string("Direction moteur", lcd.LCD_LINE_1)
lcd.lcd_string("RESET",            lcd.LCD_LINE_2)
update_shift_register()  # push états init
time.sleep(0.5)

# MAZ global (inclut V4V) — bloquant (OK pour proto)
for nom in motor_map:
    lcd.clear()
    lcd.lcd_string("MAZ moteur :", lcd.LCD_LINE_1)
    lcd.lcd_string(nom,            lcd.LCD_LINE_2)
    set_dir(nom, Sens.FERMETURE)
    move(STEP_MAZ, nom, t_maz)
    time.sleep(2 * wait)
    move(STEP_MICRO_MAZ, nom, t_maz)
    time.sleep(wait)
pos_V4V_steps = 0

lcd.clear()
lcd.lcd_string("Initialisation", lcd.LCD_LINE_1)
lcd.lcd_string("OK",             lcd.LCD_LINE_2)
log.info("Initialisation OK")
time.sleep(1)

show_idle_prompt()  # invite d’attente

# =========================
# SÉCURITÉ & ARRÊT
# =========================
def safe_shutdown():
    """EV OFF, fermer vannes (sauf V4V), afficher total."""
    try:
        log.info("[SHUTDOWN] EV OFF + fermeture vannes")
        updateElectrovanne(False)
        time.sleep(1)
        fermer_toutes_les_vannes_sauf_v4v()
        afficher_volume_total()
        log.info(f"[SHUTDOWN] Total = {volume_total_litres:.2f} L")
    except Exception as e:
        log.error(f"[SHUTDOWN] Erreur: {e}")

# =========================
# BOUCLE PRINCIPALE
# =========================

try:
    while True:
        MCP_update()
        update_shift_register()

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
    safe_shutdown()
    time.sleep(5)
    update_shift_register(new_dir_mask=0x00, new_led_mask=0x00)
    MCP_1.close()
    MCP_2.close()
    GPIO.cleanup()
    log.info("END OF PRG")
    time.sleep(wait)