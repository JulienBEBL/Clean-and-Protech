"""
main.py

Base propre pour programme principal Clean & Protech.
- Initialisation I2C
- Initialisation IOBoard (MCP)
- Initialisation LCD
- Boucle principale simple
"""

from __future__ import annotations

import time
from typing import Optional

from lib.i2c import (
    I2CBus,
    IOBoard,
    LCD2004,
    ON,
    OFF,
)

# -------------------------------------------------
# Configuration globale
# -------------------------------------------------

BUS_ID = 1
FREQ_HZ = 100_000
RETRIES = 2
RETRY_DELAY_S = 0.01

MAIN_LOOP_DELAY_S = 0.05  # 50 ms (20 Hz)


# -------------------------------------------------
# Application
# -------------------------------------------------

class Application:
    """
    Base applicative.
    Structure prête pour évoluer vers machine d'état.
    """

    def __init__(self) -> None:
        self.bus: Optional[I2CBus] = None
        self.io: Optional[IOBoard] = None
        self.lcd: Optional[LCD2004] = None
        self._running: bool = False

    # -----------------------------
    # Initialisation
    # -----------------------------
    def init(self) -> None:
        self.bus = I2CBus(
            bus_id=BUS_ID,
            freq_hz=FREQ_HZ,
            retries=RETRIES,
            retry_delay_s=RETRY_DELAY_S,
        )
        self.bus.open()

        self.io = IOBoard(self.bus)
        self.io.init(force=True)

        try:
            self.lcd = LCD2004(self.bus, address=0x27, cols=20, rows=4)
            self.lcd.init()
            self.lcd.clear()
            self.lcd.write(1, "System starting...")
        except Exception:
            # LCD non critique
            self.lcd = None

        # Etat initial sécurité
        self._safe_outputs()

        self._running = True

    # -----------------------------
    # Sécurité sortie
    # -----------------------------
    def _safe_outputs(self) -> None:
        if not self.io:
            return

        for i in range(1, 7):
            self.io.set_led(i, OFF)

        for m in range(1, 9):
            self.io.set_ena(m, OFF)
            self.io.set_dir(m, "fermeture")

    # -----------------------------
    # Boucle principale
    # -----------------------------
    def run(self) -> None:
        if not self.io:
            raise RuntimeError("Application not initialized")

        print("Application started.")
        print("Ctrl+C to stop.")

        try:
            while self._running:

                # ---------------------------------
                # Lecture entrées (actif bas)
                # ---------------------------------
                prg1 = self.io.read_btn_active(1)
                vic1 = self.io.read_vic_active(1)
                air1 = self.io.read_air_active(1)

                # ---------------------------------
                # Exemple logique simple
                # ---------------------------------

                # LED1 suit PRG1
                self.io.set_led(1, ON if prg1 else OFF)

                # Si VIC1 actif -> moteur 1 ouverture
                if vic1:
                    self.io.set_dir(1, "ouverture")
                    self.io.set_ena(1, ON)
                else:
                    self.io.set_ena(1, OFF)

                # LCD affichage simple
                if self.lcd:
                    self.lcd.write(2, f"PRG1={prg1} VIC1={vic1}".ljust(20))
                    self.lcd.write(3, f"AIR1={air1}".ljust(20))

                time.sleep(MAIN_LOOP_DELAY_S)

        except KeyboardInterrupt:
            print("\nStopping application...")

        finally:
            self.shutdown()

    # -----------------------------
    # Arrêt propre
    # -----------------------------
    def shutdown(self) -> None:
        print("Safe shutdown...")

        self._safe_outputs()

        if self.lcd:
            try:
                self.lcd.clear()
                self.lcd.write(1, "System stopped")
            except Exception:
                pass

        if self.bus:
            try:
                self.bus.close()
            except Exception:
                pass

        self._running = False
        print("Stopped.")


# -------------------------------------------------
# Entry point
# -------------------------------------------------

def main() -> None:
    app = Application()
    app.init()
    app.run()


if __name__ == "__main__":
    main()
