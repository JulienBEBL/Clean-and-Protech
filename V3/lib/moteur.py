"""
moteur.py — Stepper motors (PUL via lgpio, DIR/ENA via IOBoard i2c.py)

- PUL: GPIO RPi (BCM) par moteur (1..8)
- DIR/ENA: via IOBoard (MCP) -> io.set_dir(motor, ...) / io.set_ena(motor, ...)

Objectif V1:
- move_steps(motor_id, steps, direction)

Notes:
- Génération pulses en Python: pas "temps réel" mais suffisant pour pilotage DM860H à vitesse modérée.
- On garde des pulses "larges" (>=200 µs) pour robustesse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio is required on Raspberry Pi OS. Install python3-lgpio.") from e

# Import IOBoard (DIR/ENA)
# IMPORTANT: ce module suppose l'arborescence /lib et import depuis main/tests via sys.path.
from i2c import IOBoard  # type: ignore


class MotorError(Exception):
    pass


class MotorNotInitializedError(MotorError):
    pass


# ----------------------------
# Mapping PUL (BCM) — figé PCB
# ----------------------------
PUL_PINS_BCM: Dict[int, int] = {
    1: 17,
    2: 27,
    3: 22,
    4: 5,
    5: 18,
    6: 23,
    7: 24,
    8: 25,
}

# ----------------------------
# Paramètres impulsions (robustes)
# ----------------------------
# DM860H accepte généralement des pulses très courts, mais en Python on vise large/stable.
DEFAULT_STEP_HIGH_US = 200  # durée niveau haut (µs)
DEFAULT_STEP_LOW_US = 200   # durée niveau bas  (µs)

# Option: délai après activation ENA avant pulses
ENA_SETTLE_MS = 5


@dataclass(frozen=True)
class MotorConfig:
    gpiochip_index: int = 0
    step_high_us: int = DEFAULT_STEP_HIGH_US
    step_low_us: int = DEFAULT_STEP_LOW_US


class MotorController:
    """
    Contrôleur moteurs:
    - utilise IOBoard pour ENA/DIR (MCP)
    - utilise lgpio pour PUL (GPIO RPi)
    """

    def __init__(self, io: IOBoard, config: MotorConfig = MotorConfig()):
        self.io = io
        self.config = config
        self._chip: Optional[int] = None

    def open(self) -> None:
        if self._chip is not None:
            return
        try:
            chip = lgpio.gpiochip_open(self.config.gpiochip_index)
            # Claim outputs PUL à 0
            for motor_id, bcm in PUL_PINS_BCM.items():
                lgpio.gpio_claim_output(chip, bcm, 0)
            self._chip = chip
        except Exception as e:
            self._chip = None
            raise MotorError(f"Failed to open MotorController: {e}") from e

    def close(self) -> None:
        if self._chip is None:
            return
        try:
            # safe: PUL low + ENA off
            for motor_id, bcm in PUL_PINS_BCM.items():
                try:
                    lgpio.gpio_write(self._chip, bcm, 0)
                except Exception:
                    pass
                try:
                    self.io.set_ena(motor_id, 0)
                except Exception:
                    pass
        finally:
            lgpio.gpiochip_close(self._chip)
            self._chip = None

    def __enter__(self) -> "MotorController":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise MotorNotInitializedError("MotorController not initialized. Call open() first.")
        return self._chip

    @staticmethod
    def _norm_motor_id(motor_id: int) -> int:
        m = int(motor_id)
        if m not in PUL_PINS_BCM:
            raise ValueError("motor_id must be in 1..8")
        return m

    @staticmethod
    def _norm_direction(direction: str) -> str:
        d = direction.strip().upper()
        if d in ("OUVERTURE", "OPEN", "O"):
            return "ouverture"
        if d in ("FERMETURE", "CLOSE", "F"):
            return "fermeture"
        raise ValueError("direction must be 'ouverture' or 'fermeture'")

    @staticmethod
    def _sleep_us(us: int) -> None:
        # time.sleep a une résolution limitée; mais à ~200us ça reste OK pour un pilotage lent.
        time.sleep(max(0, int(us)) / 1_000_000.0)

    def move_steps(self, motor_id: int, steps: int, direction: str) -> None:
        """
        Déplace un moteur de N pas.
        - motor_id: 1..8
        - steps: nombre de pas (>=0)
        - direction: 'ouverture' / 'fermeture'
        """
        chip = self._require_open()
        m = self._norm_motor_id(motor_id)
        d = self._norm_direction(direction)

        n = int(steps)
        if n < 0:
            raise ValueError("steps must be >= 0")
        if n == 0:
            return

        pul_gpio = PUL_PINS_BCM[m]

        # Configure DIR + enable driver
        self.io.set_dir(m, d)
        self.io.set_ena(m, 1)
        if ENA_SETTLE_MS > 0:
            time.sleep(ENA_SETTLE_MS / 1000.0)

        # Pulse loop
        hi = int(self.config.step_high_us)
        lo = int(self.config.step_low_us)
        if hi <= 0 or lo <= 0:
            raise ValueError("step_high_us and step_low_us must be > 0")

        for _ in range(n):
            lgpio.gpio_write(chip, pul_gpio, 1)
            self._sleep_us(hi)
            lgpio.gpio_write(chip, pul_gpio, 0)
            self._sleep_us(lo)

        # Option sécurité: désactiver après mouvement (à valider selon ton besoin)
        self.io.set_ena(m, 0)