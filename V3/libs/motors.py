"""
Gestion très simple des moteurs pas à pas via DM860H.

Hypothèses :
- STEP (PUL) en direct sur des GPIO du Pi.
- DIR / ENA câblés sur MCP23017 (mcp3).

Objectif :
- fonctions lisibles pour lancer un ou plusieurs moteurs.
- pas de surcouche complexe.
"""

import time
from typing import Dict, Iterable

import RPi.GPIO as GPIO

from .i2c_devices import MCP23017


class StepperConfig:
    """
    Paramètres communs aux moteurs.
    """

    def __init__(
        self,
        steps_per_rev: int,
        default_rpm: float,
        min_rpm: float,
        max_rpm: float,
        accel_rpm_per_s: float,
    ) -> None:
        self.steps_per_rev = steps_per_rev
        self.default_rpm = default_rpm
        self.min_rpm = min_rpm
        self.max_rpm = max_rpm
        self.accel_rpm_per_s = accel_rpm_per_s


class MotorManager:
    """
    Gère un ensemble de moteurs nommés M1..M8.

    - step_pins : dict "Mx" -> GPIO BCM (PUL)
    - mcp_dir_ena : instance MCP23017 câblée aux DIR/ENA
    - dir_bank / ena_bank : "A" ou "B"
    - motor_bits : dict "Mx" -> index de bit 0..7 sur MCP
    """

    def __init__(
        self,
        config: StepperConfig,
        step_pins: Dict[str, int],
        mcp_dir_ena: MCP23017,
        dir_bank: str,
        ena_bank: str,
        motor_bits: Dict[str, int],
        ena_active_low: bool = True,
    ) -> None:
        self.cfg = config
        self.step_pins = step_pins
        self.mcp = mcp_dir_ena
        self.dir_bank = dir_bank
        self.ena_bank = ena_bank
        self.motor_bits = motor_bits
        self.ena_active_low = ena_active_low

        # Initialisation des GPIO STEP
        for pin in step_pins.values():
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

        # Par sécurité : tout désactivé
        self.disable_all()

    # --- Helpers DIR / ENA ---

    def _set_dir(self, motors: Iterable[str], direction_open: bool) -> None:
        """
        direction_open = True  => DIR=1 (par convention "ouverture")
        direction_open = False => DIR=0 (par convention "fermeture")
        """
        for name in motors:
            bit = self.motor_bits[name]
            level = 1 if direction_open else 0
            self.mcp.write_bit(self.dir_bank, bit, level)

    def _set_enable(self, motors: Iterable[str], enable: bool) -> None:
        """
        Active/désactive les drivers pour une liste de moteurs.
        """
        for name in motors:
            bit = self.motor_bits[name]
            if self.ena_active_low:
                level = 0 if enable else 1
            else:
                level = 1 if enable else 0
            self.mcp.write_bit(self.ena_bank, bit, level)

    def disable_all(self) -> None:
        """
        Désactive tous les drivers (sécurité).
        """
        for name in self.motor_bits.keys():
            self._set_enable([name], False)

    # --- Calcul du timing ---

    def _rpm_to_step_delay(self, rpm: float) -> float:
        rpm = max(self.cfg.min_rpm, min(self.cfg.max_rpm, rpm))
        steps_per_sec = rpm * self.cfg.steps_per_rev / 60.0
        if steps_per_sec <= 0:
            return 0.01  # fallback lent
        return 1.0 / steps_per_sec

    # --- Mouvement simple (sans rampe avancée) ---

    def move_relative(
        self,
        names: Iterable[str],
        steps: int,
        rpm: float | None = None,
        direction_open: bool = True,
    ) -> None:
        """
        Mouvement relatif :
        - names : liste de moteurs (["M1"], ["M1","M2"], etc.)
        - steps : nombre de pas (>=0)
        - rpm   : vitesse (sinon cfg.default_rpm)
        - direction_open : True => DIR=1, False => DIR=0

        NOTE : tous les moteurs donnés font les MÊMES pas (synchrones).
        """
        if steps <= 0:
            return

        rpm = rpm or self.cfg.default_rpm
        delay = self._rpm_to_step_delay(rpm)
        motors = list(names)

        self._set_dir(motors, direction_open)
        self._set_enable(motors, True)

        try:
            for _ in range(steps):
                for name in motors:
                    pin = self.step_pins[name]
                    GPIO.output(pin, GPIO.HIGH)
                time.sleep(delay)
                for name in motors:
                    pin = self.step_pins[name]
                    GPIO.output(pin, GPIO.LOW)
                time.sleep(delay)
        finally:
            # Environnement industriel : on préfère tout relâcher en fin de mouvement.
            self._set_enable(motors, False)

