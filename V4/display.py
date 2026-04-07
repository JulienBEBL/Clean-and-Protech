"""
display.py — Rendu LCD 20×4 pour Clean & Protech V4.

Chaque fonction render_*() écrit les 4 lignes de l'écran.
Pas de lcd.clear() dans les fonctions de boucle (évite le clignotement) :
les lignes sont écrasées en place à chaque appel.

lcd.clear() est appelé uniquement lors des transitions d'état
(ex. passage de IDLE à STARTING) depuis main.py.

Fonctions disponibles :
    render_splash(lcd)                          — démarrage machine
    render_homing(lcd)                          — homing en cours
    render_idle(lcd, io)                        — attente (10 Hz)
    render_starting(lcd, prg_id, prg_name)      — une fois avant program.start()
    render_running(lcd, program, ctx, elapsed_s) — exécution (10 Hz)
    render_stopping(lcd, prg_id, prg_name)      — une fois avant program.stop()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.lcd2004 import LCD2004
    from libs.io_board import IOBoard
    from programs import ProgramBase, MachineContext


# ============================================================
# Constantes d'affichage
# ============================================================

_AIR_LABELS: dict[int, str] = {0: "OFF", 1: "FAI", 2: "MOY", 3: "CON"}


# ============================================================
# Helpers internes
# ============================================================

def _pad(s: str) -> str:
    """Tronque ou complète à 20 caractères pour le LCD."""
    return s[:20].ljust(20)


def _read_vic_pos(io: "IOBoard") -> int:
    """Retourne la position active du sélecteur VIC (1..5), ou 0 si aucune."""
    for i in range(1, 6):
        if io.read_vic_active(i):
            return i
    return 0


# ============================================================
# Écrans
# ============================================================

def render_splash(lcd: "LCD2004") -> None:
    """
    Écran de démarrage — affiché pendant l'initialisation des périphériques.

    ┌────────────────────┐
    │  CLEAN & PROTECH   │
    │      SERENA        │
    │   Initialisation   │
    │                    │
    └────────────────────┘
    """
    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "SERENA")
    lcd.write_centered(3, "Initialisation...")
    lcd.write_centered(4, "")


def render_homing(lcd: "LCD2004") -> None:
    """
    Homing en cours — affiché pendant la fermeture simultanée des 8 moteurs.

    ┌────────────────────┐
    │  CLEAN & PROTECH   │
    │      SERENA        │
    │  Préparation ....  │
    │                    │
    └────────────────────┘
    """
    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "SERENA")
    lcd.write_centered(3, "Préparation ...")
    lcd.write_centered(4, "")


def render_idle(lcd: "LCD2004", io: "IOBoard") -> None:
    """
    État d'attente — appelée à ~10 Hz dans la boucle principale.
    Lit les sélecteurs VIC et AIR et les affiche sur la ligne 4.

    ┌────────────────────┐
    │  CLEAN & PROTECH   │
    │  Choisir programme │
    │   PRG1  a  PRG5    │
    │ VIC: 3   AIR: MOY  │
    └────────────────────┘  
    """
    vic_pos  = _read_vic_pos(io)
    air_mode = io.read_air_mode()
    vic_str  = str(vic_pos) if vic_pos > 0 else "-"
    air_str  = _AIR_LABELS.get(air_mode, "---")

    lcd.write_centered(1, "CLEAN & PROTECH")
    lcd.write_centered(2, "Choisir programme")
    lcd.write_centered(3, "PRG1  a  PRG5")
    lcd.write(4, _pad(f" VIC:{vic_str}     AIR:{air_str}"))


def render_starting(lcd: "LCD2004", prg_id: int, prg_name: str) -> None:
    """
    Affiché une fois avant program.start() (opération bloquante).

    ┌────────────────────┐
    │   PRG1 PREM.VID.   │
    │                    │
    │    Demarrage...    │
    │                    │
    └────────────────────┘
    """
    lcd.write_centered(1, f"PRG{prg_id} {prg_name}")
    lcd.write_centered(2, "")
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

    Exemple PRG1 :
    ┌────────────────────┐
    │ PRG1 PREM.VIDANGE  │
    │ VIC:DEP  AIR: ON   │
    │                    │
    │ Duree   00:03:42   │
    └────────────────────┘

    Exemple PRG5 :
    ┌────────────────────┐
    │ PRG5 DESEMBOUAGE   │
    │ VIC:3    AIR:MOY   │
    │ Debit:  12.3 L/min │
    │ Duree   00:10:42   │
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

    ┌────────────────────┐
    │   PRG1 PREM.VID.   │
    │                    │
    │      Arret...      │
    │                    │
    └────────────────────┘
    """
    lcd.write_centered(1, f"PRG{prg_id} {prg_name}")
    lcd.write_centered(2, "")
    lcd.write_centered(3, "Arret...")
    lcd.write_centered(4, "")
