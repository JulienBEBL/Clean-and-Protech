"""
display.py — Rendu LCD 20×4 pour Clean & Protech V5 (SERENA 230V).

Chaque fonction render_*() écrit les 4 lignes de l'écran.
Pas de lcd.clear() dans les fonctions de boucle (évite le clignotement) :
les lignes sont écrasées en place à chaque appel.

lcd.clear() est appelé uniquement lors des transitions d'état
(ex. passage de IDLE à STARTING) depuis main.py.

Fonctions disponibles :
    render_splash(lcd)                          — démarrage machine
    render_homing(lcd)                          — homing VIC en cours
    render_idle(lcd, io)                        — attente (10 Hz)
    render_pre_program(lcd, prg_id)             — consignes opérateur avant lancement
    render_starting(lcd, prg_id, prg_name)      — une fois avant program.start()
    render_running(lcd, program, ctx, elapsed_s) — exécution (10 Hz)
    render_stopping(lcd, prg_id, prg_name)      — une fois avant program.stop()
    render_cuve_vide_confirm(lcd, prg_id)       — confirmation PRG2/PRG4 (10 Hz)
    render_prg5_summary(lcd, prg_id, prg_name, total_liters)     — récap volume PRG5

Différences V4→V5 :
    - Splash : SERENA 230V (était 380V)
    - Sélecteur VIC : 2 positions câblées (était 5)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from libs.lcd2004 import LCD2004
    from libs.io_board import IOBoard
    from programs import ProgramBase, MachineContext


# ============================================================
# Constantes d'affichage
# ============================================================

_AIR_LABELS: dict[int, str] = {0: "OFF", 1: "FAI", 2: "MOY", 3: "CON"}

# Libellés VIC en toutes lettres — tous font 6 caractères, la ligne 4 de
# l'écran d'attente reste donc calée à 20 caractères quelle que soit la position.
_VIC_LABELS: dict[int, str] = {0: "NEUTRE", 1: "DEPART", 2: "RETOUR"}


# ============================================================
# Helpers internes
# ============================================================

def _pad(s: str) -> str:
    """Tronque ou complète à 20 caractères pour le LCD."""
    return s[:20].ljust(20)


# ============================================================
# Écrans
# ============================================================

def render_splash(lcd: "LCD2004") -> None:
    """
    Écran de démarrage — affiché pendant l'initialisation des périphériques.

    ┌────────────────────┐
    │  CLEAN & PROTECH   │
    │                    │
    │    SERENA 230V     │
    │                    │
    └────────────────────┘
    """
    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "")
    lcd.write_centered(3, "SERENA 230V")
    lcd.write_centered(4, "")


def render_homing(lcd: "LCD2004") -> None:
    """
    Homing VIC en cours — affiché pendant la séquence de référencement.

    ┌────────────────────┐
    │  CLEAN & PROTECH   │
    │      SERENA        │
    │  Préparation ....  │
    │                    │
    └────────────────────┘
    """
    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "SERENA")
    lcd.write_centered(3, "Preparation ...")
    lcd.write_centered(4, "")


def render_idle(lcd: "LCD2004", io: "IOBoard") -> None:
    """
    État d'attente — appelée à ~10 Hz dans la boucle principale.
    Lit les sélecteurs VIC et AIR et les affiche sur la ligne 4.

    ┌────────────────────┐
    │  CLEAN & PROTECH   │
    │ CHOISIR PROGRAMME  │
    │   PRG1  A  PRG5    │
    │VIC:NEUTRE   AIR:MOY│
    └────────────────────┘

    La ligne 4 fait exactement 20 caractères quelle que soit la position des
    sélecteurs : les 3 libellés VIC font 6 caractères et les 4 libellés AIR
    en font 3. Aucun décalage latéral au rafraîchissement 10 Hz.
    """
    vic_pos  = io.read_vic_selector()
    air_mode = io.read_air_mode()
    vic_str  = _VIC_LABELS.get(vic_pos, "------")
    air_str  = _AIR_LABELS.get(air_mode, "---")

    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "CHOISIR PROGRAMME")
    lcd.write_centered(3, "PRG1  A  PRG5")
    lcd.write(4, _pad(f"VIC:{vic_str}   AIR:{air_str}"))


def render_cuve_vide_confirm(lcd: "LCD2004", prg_id: int) -> None:
    """
    Avertissement avant le lancement de PRG2 / PRG4.
    Appelée à ~10 Hz : l'opérateur valide par un 2e appui sur le même bouton.
    Aucun compte à rebours affiché.

    La question porte sur l'état de la cuve AVANT le programme : celle-ci doit
    être PLEINE pour être vidangée. La sécurité qui surveille ensuite le débit
    détecte, elle, le moment où la cuve devient vide.

    ┌────────────────────┐
    │      ATTENTION     │
    │    CUVE PLEINE ?   │
    │  PRG2 : reappuyer  │
    │    pour lancer     │
    └────────────────────┘
    """
    lcd.write_centered(1, "ATTENTION")
    lcd.write_centered(2, "CUVE PLEINE ?")
    lcd.write_centered(3, f"PRG{prg_id} : reappuyer")
    lcd.write_centered(4, "pour lancer")


def render_pre_program(lcd: "LCD2004", prg_id: int) -> None:
    """
    Écran de consignes avant lancement — affiché une seule fois.

    Le message vient de config.PREMSG_LINES[prg_id] (3 lignes max).
    Les lignes non utilisées sont effacées pour éviter tout résidu
    d'un écran précédent. Pas de compte à rebours.

    Exemple PRG4 :
    ┌────────────────────┐
    │    PROGRAMME 4     │
    │  Activer la pompe  │
    │  Verifier niveau   │
    │     max Cuve 2     │
    └────────────────────┘
    """
    lines = config.PREMSG_LINES.get(prg_id, ())

    lcd.write_centered(1, f"PROGRAMME {prg_id}")
    for i in range(3):
        text = lines[i] if i < len(lines) else ""
        lcd.write_centered(2 + i, text)


def render_starting(lcd: "LCD2004", prg_id: int, prg_name: str) -> None:
    """
    Affiché une fois avant program.start() (opération bloquante si déplacement VIC).

    ┌────────────────────┐
    │    PROGRAMME 1     │
    │   PREM.VIDANGE     │
    │    Demarrage...    │
    │                    │
    └────────────────────┘
    """
    lcd.write_centered(1, f"PROGRAMME {prg_id}")
    lcd.write_centered(2, prg_name)
    lcd.write_centered(3, "Demarrage...")
    lcd.write_centered(4, "")


def render_running(
    lcd: "LCD2004",
    program: "ProgramBase",
    ctx: "MachineContext",
    elapsed_s: float,
) -> None:
    """
    Programme en cours d'exécution — appelée à ~10 Hz.
    Délègue la construction des lignes à program.lcd_info().

    Exemple PRG1 (lignes 2 et 3 alternées toutes les 3 s) :
    ┌────────────────────┐   ┌────────────────────┐
    │    PROGRAMME 1     │   │    PROGRAMME 1     │
    │  PREMIERE VIDANGE  │ ↔ │     ATTENTION      │
    │  100% AUTOMATIQUE  │ ↔ │ SURVEILLER CUVE 1  │
    │   DUREE : 12:34    │   │   DUREE : 12:37    │
    └────────────────────┘   └────────────────────┘

    Exemple PRG5 (lignes 2 et 3 clignotantes, 1 s / 1 s) :
    ┌────────────────────┐
    │  PRG5 DESEMBOUAGE  │
    │POMPE A L'ARRET POUR│
    │ CHANGEMENT DE SENS │
    │12:34      123 l/min│
    └────────────────────┘
    """
    l1, l2, l3, l4 = program.lcd_info(ctx, elapsed_s)
    lcd.write(1, l1)
    lcd.write(2, l2)
    lcd.write(3, l3)
    lcd.write(4, l4)


def render_stopping(lcd: "LCD2004", prg_id: int, prg_name: str) -> None:
    """
    Affiché une fois avant program.stop().

    La ligne 4 porte le message de fin du programme (config.ENDMSG) :
    elle confirme à l'opérateur quelle cuve vient d'être vidée.
    Vide pour les programmes qui n'en définissent pas.

    ┌────────────────────┐
    │    PROGRAMME 2     │
    │    VIDANGE CUVE    │
    │      Arret...      │
    │    CUVE 1 VIDE     │
    └────────────────────┘
    """
    lcd.write_centered(1, f"PROGRAMME {prg_id}")
    lcd.write_centered(2, prg_name)
    lcd.write_centered(3, "Arret...")
    lcd.write_centered(4, config.ENDMSG.get(prg_id, ""))


def render_prg5_summary(lcd: "LCD2004", prg_id: int, prg_name: str, total_liters: float) -> None:
    """
    Affiché après program.stop() pour PRG5 uniquement — récapitulatif volume.

    ┌────────────────────┐
    │    PROGRAMME 5     │
    │    DESEMBOUAGE     │
    │                    │
    │  Volume : 12.34 L  │
    └────────────────────┘
    """
    lcd.write_centered(1, f"PROGRAMME {prg_id}")
    lcd.write_centered(2, prg_name)
    lcd.write_centered(3, "")
    lcd.write_centered(4, f"Volume : {total_liters:.2f} L")
