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
MOTOR_HOMING_FIRST_CLOSE_FACTOR: float = 1.06


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

# Sélecteur rotatif VIC — 2 positions câblées (VIC3 non connecté) :
#   VIC1 actif (B0) → 1 → DEPART ( 0 pas)
#   VIC2 actif (B1) → 2 → RETOUR (100 pas)
#   rien actif      → 0 → NEUTRE ( 50 pas) — position par défaut
VIC_POSITIONS: dict[int, int] = {0: 50, 1: 0, 2: 100}

# Vitesse de déplacement VIC (très lent — mouvement précis)
VIC_SPEED_SPS: float = 10.0

# Homing VIC — nombre de traversées vers les butées.
# Avec VIC_HOMING_CYCLES = 3, la séquence complète est :
#   DEPART → RETOUR → DEPART → RETOUR → DEPART → RETOUR → NEUTRE
# (ancrage initial DEPART + N cycles alternés RETOUR/DEPART,
#  dernier cycle finit en RETOUR, puis 50 pas fermeture vers NEUTRE)
VIC_HOMING_CYCLES: int = 10


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

# Bip long de signalisation début / fin de programme.
# Émis une fois au lancement (timer démarré) et une fois à l'arrêt du programme.
# Bloquant — il marque une transition, aucun bouton n'a à être lu à cet instant.
BUZZER_PROGRAM_SIGNAL_MS: int = 2_500


# ============================================================
# Débitmètre
# ============================================================

# K-factor — impulsions par litre.
# ⚠️ CONSTANTE DE CALIBRATION : sa valeur est ajustée en permanence, en test
#    comme en production. Une valeur différente de la référence ci-dessous
#    n'est PAS une erreur — c'est le fonctionnement normal.
# Valeur de référence terrain mesurée : 10.84 imp/L (à conserver en mémoire).
DEBITMETRE_K_FACTOR: float  = 9.25
DEBITMETRE_DEBOUNCE_US: int =    400  # filtre anti-rebond (µs)


# ============================================================
# Sécurité cuve vide — PRG2 et PRG4
#
# PRG2 et PRG4 vident une cuve censée être pleine. Si le débit s'effondre,
# c'est que la cuve est vide : il n'y a rien à relancer.
#   → coupure pompe + arrêt du programme, SANS tentative de relance.
#
# Un délai de garde après le démarrage évite que la sécurité se déclenche
# pendant la montée en pression et bloque le démarrage de la pompe.
#
# Un écran d'avertissement "Attention, cuve vide" est affiché avant le
# lancement ; l'opérateur valide par un 2e appui sur le bouton du programme.
# ============================================================

# --- PRG2 — Vidange cuve de travail ---
PRG2_CUVE_VIDE_MIN_LPM:   float = 50.0   # seuil de débit (L/min)
PRG2_CUVE_VIDE_TIMEOUT_S: float =  3.0   # durée continue sous le seuil avant arrêt
PRG2_CUVE_VIDE_GRACE_S:   float = 10.0   # délai de garde après start() avant activation

# --- PRG4 — Remplissage cuve de travail ---
PRG4_CUVE_VIDE_MIN_LPM:   float = 50.0
PRG4_CUVE_VIDE_TIMEOUT_S: float =  3.0
PRG4_CUVE_VIDE_GRACE_S:   float = 10.0

# --- Confirmation opérateur avant lancement ---
# Programmes qui exigent l'écran d'avertissement + 2e appui de validation.
CUVE_VIDE_CONFIRM_PROGRAMS: tuple[int, ...] = (2, 4)

# Abandon automatique si l'opérateur ne confirme pas — retour IDLE.
CUVE_VIDE_CONFIRM_TIMEOUT_S: float = 10.0

# Motif sonore pendant l'écran de confirmation : salve de N bips, puis pause,
# répétée pendant toute la durée d'affichage — l'opérateur est sollicité en
# continu pour qu'il regarde et lise l'écran.
# ⚠️ Ce motif est joué de façon NON BLOQUANTE : l'écran doit rester à l'écoute
#    du 2e appui de confirmation pendant que le buzzer sonne.
CUVE_VIDE_CONFIRM_BEEP_COUNT: int     = 2
CUVE_VIDE_CONFIRM_BEEP_PAUSE_S: float = 1.0

# Durée d'affichage du message "Plus de debit / Cuve vide" avant l'arrêt.
CUVE_VIDE_ALERT_TIME_S: float = 5.0

# --- Message de fin de programme ---
# Affiché sur l'écran d'arrêt de PRG2 / PRG4 pour confirmer à l'opérateur
# quelle cuve vient d'être vidée. PRG2 vide la cuve 1, PRG4 vide la cuve 2
# (réserve d'eau propre) en remplissant la cuve 1.
# 20 caractères max, ASCII pur (cf. limitation HD44780).
PRG2_ENDMSG: str = "CUVE 1 VIDE"
PRG4_ENDMSG: str = "CUVE 2 VIDE"

# Table de correspondance — un programme absent n'affiche aucun message de fin.
ENDMSG: dict[int, str] = {
    2: PRG2_ENDMSG,
    4: PRG4_ENDMSG,
}


# ============================================================
# Sécurité débit avec relance pompe — PRG5 uniquement
#
# PRG5 tourne en circuit fermé : une chute de débit peut être passagère
# (bulle d'air, colmatage temporaire). Une procédure de relance a donc du sens.
#
# ⚠️ La procédure est volontairement BLOQUANTE : la machine doit rester
#    100 % automatique et l'opérateur ne doit pas pouvoir intervenir
#    pendant la tentative de rétablissement.
# ============================================================

PRG5_FLOW_MIN_LPM:        float = 50.0   # seuil de débit (L/min)
PRG5_FLOW_TIMEOUT_S:      float = 10.0   # durée continue sous le seuil avant relance
PRG5_FLOW_RESTART_COUNT:  int   = 3      # nombre de cycles pompe OFF → ON
PRG5_FLOW_RESTART_PAUSE_S: float = 5.0   # durée de chaque phase OFF puis ON

# Délai de garde après start() : la surveillance ne s'active qu'ensuite, le temps
# que la pompe monte en pression. Évite un déclenchement au démarrage.
PRG5_FLOW_GRACE_S: float = 5.0


# ============================================================
# Vannes US Solid — temporisations
#
# Les vannes US Solid ont une course mecanique LENTE (~10-20s).
#
# Ouverture (relay ON) :
#   Le condensateur interne se charge et actionne l'ouverture.
#   La vanne atteint la butee ouverte en ~10s de course mecanique.
#   Attendre VALVE_OPEN_CAPACITOR_CHARGE_S avant toute action suivante
#   (vanne physiquement ouverte + condensateur pleinement rechargé).
#
# Fermeture (relay OFF) :
#   Le condensateur se décharge pour actionner la fermeture.
#   La vanne atteint la butee fermee en VALVE_CLOSE_TRAVEL_S.
#   Aucune action sur une autre vanne avant ce delai.
# ============================================================

# Ouverture — attente apres relay ON (course mecanique ~10s + charge condensateur).
VALVE_OPEN_CAPACITOR_CHARGE_S: float = 15

# Fermeture — duree de course mecanique apres relay OFF (butee fermee).
VALVE_CLOSE_TRAVEL_S: float = 16


# ============================================================
# Programmes — cycles AIR et EGOUTS
# ============================================================

# PRG1 — Première vidange : cycle AIR automatique
PRG1_AIR_ON_S:  float = 4.0
PRG1_AIR_OFF_S: float = 3.0

# PRG3 — Séchage : cycle AIR automatique
PRG3_AIR_ON_S:  float = 6.0
PRG3_AIR_OFF_S: float = 2.0

# PRG3 — Séchage : cycle relay EGOUTS (ON/OFF non-bloquant, vs moteur bloquant en V4)
PRG3_EGOUTS_OPEN_S:   float = 15.0  # durée relay EGOUTS ON
PRG3_EGOUTS_CLOSED_S: float = 30.0  # durée relay EGOUTS OFF

# PRG3 — Séchage : inversion automatique du sens de la VIC.
#
# Objectif : inverser le sens d'injection d'air pour décoller efficacement
# les saletés dans les tuyaux.
#
# Cycle : VIC en butée → attente PRG3_VIC_INVERT_PERIOD_S → traversée vers
#         la butée opposée → attente → traversée retour → ...
#
# Chaque traversée est faite en OVERCOURSE (facteur ci-dessous) afin de
# garantir l'arrivée en butée mécanique quelle que soit la dérive éventuelle.
# Le compteur de position est recalé à l'arrivée.
#
# ⚠️ Ce cycle est NON BLOQUANT : un pas est généré par itération de la boucle
#    principale, ce qui laisse les cycles AIR et EGOUTS se dérouler normalement.
PRG3_VIC_INVERT_PERIOD_S: float = 50.0   # attente en butée avant chaque traversée

# Facteur d'overcourse des traversées PRG3 : 1.15 = 115 % de VIC_TOTAL_STEPS.
# Avec VIC_TOTAL_STEPS = 100 → 115 pas par traversée (≈ 12 s à VIC_SPEED_SPS = 10).
PRG3_VIC_OVERCOURSE_FACTOR: float = 1.10

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


# ============================================================
# Affichage LCD — durées des écrans temporisés
#
# Durée pendant laquelle chaque écran reste visible avant d'être
# automatiquement remplacé par le suivant.
# ============================================================

# Écran d'accueil au démarrage machine — "CLEAN & PROTECH / SERENA 230V".
# Affiché juste après l'init des périphériques, avant le homing VIC.
LCD_WELCOME_SCREEN_TIME_S: float = 5.0

# Écran de fin de programme — "PROGRAMME x / <nom> / Arret...".
# Affiché après program.stop(), avant le retour à l'écran d'attente.
# Ne concerne pas PRG5, qui affiche son récapitulatif à la place.
LCD_STOP_SCREEN_TIME_S: float = 10.0

# Écran de récapitulatif PRG5 — "Termine / Volume : x.xx L".
# Affiché en fin de PRG5 uniquement, à la place de l'écran "Arret...".
LCD_PRG5_SUMMARY_TIME_S: float = 10.0

# Clignotement des consignes critiques sur les écrans RUNNING.
# Cadence : LCD_BLINK_PERIOD_S allumé, puis LCD_BLINK_PERIOD_S éteint.
# Une valeur <= 0 désactive le clignotement (texte affiché en permanence).
LCD_BLINK_PERIOD_S: float = 1.0

# Clignotement des LEDs programme.
# Cadence : LED_BLINK_PERIOD_S allumée, puis LED_BLINK_PERIOD_S éteinte.
#
# Convention d'état des LEDs :
#   IDLE                      → toutes éteintes
#   transitions (CONFIRM,     → LED du programme concerné CLIGNOTANTE
#     avant-programme,
#     démarrage, arrêt)
#   RUNNING                   → LED du programme allumée FIXE
#   sécurité / défaut         → LED CLIGNOTANTE
LED_BLINK_PERIOD_S: float = 1.0

# Alternance de deux textes sur une même ligne (écrans RUNNING).
# Chaque texte reste affiché LCD_ALTERNATE_PERIOD_S avant de céder la place
# à l'autre. Permet de faire tenir deux informations sur une seule ligne.
# Une valeur <= 0 fige l'affichage sur le premier texte.
LCD_ALTERNATE_PERIOD_S: float = 3.0


# ============================================================
# Écrans avant-programme — consignes opérateur
#
# Affichés APRÈS l'appui bouton (et après l'écran de confirmation cuve vide
# pour PRG2/PRG4), AVANT toute action machine : ni vanne, ni VIC, ni pompe.
#
# Comportement : purement automatique et BLOQUANT.
#   → aucun bouton n'est lu pendant l'affichage
#   → à l'expiration du délai, le programme démarre tout seul
#
# Mise en page LCD 20x4 :
#   ligne 1        : "PROGRAMME x"
#   lignes 2 à 4   : message (3 lignes max), centrées
#   pas de compte à rebours affiché
#
# ⚠️ Le LCD est un HD44780 : il ne sait PAS afficher les caractères accentués.
#    Les messages doivent rester en ASCII pur (pas de é, è, à, ç...)
#    et chaque ligne doit tenir en LCD_COLS (20) caractères.
# ============================================================

# --- Durée d'affichage, par programme ---
PRG1_PREMSG_TIME_S: float = 10.0
PRG2_PREMSG_TIME_S: float = 10.0
PRG3_PREMSG_TIME_S: float = 10.0
PRG4_PREMSG_TIME_S: float = 10.0
PRG5_PREMSG_TIME_S: float = 10.0

# --- Message affiché, par programme (3 lignes max, 20 caractères max/ligne) ---
PRG1_PREMSG_LINES: tuple[str, ...] = (
    "Referez vous",
    "a la notice",
)
PRG2_PREMSG_LINES: tuple[str, ...] = (
    "Activer la pompe",
    "Vidage Cuve 1",
)
PRG3_PREMSG_LINES: tuple[str, ...] = (
    "Brancher le",
    "compresseur",
)
PRG4_PREMSG_LINES: tuple[str, ...] = (
    "Activer la pompe",
    "Verifier niveau",
    "max Cuve 2",
)
PRG5_PREMSG_LINES: tuple[str, ...] = (
    "Mettre la VIC en",
    "position Neutre",
    "Activer la pompe",
)

# --- Motif sonore pendant l'affichage ---
# Salve de PREMSG_BEEP_COUNT bips, puis pause de PREMSG_BEEP_PAUSE_S,
# répétée jusqu'à expiration du délai : "bip-bip ... bip-bip ... bip-bip"
PREMSG_BEEP_COUNT: int      = 2
PREMSG_BEEP_PAUSE_S: float  = 1.0

# --- Tables de correspondance (construites à partir des constantes ci-dessus) ---
# Un programme absent de ces tables n'affiche aucun écran avant-programme.
PREMSG_TIME_S: dict[int, float] = {
    1: PRG1_PREMSG_TIME_S,
    2: PRG2_PREMSG_TIME_S,
    3: PRG3_PREMSG_TIME_S,
    4: PRG4_PREMSG_TIME_S,
    5: PRG5_PREMSG_TIME_S,
}

PREMSG_LINES: dict[int, tuple[str, ...]] = {
    1: PRG1_PREMSG_LINES,
    2: PRG2_PREMSG_LINES,
    3: PRG3_PREMSG_LINES,
    4: PRG4_PREMSG_LINES,
    5: PRG5_PREMSG_LINES,
}