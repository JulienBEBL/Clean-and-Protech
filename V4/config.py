"""
config.py — Source de vérité unique pour Clean & Protech V4.

Toutes les constantes matérielles (GPIO, I2C, moteurs, périphériques)
sont définies ici. Aucun module ne doit contenir de constante hardware
en dur : tout passe par ce fichier.

Hardware cible : Raspberry Pi 5, Python 3.11+, lgpio.
"""

from __future__ import annotations

# ============================================================
# GPIO — Raspberry Pi 5 (numérotation BCM)
# ============================================================

# lgpio chip index (gpiochip4 sur RPi 5)
GPIO_CHIP: int = 4

# Moteurs — broches PUL (pulse / step), une par driver
# Clé = ID moteur (1..8), Valeur = GPIO BCM
MOTOR_PUL_PINS: dict[int, int] = {
    1: 17,  # POT_A_BOUE
    2: 27,  # POMPE
    3: 22,  # CUVE_TRAVAIL
    4:  5,  # RETOUR
    5: 18,  # EGOUTS
    6: 23,  # VIC
    7: 24,  # DEPART
    8: 25,  # EAU_PROPRE
}

# Buzzer
BUZZER_GPIO: int = 26

# Débitmètre
DEBITMETRE_GPIO: int = 21

# Relais critiques
RELAY_POMPE_OFF_GPIO: int = 16
RELAY_AIR_GPIO: int = 20


# ============================================================
# I2C
# ============================================================

I2C_BUS_ID: int = 1
I2C_FREQ_HZ: int = 100_000
I2C_RETRIES: int = 2
I2C_RETRY_DELAY_S: float = 0.01

# Adresses MCP23017
MCP1_ADDR: int = 0x24  # Programmes : LEDs (A) + boutons PRG (B)
MCP2_ADDR: int = 0x26  # Sélecteurs : VIC (B) + AIR (A)
MCP3_ADDR: int = 0x25  # Drivers moteurs : ENA (B) + DIR (A)

# Adresse LCD
LCD_ADDR: int = 0x27
LCD_COLS: int = 20
LCD_ROWS: int = 4


# ============================================================
# Drivers moteurs — DM860H (JKongMotor)
# Configuration DIP switch : 11011111
#   SW1=ON  SW2=ON  SW3=OFF  → Courant crête : 5 A
#   SW4=ON                   → Courant maintenu plein (pas de demi-courant en pause)
#   SW5=ON  SW6=ON  SW7=ON  SW8=ON → Résolution : 400 pas/tour
# ============================================================

DRIVER_MICROSTEP: int = 400        # pas par tour (microstep resolution)
DRIVER_PEAK_CURRENT_A: float = 5
DRIVER_FULL_CURRENT_STANDBY: bool = True  # SW4=ON : pas de réduction en pause
DRIVER_DIP_SWITCH: str = "11011111"       # référence visuelle du réglage physique


# ============================================================
# Moteurs — mapping et contraintes
# ============================================================

# Nom métier → ID driver (1..8)
MOTOR_NAME_TO_ID: dict[str, int] = {
    "POT_A_BOUE":   2,
    "POMPE":        8,
    "CUVE_TRAVAIL": 4,
    "RETOUR":       1,
    "EGOUTS":       5,
    "VIC":          3,
    "DEPART":       6,
    "EAU_PROPRE":   7,
}

# Alias acceptés (normalisés en majuscules)
MOTOR_ALIASES: dict[str, str] = {
    "POT A BOUE":   "POT_A_BOUE",
    "POT À BOUE":   "POT_A_BOUE",
    "CUVE TRAVAIL": "CUVE_TRAVAIL",
    "EAU PROPRE":   "EAU_PROPRE",
    "EGOUT":        "EGOUTS",
}

# ENA : niveau logique driver actif / inactif (câblage inversé)
ENA_ACTIVE_LEVEL: int   = 0  # driver ON  quand ENA = 0
ENA_INACTIVE_LEVEL: int = 1  # driver OFF quand ENA = 1

# Plage vitesse validée (steps/sec)
MOTOR_MIN_SPEED_SPS: float = 10.0
MOTOR_MAX_SPEED_SPS: float = 20_000.0

# Courses complètes (steps)
MOTOR_OUVERTURE_STEPS: int = 3_700
MOTOR_FERMETURE_STEPS: int = 4_000

# Profil de rampe par défaut
MOTOR_RAMP_ACCEL_TIME_S: float = 2.0
MOTOR_RAMP_DECEL_TIME_S: float = 0.5

# Ouverture complète — profil de vitesse
MOTOR_OUVERTURE_SPEED_SPS: float = 800.0
MOTOR_OUVERTURE_ACCEL_SPS: float = 50.0
MOTOR_OUVERTURE_DECEL_SPS: float = 700.0

# Fermeture complète — profil de vitesse
MOTOR_FERMETURE_SPEED_SPS: float = 1600.0
MOTOR_FERMETURE_ACCEL_SPS: float = 600.0
MOTOR_FERMETURE_DECEL_SPS: float = 1200.0

# Vitesse constante — move_steps()
MOTOR_DEFAULT_CONST_SPEED_SPS: float = 800.0

# Timing bas-niveau
MOTOR_MIN_PULSE_US: int  = 50   # durée minimale demi-impulsion (µs)
MOTOR_ENA_SETTLE_MS: int =  5   # délai après activation ENA avant premier pas (ms)

# Homing — première fermeture : course majorée pour garantir la butée
# quelle que soit la position initiale (appliqué aux moteurs et à la VIC)
MOTOR_HOMING_FIRST_CLOSE_FACTOR: float = 1.1

# Homing — cycles de rodage après la première fermeture/ouverture
# (fermeture standard + ouverture standard, répétés N fois)
MOTOR_HOMING_RODAGE_CYCLES: int = 5


# ============================================================
# Buzzer
# ============================================================

# Référence composant : SEA-1295Y-0520-42Ω-38P6.5 (passif, 5V, 42Ω, résonance 2 kHz)
# Courbe de réponse : montée à partir de 500 Hz, pic à 2 kHz (≥90 dB), chute au-delà de 4 500 Hz
BUZZER_FREQ_MIN_HZ: int     =  500   # en dessous : réponse < 60 dB, inutilisable
BUZZER_FREQ_MAX_HZ: int     = 4_500  # au-delà : chute marquée + oscillations parasites
BUZZER_DEFAULT_FREQ_HZ: int = 2_000  # fréquence de résonance nominale
BUZZER_DEFAULT_DUTY_PCT: float = 50.0

# Paramètres par défaut de beep()
BUZZER_BEEP_TIME_MS: int   = 100
BUZZER_BEEP_POWER_PCT: int =  50
BUZZER_BEEP_REPEAT: int    =   1
BUZZER_BEEP_GAP_MS: int    =  60


# ============================================================
# Débitmètre
# ============================================================

DEBITMETRE_K_FACTOR: float = 10.5  # impulsions par litre (K-factor)
DEBITMETRE_DEBOUNCE_US: int = 400    # filtre anti-rebond (µs)


# ============================================================
# VIC — vanne de direction (course physique 90° = 100 pas)
#   0 pas   → flux vers DEPART  (position homing / fermeture)
#   50 pas  → neutre            (flux partagé)
#   100 pas → flux vers RETOUR  (ouverture complète)
# ============================================================

VIC_TOTAL_STEPS: int  = 100   # course totale
VIC_DEPART_STEPS: int =   0   # fermeture = vers départ
VIC_NEUTRE_STEPS: int =  50   # milieu
VIC_RETOUR_STEPS: int = 100   # ouverture = vers retour

# 5 positions du sélecteur rotatif VIC → steps correspondants
VIC_POSITIONS: dict[int, int] = {1: 0, 2: 30, 3: 50, 4: 70, 5: 100}

# Vitesse de déplacement VIC (très lent — mouvement précis)
VIC_SPEED_SPS: float = 20.0


# ============================================================
# Programmes — cycles AIR et EGOUTS
# ============================================================

# PRG1 — Première vidange : cycle AIR automatique
PRG1_AIR_ON_S:  float = 3.0   # durée injection
PRG1_AIR_OFF_S: float = 4.0   # durée pause

# PRG3 — Séchage : cycle AIR automatique (indépendant du cycle EGOUTS)
PRG3_AIR_ON_S:  float = 4.0
PRG3_AIR_OFF_S: float = 2.0

# PRG3 — Séchage : cycle EGOUTS (ouverture/fermeture moteur alternée)
PRG3_EGOUTS_OPEN_S:   float = 4.0   # durée vanne EGOUTS ouverte — à ajuster terrain
PRG3_EGOUTS_CLOSED_S: float = 3.0   # durée vanne EGOUTS fermée — à ajuster terrain

# PRG5 — Désembouage : cycles AIR manuel (sélecteur AIR 1..3)
PRG5_AIR_FAIBLE_ON_S:  float = 2.0   # mode 1 — faible
PRG5_AIR_FAIBLE_OFF_S: float = 2.0
PRG5_AIR_MOYEN_ON_S:   float = 4.0   # mode 2 — moyen
PRG5_AIR_MOYEN_OFF_S:  float = 2.0
# mode 3 — continu : relais AIR ON permanent (pas de cycle)


# ============================================================
# Boucle principale et IHM
# ============================================================

MAIN_LOOP_HZ: int     = 10     # fréquence de la boucle principale
BTN_DEBOUNCE_MS: int  = 50     # anti-rebond boutons PRG (ms)
