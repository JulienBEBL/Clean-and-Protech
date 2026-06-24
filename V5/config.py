"""
config.py — Source de vérité unique pour Clean & Protech V5.

Toutes les constantes matérielles (GPIO, I2C, relais, VIC, périphériques)
sont définies ici. Aucun module ne doit contenir de constante hardware
en dur : tout passe par ce fichier.

Hardware cible : Raspberry Pi 5, Python 3.11+, lgpio.
Machine 230V — SERENA 230V.
"""

from __future__ import annotations


# ============================================================
# GPIO — Raspberry Pi 5 (numérotation BCM)
# ============================================================

# lgpio chip index (gpiochip4 sur RPi 5)
GPIO_CHIP: int = 4

# Buzzer — 2 buzzers passifs en parallèle sur la même broche
BUZZER_GPIO: int = 21

# Débitmètre à impulsions
DEBITMETRE_GPIO: int = 13


# ============================================================
# Relais — POMPE et EV AIR (GPIO direct, actifs haut)
# ============================================================

# Relais POMPE — pilote le câble de commande ON du variateur de vitesse.
# GPIO HIGH → relais ON  → commande ON variateur active  → pompe tourne.
# GPIO LOW  → relais OFF → commande ON variateur inactive → pompe à l'arrêt.
# NOTE : le variateur dispose également d'une commande OFF indépendante (câble
#        séparé, raccordé à un sélecteur mécanique). Le câblage de ce relais
#        peut évoluer en fonction du comportement terrain du variateur.
RELAY_POMPE_GPIO: int = 19

# Relais EV AIR — pilote l'électrovanne d'injection d'air, contact NO.
# GPIO HIGH → relais ON  → EV ouverte → injection d'air active.
# GPIO LOW  → relais OFF → EV fermée  → pas d'injection d'air.
RELAY_AIR_GPIO: int = 26


# ============================================================
# Relais vannes US Solid — contacts NO, actifs haut
# GPIO HIGH → relais ON  → contact NO fermé  → vanne ouverte.
# GPIO LOW  → relais OFF → contact NO ouvert → vanne fermée (état sûr).
# Seuls V1..V4 sont câblés/utilisés. V5..V8 réservés (non connectés côté vannes).
# ============================================================

RELAY_POT_A_BOUE_GPIO:  int = 7    # V1
RELAY_EGOUTS_GPIO:       int = 8    # V2
RELAY_CUVE_TRAVAIL_GPIO: int = 25   # V3
RELAY_EAU_PROPRE_GPIO:   int = 24   # V4

# Réserve — présents sur le PCB, non câblés côté vannes (modifiables)
RELAY_RESERVE_V5_GPIO: int = 23
RELAY_RESERVE_V6_GPIO: int = 18
RELAY_RESERVE_V7_GPIO: int = 15
RELAY_RESERVE_V8_GPIO: int = 14


# ============================================================
# I2C
# ============================================================

I2C_BUS_ID: int = 1
I2C_FREQ_HZ: int = 100_000
I2C_RETRIES: int = 2
I2C_RETRY_DELAY_S: float = 0.01

# Adresses MCP23017 — À CONFIRMER via test_i2c_scan.py après câblage PCB.
# Valeurs probables : 0x24 (MCP1) et 0x26 (MCP2), identiques à V4 (MCP3 retiré).
MCP1_ADDR: int = 0x24   # LEDs PRG (port A) + boutons PRG (port B)
MCP2_ADDR: int = 0x26   # sélecteur VIC 3 pos (port B) + sélecteur AIR (port A)

# Adresse LCD
LCD_ADDR: int = 0x27
LCD_COLS: int = 20
LCD_ROWS: int  = 4


# ============================================================
# VIC — driver JK-DM860H, GPIO direct (STEP, DIR, ENA)
# ============================================================

VIC_STEP_GPIO: int = 27   # PUL / STEP
VIC_DIR_GPIO:  int = 17   # DIR
VIC_ENA_GPIO:  int = 22   # ENA

# ENA actif bas (câblage DM860H) : 0 = driver actif, 1 = driver désactivé
VIC_ENA_ACTIVE_LEVEL:   int = 0
VIC_ENA_INACTIVE_LEVEL: int = 1

# Direction (niveau logique sur DIR) :
#   HIGH → vers RETOUR (sens ouverture, steps croissants)
#   LOW  → vers DEPART (sens fermeture, steps décroissants)
VIC_DIR_OUVERTURE: int = 1
VIC_DIR_FERMETURE: int = 0


# ============================================================
# Driver VIC — DM860H (JKongMotor)
# DIP switch : 400 pas/tour, courant selon réglage physique du DIP.
# ============================================================

DRIVER_MICROSTEP: int = 400   # pas par tour (microstep resolution)

# Plage vitesse validée pour la VIC (steps/sec)
MOTOR_MIN_SPEED_SPS: float = 5.0
MOTOR_MAX_SPEED_SPS: float = 100.0

# Timing bas-niveau
MOTOR_MIN_PULSE_US: int  = 50   # durée minimale demi-impulsion (µs)
MOTOR_ENA_SETTLE_MS: int =  5   # délai après activation ENA avant premier pas (ms)

# Homing — facteur d'overcourse (ex : 1.1 = +10 %)
# Garantit l'ancrage en butée quelle que soit la position initiale.
MOTOR_HOMING_FIRST_CLOSE_FACTOR: float = 1.1


# ============================================================
# VIC — course et positions
#
#   0 pas  → DEPART  (butée fermeture)
#  50 pas  → NEUTRE  (milieu de course)
# 100 pas  → RETOUR  (butée ouverture)
# ============================================================

VIC_TOTAL_STEPS: int  = 100
VIC_DEPART_STEPS: int =   0
VIC_NEUTRE_STEPS: int =  50
VIC_RETOUR_STEPS: int = 100

# Sélecteur rotatif VIC — 3 positions (MCP2 port B, B0..B2, actif bas) :
#   position 1 (B0) → DEPART (0 pas)
#   position 2 (B1) → NEUTRE (50 pas)
#   position 3 (B2) → RETOUR (100 pas)
VIC_POSITIONS: dict[int, int] = {1: 0, 2: 50, 3: 100}

# Vitesse de déplacement VIC (très lent — mouvement précis)
VIC_SPEED_SPS: float = 10.0

# Homing VIC — nombre de traversées vers les butées.
# Avec VIC_HOMING_CYCLES = 3, la séquence complète est :
#   DEPART → RETOUR → DEPART → RETOUR → DEPART → RETOUR → NEUTRE
# (ancrage initial DEPART + N cycles alternés RETOUR/DEPART,
#  dernier cycle finit en RETOUR, puis 50 pas fermeture vers NEUTRE)
VIC_HOMING_CYCLES: int = 3


# ============================================================
# Buzzer
# ============================================================

# Composant : 2× SEA-1295Y-0520-42Ω-38P6.5 (passifs, 5V, 42Ω, résonance 2 kHz) en parallèle
BUZZER_FREQ_MIN_HZ: int      =   500
BUZZER_FREQ_MAX_HZ: int      = 4_500
BUZZER_DEFAULT_FREQ_HZ: int  = 2_000
BUZZER_DEFAULT_DUTY_PCT: float = 50.0

BUZZER_BEEP_TIME_MS: int   = 100
BUZZER_BEEP_POWER_PCT: int =  50
BUZZER_BEEP_REPEAT: int    =   1
BUZZER_BEEP_GAP_MS: int    =  60


# ============================================================
# Débitmètre
# ============================================================

DEBITMETRE_K_FACTOR: float  = 10.84   # impulsions par litre — valeur terrain mesurée
DEBITMETRE_DEBOUNCE_US: int =    400  # filtre anti-rebond (µs)


# ============================================================
# Sécurité débit — surveillance + procédure de relance pompe
# ============================================================

# Programmes sur lesquels la sécurité débit est active (modifiable)
FLOW_SAFETY_ENABLED_PROGRAMS: tuple[int, ...] = (2, 4, 5)

# Débit minimum acceptable
FLOW_SAFETY_MIN_LPM: float = 50.0   # L/min

# Durée continue sous le seuil avant déclenchement de la relance
FLOW_SAFETY_TIMEOUT_S: float = 10.0  # secondes

# Procédure de relance : nombre de cycles pompe OFF → ON
FLOW_SAFETY_RESTART_COUNT: int = 3

# Durée de chaque phase OFF et ON de la relance, et attente finale avant relecture débit
FLOW_SAFETY_RESTART_PAUSE_S: float = 5.0  # secondes


# ============================================================
# Vannes US Solid — charge condensateurs
# ============================================================

# Durée d'alimentation de toutes les vannes au démarrage de la machine.
# Permet de charger à fond les condensateurs internes avant le premier cycle.
VALVE_STARTUP_CAPACITOR_CHARGE_S: float = 10.0

# Attente après ouverture d'une vanne en début de programme.
# Garantit que les condensateurs sont rechargés avant l'action suivante (pompe, VIC...).
VALVE_OPEN_CAPACITOR_CHARGE_S: float = 5.0


# ============================================================
# Programmes — cycles AIR et EGOUTS
# ============================================================

# PRG1 — Première vidange : cycle AIR automatique
PRG1_AIR_ON_S:  float = 4.0
PRG1_AIR_OFF_S: float = 3.0

# PRG3 — Séchage : cycle AIR automatique
PRG3_AIR_ON_S:  float = 8.0
PRG3_AIR_OFF_S: float = 2.0

# PRG3 — Séchage : cycle relay EGOUTS (ON/OFF non-bloquant, vs moteur bloquant en V4)
PRG3_EGOUTS_OPEN_S:   float = 2.0   # durée relay EGOUTS ON
PRG3_EGOUTS_CLOSED_S: float = 8.0   # durée relay EGOUTS OFF

# PRG5 — Désembouage : cycles AIR manuel (sélecteur AIR 1..3)
PRG5_AIR_FAIBLE_ON_S:  float = 2.0   # mode 1 — faible
PRG5_AIR_FAIBLE_OFF_S: float = 2.0
PRG5_AIR_MOYEN_ON_S:   float = 4.0   # mode 2 — moyen
PRG5_AIR_MOYEN_OFF_S:  float = 2.0
# mode 3 — continu : relais AIR ON permanent (pas de cycle)


# ============================================================
# Boucle principale et IHM
# ============================================================

MAIN_LOOP_HZ: int    = 10
BTN_DEBOUNCE_MS: int = 50
