"""
test_rodage_vic.py — Rodage automatique de la VIC — V5.

Objectif : faire tourner le moteur pas a pas de la VIC en cycles continus
DEPART → RETOUR → NEUTRE pour roder les mecanismes (vis, guidages, contacts)
et valider la fiabilite du driver DM860H sur la duree.

Sequence par cycle :
    1. DEPART  (  0 pas)
    2. RETOUR  (100 pas)
    3. DEPART  (  0 pas)
    4. NEUTRE  ( 50 pas)
    5. RETOUR  (100 pas)
    6. NEUTRE  ( 50 pas)
    7. RETOUR  (100 pas)
    8. NEUTRE  ( 50 pas)
    Reprise en 1.

Initialisation :
    Homing complet (identique a main.py) — ancrage + positionnement NEUTRE.
    Assure que la position de reference est connue avant le rodage.

Parametres driver DM860H :
    400 pas/tour (SW5..SW8 = ON)
    Vitesse de rodage = VIC_SPEED_SPS (config.py)
    Course totale    = VIC_TOTAL_STEPS = 100 pas

Affichage (10 Hz) :
    LCD  : position courante, numero de cycle, duree totale
    Terminal : meme info + statistiques (pas totaux, tours equiv.)

Ctrl+C : arrete proprement apres avoir immobilise le moteur (ENA desactive).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
import libs.gpio_handle as gpio_handle
from libs.i2c_bus import I2CBus
from libs.lcd2004 import LCD2004
from libs.vic import VICController

_COLS = config.LCD_COLS  # 20

# Sequence de rodage : 8 positions par cycle
_SEQUENCE: tuple[tuple[str, int], ...] = (
    ("DEPART", config.VIC_DEPART_STEPS),   # 0
    ("RETOUR", config.VIC_RETOUR_STEPS),   # 100
    ("DEPART", config.VIC_DEPART_STEPS),   # 0
    ("NEUTRE", config.VIC_NEUTRE_STEPS),   # 50
    ("RETOUR", config.VIC_RETOUR_STEPS),   # 100
    ("NEUTRE", config.VIC_NEUTRE_STEPS),   # 50
    ("RETOUR", config.VIC_RETOUR_STEPS),   # 100
    ("NEUTRE", config.VIC_NEUTRE_STEPS),   # 50
)

# Pause entre chaque deplacement (secondes) — 0 = sans pause
_PAUSE_BETWEEN_MOVES_S: float = 0.5


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _fmt_elapsed(elapsed_s: float) -> str:
    h = int(elapsed_s) // 3600
    m = (int(elapsed_s) % 3600) // 60
    s = int(elapsed_s) % 60
    if h > 0:
        return f"{h:02d}h{m:02d}m{s:02d}s"
    return f"{m:02d}:{s:02d}"


def _lcd_rodage(
    lcd: LCD2004,
    cycle: int,
    pos_label: str,
    elapsed_s: float,
    total_steps: int,
) -> None:
    """
    LCD pendant le rodage :
        L1 : RODAGE VIC
        L2 : Cycle NNNN  POS:XXXXXX
        L3 : Duree HH:MM:SS
        L4 : Pas totaux : NNNNNN
    """
    lcd.write_centered(1, "RODAGE VIC")
    lcd.write(2, _pad(f"Cycle {cycle:4d}  {pos_label}"))
    lcd.write(3, _pad(f"Duree {_fmt_elapsed(elapsed_s)}"))
    lcd.write(4, _pad(f"Pas tot. : {total_steps:7d}"))


# ============================================================
# Phase 1 — Homing
# ============================================================

def phase_homing(lcd: LCD2004, vic: VICController) -> None:
    print("=" * 54)
    print("  PHASE INIT — HOMING VIC")
    print("=" * 54)
    print(f"  Cycles homing  : {config.VIC_HOMING_CYCLES}")
    overcourse = int(config.VIC_TOTAL_STEPS * config.MOTOR_HOMING_FIRST_CLOSE_FACTOR)
    print(f"  Overcourse     : {overcourse} pas ({config.MOTOR_HOMING_FIRST_CLOSE_FACTOR:.0%})")
    print(f"  Position finale: NEUTRE = {config.VIC_NEUTRE_STEPS} pas")
    print()

    lcd.clear()
    lcd.write_centered(1, "RODAGE VIC")
    lcd.write_centered(2, "")
    lcd.write_centered(3, "Homing en cours...")
    lcd.write_centered(4, "")

    t0 = time.monotonic()
    vic.homing()
    dt = time.monotonic() - t0

    pos = vic.position
    ok  = pos == config.VIC_NEUTRE_STEPS

    print(f"  Homing termine en {dt:.1f}s")
    print(f"  Position finale : {pos} pas  ({'OK' if ok else 'ERREUR'})")
    if not ok:
        raise RuntimeError(
            f"Homing echoue : position {pos} pas (attendu {config.VIC_NEUTRE_STEPS})"
        )

    lcd.clear()
    lcd.write_centered(1, "RODAGE VIC")
    lcd.write_centered(2, "Homing OK")
    lcd.write_centered(3, f"NEUTRE = {pos} pas")
    lcd.write_centered(4, "")
    time.sleep(2.0)


# ============================================================
# Phase 2 — Rodage cyclique
# ============================================================

def phase_rodage(lcd: LCD2004, vic: VICController) -> None:
    print()
    print("=" * 54)
    print("  PHASE RODAGE — DEPART / RETOUR / NEUTRE")
    print("=" * 54)
    print(f"  Sequence : DEP → RET → DEP → NEU → RET → NEU → RET → NEU → ...")
    print(f"  Vitesse  : {config.VIC_SPEED_SPS} sps  "
          f"({config.DRIVER_MICROSTEP} pas/tour)")
    print(f"  Pause    : {_PAUSE_BETWEEN_MOVES_S:.1f}s entre chaque position")
    print(f"  Ctrl+C   : arret propre en fin de deplacement courant")
    print()
    print("  >>> Entree pour demarrer...", end="", flush=True)
    input()

    cycle       = 0
    total_steps = 0
    seq_idx     = 0        # index dans _SEQUENCE
    t_start     = time.monotonic()
    stop_req    = False

    # Partir de NEUTRE (position apres homing) vers DEPART pour commencer proprement
    print(f"\n  Deplacement initial : NEUTRE → DEPART")
    vic.move_to(config.VIC_DEPART_STEPS)
    total_steps += abs(config.VIC_DEPART_STEPS - config.VIC_NEUTRE_STEPS)

    try:
        while not stop_req:
            pos_label, target = _SEQUENCE[seq_idx]

            # Avancer seq_idx pour la prochaine iteration
            next_idx = (seq_idx + 1) % len(_SEQUENCE)
            if next_idx == 0:
                cycle += 1

            elapsed = time.monotonic() - t_start
            steps_this_move = abs(target - vic.position)
            total_steps += steps_this_move

            # Statistiques terminal
            tours_equiv = total_steps / config.DRIVER_MICROSTEP
            print(
                f"  Cycle {cycle:4d} | {pos_label:<6} | "
                f"duree {_fmt_elapsed(elapsed)} | "
                f"pas tot. {total_steps:7d} ({tours_equiv:.1f} tours)     "
            )

            # Deplacement (bloquant)
            vic.move_to(target)

            # Mise a jour LCD apres deplacement
            elapsed = time.monotonic() - t_start
            _lcd_rodage(lcd, cycle, pos_label, elapsed, total_steps)

            # Pause entre positions
            if _PAUSE_BETWEEN_MOVES_S > 0:
                time.sleep(_PAUSE_BETWEEN_MOVES_S)

            seq_idx = next_idx

    except KeyboardInterrupt:
        stop_req = True
        print(f"\n\n  Arret demande (Ctrl+C)")

    # Bilan final
    elapsed = time.monotonic() - t_start
    tours_equiv = total_steps / config.DRIVER_MICROSTEP
    print()
    print("=" * 54)
    print("  BILAN RODAGE")
    print("=" * 54)
    print(f"  Cycles complets : {cycle}")
    print(f"  Pas totaux      : {total_steps}")
    print(f"  Tours equivalents : {tours_equiv:.1f}")
    print(f"  Duree totale    : {_fmt_elapsed(elapsed)}")
    print(f"  Position finale : {vic.position} pas")

    lcd.clear()
    lcd.write_centered(1, "RODAGE VIC")
    lcd.write_centered(2, f"Cycles : {cycle}")
    lcd.write_centered(3, f"Pas : {total_steps}")
    lcd.write_centered(4, f"Duree {_fmt_elapsed(elapsed)}")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  RODAGE VIC — Clean & Protech V5")
    print("=" * 54)
    print(f"  Driver DM860H   : {config.DRIVER_MICROSTEP} pas/tour")
    print(f"  Course          : {config.VIC_TOTAL_STEPS} pas")
    print(f"  DEPART          : {config.VIC_DEPART_STEPS} pas")
    print(f"  NEUTRE          : {config.VIC_NEUTRE_STEPS} pas")
    print(f"  RETOUR          : {config.VIC_RETOUR_STEPS} pas")
    print(f"  Vitesse         : {config.VIC_SPEED_SPS} sps")
    print(f"  GPIO STEP/DIR/ENA : {config.VIC_STEP_GPIO}/{config.VIC_DIR_GPIO}/{config.VIC_ENA_GPIO}")
    print()

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()

        vic = VICController()
        vic.open()

        try:
            phase_homing(lcd, vic)
            phase_rodage(lcd, vic)

        except KeyboardInterrupt:
            print("\n\n  Arret global (Ctrl+C)")

        except RuntimeError as e:
            print(f"\n  ERREUR : {e}")
            lcd.clear()
            lcd.write_centered(1, "RODAGE VIC")
            lcd.write_centered(2, "ERREUR")
            lcd.write_centered(3, "Voir terminal")

        finally:
            vic.disable()
            vic.close()
            lcd.clear()
            lcd.write_centered(1, "RODAGE VIC")
            lcd.write_centered(2, "Termine")
            lcd.write_centered(3, f"pos={vic.position} pas")

    gpio_handle.close()
    print("=== FIN RODAGE VIC ===")


if __name__ == "__main__":
    main()
