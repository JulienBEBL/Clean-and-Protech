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
# Configuration DIP switch : 10111111
#   SW1=ON  SW2=OFF  SW3=ON  → Courant crête : 3.14 A
#   SW4=ON                   → Courant maintenu plein (pas de demi-courant en pause)
#   SW5=ON  SW6=ON  SW7=ON  SW8=ON → Résolution : 400 pas/tour
# ============================================================

DRIVER_MICROSTEP: int = 400        # pas par tour (microstep resolution)
DRIVER_PEAK_CURRENT_A: float = 3.14
DRIVER_FULL_CURRENT_STANDBY: bool = True  # SW4=ON : pas de réduction en pause
DRIVER_DIP_SWITCH: str = "10111111"       # référence visuelle du réglage physique


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
MOTOR_MIN_SPEED_SPS: float = 100.0
MOTOR_MAX_SPEED_SPS: float = 4_000.0

# Courses complètes (steps)
MOTOR_OUVERTURE_STEPS: int = 3_800
MOTOR_FERMETURE_STEPS: int = 4_000

# Profil de rampe par défaut
MOTOR_RAMP_ACCEL_TIME_S: float = 2.0
MOTOR_RAMP_DECEL_TIME_S: float = 2.0

# Vitesses de rampe par défaut pour ouverture/fermeture complètes
MOTOR_DEFAULT_SPEED_SPS: float  = 2_000.0
MOTOR_DEFAULT_ACCEL_SPS: float  = 1_000.0
MOTOR_DEFAULT_DECEL_SPS: float  = 1_000.0

# Timing bas-niveau
MOTOR_MIN_PULSE_US: int  = 50   # durée minimale demi-impulsion (µs)
MOTOR_ENA_SETTLE_MS: int =  5   # délai après activation ENA avant premier pas (ms)


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

DEBITMETRE_K_FACTOR: float = 11.15   # impulsions par litre
DEBITMETRE_DEBOUNCE_US: int = 400    # filtre anti-rebond (µs)