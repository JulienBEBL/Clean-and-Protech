"""
test_display.py — Rendu visuel dynamique de tous les écrans de display.py.

Cycle de test :
    1. Splash          — 3s
    2. Homing          — 3s
    3. IDLE            — 5s (sélecteurs VIC/AIR lus en temps réel)
    4. Pour chaque programme (PRG1..PRG5) :
         a. Starting       — 2s
         b. Running        — 8s (temps qui défile, état AIR/VIC simulé)
         c. Stopping       — 2s
    5. IDLE            — 5s (fin)

Moteurs et relais sont des mocks légers — aucun mouvement mécanique.
Le débit est simulé (12.3 L/min).
Les sélecteurs VIC et AIR sont lus sur le vrai matériel.

Ctrl+C pour arrêter proprement à tout moment.
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
from libs.io_board import IOBoard
from libs.lcd2004 import LCD2004
import display
from programs import MachineContext, PROGRAMS


# ============================================================
# Mocks — aucun mouvement mécanique
# ============================================================

class _MockMotors:
    def ouverture(self, name: str) -> None: pass
    def fermeture(self, name: str) -> None: pass
    def move_steps(self, name: str, steps: int, direction: str, speed: float = 0) -> None: pass


class _MockRelays:
    def set_air_on(self, time_s=None) -> None: pass
    def set_air_off(self) -> None: pass
    def set_pompe_on(self) -> None: pass
    def set_pompe_off(self) -> None: pass
    def tick(self) -> None: pass


class _MockFlow:
    def flow_lpm(self, window_s: float = 1.0) -> float:
        return 12.3
    def total_liters(self) -> float:
        return 5.0


# ============================================================
# Helpers
# ============================================================

def _wait(lcd: LCD2004, io: IOBoard, seconds: float, step: float = 0.1) -> None:
    """Attend `seconds` secondes en lisant les sélecteurs pour afficher IDLE dynamique."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(step)


def _running_loop(
    lcd: LCD2004,
    prg,
    ctx: MachineContext,
    duration_s: float,
    tick_s: float = 0.1,
) -> None:
    """
    Simule la boucle RUNNING : appelle program.tick() + render_running() à ~10 Hz.
    Le temps écoulé s'incrémente en temps réel.
    """
    t0 = time.monotonic()
    deadline = t0 + duration_s
    while time.monotonic() < deadline:
        elapsed = time.monotonic() - t0
        prg.tick(ctx)
        display.render_running(lcd, prg, ctx, elapsed)
        time.sleep(tick_s)


# ============================================================
# Séquence de test
# ============================================================

def _run_program_sequence(lcd: LCD2004, io: IOBoard, ctx: MachineContext) -> None:
    for prg_id, prg in PROGRAMS.items():
        print(f"\n  PRG{prg_id} — {prg.name}")

        # Starting
        print("    → render_starting")
        lcd.clear()
        display.render_starting(lcd, prg.id, prg.name)
        _wait(lcd, io, 2.0)

        # Simule start() sans hardware : remet l'état interne du programme
        # (pas d'appel à prg.start() pour éviter les mouvements moteur)
        ctx.vic_steps = _vic_steps_for(prg_id)

        # Running — boucle 8s
        print("    → render_running (8s)")
        lcd.clear()
        _running_loop(lcd, prg, ctx, duration_s=8.0)

        # Stopping
        print("    → render_stopping")
        lcd.clear()
        display.render_stopping(lcd, prg.id, prg.name)
        _wait(lcd, io, 2.0)

        lcd.clear()


def _vic_steps_for(prg_id: int) -> int:
    """Retourne une position VIC simulée cohérente avec le programme."""
    return {
        1: config.VIC_DEPART_STEPS,   # 0
        2: config.VIC_NEUTRE_STEPS,   # 50
        3: config.VIC_DEPART_STEPS,   # 0
        4: config.VIC_NEUTRE_STEPS,   # 50
        5: 70,                         # position manuelle simulée
    }.get(prg_id, 0)


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 50)
    print("  TEST AFFICHAGE — display.py")
    print("=" * 50)
    print("  Aucun mouvement moteur (mocks actifs)")
    print("  Sélecteurs VIC/AIR lus sur le vrai matériel")
    print("  Ctrl+C pour arrêter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io  = IOBoard(bus)
        io.init()
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()

        ctx = MachineContext(
            motors      = _MockMotors(),
            relays      = _MockRelays(),
            io          = io,
            flow        = _MockFlow(),
            vic_steps   = 0,
        )

        try:
            # 1 — Splash
            print("  [1/4] Splash (3s)")
            display.render_splash(lcd)
            _wait(lcd, io, 3.0)
            lcd.clear()

            # 2 — Homing
            print("  [2/4] Homing (3s)")
            display.render_homing(lcd)
            _wait(lcd, io, 3.0)
            lcd.clear()

            # 3 — IDLE (sélecteurs réels)
            print("  [3/4] IDLE (5s) — bougez VIC/AIR pour voir les changements")
            t0 = time.monotonic()
            while time.monotonic() - t0 < 5.0:
                display.render_idle(lcd, io)
                time.sleep(0.1)
            lcd.clear()

            # 4 — Programmes
            print("  [4/4] Programmes PRG1..PRG5")
            _run_program_sequence(lcd, io, ctx)

            # 5 — IDLE finale
            print("\n  Fin — IDLE (5s)")
            t0 = time.monotonic()
            while time.monotonic() - t0 < 5.0:
                display.render_idle(lcd, io)
                time.sleep(0.1)

            print("\n  Test terminé.")
            lcd.clear()
            lcd.write_centered(1, "Test termine")
            lcd.write_centered(2, "OK")

        except KeyboardInterrupt:
            print("\n  Arrêté par l'utilisateur.")
            lcd.clear()
            lcd.write_centered(1, "Arret utilisateur")

    gpio_handle.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Arrêté par l'utilisateur.")
        gpio_handle.close()
