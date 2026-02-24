"""
moteur.py — Stepper motors (PUL via lgpio, DIR/ENA via IOBoard i2c.py)

- PUL: GPIO RPi (BCM) par moteur
- DIR/ENA: via IOBoard (MCP) -> io.set_dir(motor_id, ...) / io.set_ena(motor_id, ...)

Spécificités projet:
- move_steps utilise le NOM moteur (pas le numéro)
- ENA inversé:
    ENA=1 => driver désactivé
    ENA=0 (ou déconnecté) => driver actif
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio is required on Raspberry Pi OS. Install python3-lgpio.") from e

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
# Mapping noms moteurs -> ID
# ----------------------------
MOTOR_NAME_TO_ID: Dict[str, int] = {
    "CUVE_TRAVAIL": 1,
    "EAU_PROPRE": 2,
    "POMPE": 3,
    "DEPART": 4,
    "RETOUR": 5,
    "POT_A_BOUE": 6,
    "EGOUTS": 7,
    "VIC": 8,
}

# Alias tolérés (si tu veux écrire avec accents / espaces)
MOTOR_ALIASES: Dict[str, str] = {
    "CUVE TRAVAIL": "CUVE_TRAVAIL",
    "EAU PROPRE": "EAU_PROPRE",
    "POT À BOUE": "POT_A_BOUE",
    "POT A BOUE": "POT_A_BOUE",
    "EGOUT": "EGOUTS",
    "EGOUTS": "EGOUTS",
}

# ENA inversé (spécifique à ton câblage)
# io.set_ena(m, 1) => driver OFF
# io.set_ena(m, 0) => driver ON
ENA_ACTIVE_LEVEL = 0
ENA_INACTIVE_LEVEL = 1

# Timing robustesse
MIN_PULSE_US = 50          # garde-fou (DM860H accepte souvent moins, mais Python -> conservatif)
ENA_SETTLE_MS = 5          # délai après enable avant pulses


@dataclass(frozen=True)
class MotorConfig:
    gpiochip_index: int = 0
    min_pulse_us: int = MIN_PULSE_US


class MotorController:
    """
    Contrôleur moteurs:
    - utilise IOBoard pour ENA/DIR (MCP)
    - utilise lgpio pour PUL (GPIO RPi)

    Fonctions "main-friendly":
      - enable_all_drivers()
      - disable_all_drivers()
      - move_steps(motor_name, steps, direction, speed_sps)
    """

    def __init__(self, io: IOBoard, config: MotorConfig = MotorConfig()):
        self.io = io
        self.config = config
        self._chip: Optional[int] = None

    # -----------------
    # lifecycle
    # -----------------
    def open(self) -> None:
        if self._chip is not None:
            return
        try:
            chip = lgpio.gpiochip_open(self.config.gpiochip_index)
            for _, bcm in PUL_PINS_BCM.items():
                lgpio.gpio_claim_output(chip, bcm, 0)
            self._chip = chip
        except Exception as e:
            self._chip = None
            raise MotorError(f"Failed to open MotorController: {e}") from e

    def close(self) -> None:
        if self._chip is None:
            return
        try:
            # Safe: PUL low + disable drivers
            for _, bcm in PUL_PINS_BCM.items():
                try:
                    lgpio.gpio_write(self._chip, bcm, 0)
                except Exception:
                    pass
            try:
                self.disable_all_drivers()
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

    # -----------------
    # name -> id helpers
    # -----------------
    @staticmethod
    def _norm_name(name: str) -> str:
        n = name.strip().upper()
        n = n.replace("-", "_")
        n = n.replace(" ", "_") if n not in MOTOR_ALIASES else n
        if n in MOTOR_ALIASES:
            n = MOTOR_ALIASES[n]
        return n

    def motor_id(self, motor_name: str) -> int:
        n = self._norm_name(motor_name)
        if n not in MOTOR_NAME_TO_ID:
            valid = ", ".join(sorted(MOTOR_NAME_TO_ID.keys()))
            raise ValueError(f"Unknown motor_name '{motor_name}'. Valid: {valid}")
        return MOTOR_NAME_TO_ID[n]

    @staticmethod
    def _norm_direction(direction: str) -> str:
        d = direction.strip().upper()
        if d in ("OUVERTURE", "OPEN", "O"):
            return "ouverture"
        if d in ("FERMETURE", "CLOSE", "F"):
            return "fermeture"
        raise ValueError("direction must be 'ouverture' or 'fermeture'")

    # -----------------
    # Driver enable/disable
    # -----------------
    def enable_driver(self, motor_name: str) -> None:
        """Active un driver (ENA=0)."""
        m = self.motor_id(motor_name)
        self.io.set_ena(m, ENA_ACTIVE_LEVEL)

    def disable_driver(self, motor_name: str) -> None:
        """Désactive un driver (ENA=1)."""
        m = self.motor_id(motor_name)
        self.io.set_ena(m, ENA_INACTIVE_LEVEL)

    def enable_all_drivers(self) -> None:
        """Active tous les drivers (ENA=0 sur 1..8)."""
        for m in range(1, 9):
            self.io.set_ena(m, ENA_ACTIVE_LEVEL)

    def disable_all_drivers(self) -> None:
        """Désactive tous les drivers (ENA=1 sur 1..8)."""
        for m in range(1, 9):
            self.io.set_ena(m, ENA_INACTIVE_LEVEL)

    # -----------------
    # Step generation (speed in steps/s)
    # -----------------
    @staticmethod
    def _sleep_us(us: int) -> None:
        time.sleep(max(0, int(us)) / 1_000_000.0)

    def _compute_pulse_timings_us(self, speed_sps: float) -> Tuple[int, int]:
        """
        Convertit speed (steps/s) en (high_us, low_us) avec un duty ~50%.
        Garde-fou min_pulse_us.
        """
        if speed_sps <= 0:
            raise ValueError("speed_sps must be > 0")

        period_s = 1.0 / float(speed_sps)
        half_us = int((period_s * 1_000_000.0) / 2.0)

        min_us = int(self.config.min_pulse_us)
        if half_us < min_us:
            # on force au min -> la vitesse réelle sera plus basse que demandée
            half_us = min_us

        return half_us, half_us

    def move_steps(self, motor_name: str, steps: int, direction: str, speed_sps: float) -> None:
        """
        Déplace un moteur d'un nombre de pas donné à une vitesse donnée.

        Params:
          - motor_name: ex "Cuve_travail", "VIC", ...
          - steps: nb de pas (>=0)
          - direction: "ouverture"/"fermeture"
          - speed_sps: vitesse en pas/seconde (steps per second)
        """
        chip = self._require_open()

        nsteps = int(steps)
        if nsteps < 0:
            raise ValueError("steps must be >= 0")
        if nsteps == 0:
            return

        m = self.motor_id(motor_name)
        d = self._norm_direction(direction)
        pul_gpio = PUL_PINS_BCM[m]

        # DIR
        self.io.set_dir(m, d)

        # Enable driver (ENA inversé => 0=ON)
        self.io.set_ena(m, ENA_ACTIVE_LEVEL)
        if ENA_SETTLE_MS > 0:
            time.sleep(ENA_SETTLE_MS / 1000.0)

        high_us, low_us = self._compute_pulse_timings_us(speed_sps)

        for _ in range(nsteps):
            lgpio.gpio_write(chip, pul_gpio, 1)
            self._sleep_us(high_us)
            lgpio.gpio_write(chip, pul_gpio, 0)
            self._sleep_us(low_us)

        # Ne pas imposer une politique ici.
        # Par défaut: on laisse le driver actif (utile étanchéité).
        # Si tu veux l'inverse, tu appelles disable_driver() depuis le main.