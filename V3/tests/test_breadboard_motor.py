from __future__ import annotations

import math
import time
from dataclasses import dataclass

import lgpio

# =============================================================================
# CONFIGURATION
# =============================================================================

MOTOR_NAME = "TEST_VANNE"

# GPIO BCM
PUL_PIN = 20
DIR_PIN = 21

# sens moteur
DIRECTION_LEVELS = {
    "ouverture": 1,
    "fermeture": 0,
}

# paramètres mouvement
OUVERTURE_STEPS = 30000
FERMETURE_STEPS = 32000

OUVERTURE_SPEED_SPS = 10000.0
FERMETURE_SPEED_SPS = 10000.0

OUVERTURE_ACCEL = 3200.0
OUVERTURE_DECEL = 9600.0

FERMETURE_ACCEL = 3200.0
FERMETURE_DECEL = 9600.0

# timings driver (marges confortables)
DIR_SETUP_SECONDS = 10e-6
PULSE_HIGH_SECONDS = 8e-6
PULSE_LOW_MIN_SECONDS = 8e-6

# sécurité
MOVE_TIMEOUT_SECONDS: float | None = 30.0


# =============================================================================
# STRUCTURES
# =============================================================================

@dataclass
class MotorPins:
    pul: int
    dir: int


# =============================================================================
# CONTROLEUR
# =============================================================================

class StepperMotorController:

    def __init__(self) -> None:
        self._h: int | None = None
        self._opened = False
        self._pins = MotorPins(PUL_PIN, DIR_PIN)

    # -------------------------------------------------------------------------

    def open(self) -> None:

        if self._opened:
            return

        self._h = lgpio.gpiochip_open(0)

        lgpio.gpio_claim_output(self._h, self._pins.pul, 0)
        lgpio.gpio_claim_output(self._h, self._pins.dir, 0)

        lgpio.gpio_write(self._h, self._pins.pul, 0)
        lgpio.gpio_write(self._h, self._pins.dir, 0)

        self._opened = True

    # -------------------------------------------------------------------------

    def close(self) -> None:

        if self._h is None:
            return

        lgpio.gpio_write(self._h, self._pins.pul, 0)

        lgpio.gpiochip_close(self._h)

        self._h = None
        self._opened = False

    # -------------------------------------------------------------------------

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # =============================================================================
    # API METIER
    # =============================================================================

    def ouverture(self, motor_name: str) -> None:

        if motor_name != MOTOR_NAME:
            raise ValueError("motor_name invalide")

        self.move_steps_ramp(
            motor_name,
            OUVERTURE_STEPS,
            "ouverture",
            OUVERTURE_SPEED_SPS,
            OUVERTURE_ACCEL,
            OUVERTURE_DECEL,
        )

    # -------------------------------------------------------------------------

    def fermeture(self, motor_name: str) -> None:

        if motor_name != MOTOR_NAME:
            raise ValueError("motor_name invalide")

        self.move_steps_ramp(
            motor_name,
            FERMETURE_STEPS,
            "fermeture",
            FERMETURE_SPEED_SPS,
            FERMETURE_ACCEL,
            FERMETURE_DECEL,
        )

    # =============================================================================
    # MOUVEMENT
    # =============================================================================

    def move_steps_ramp(
        self,
        motor_name: str,
        steps: int,
        direction: str,
        speed_sps: float,
        accel: float,
        decel: float,
    ) -> None:

        if not self._opened:
            raise RuntimeError("GPIO non ouverts")

        if direction not in DIRECTION_LEVELS:
            raise ValueError("direction invalide")

        lgpio.gpio_write(self._h, self._pins.dir, DIRECTION_LEVELS[direction])

        time.sleep(DIR_SETUP_SECONDS)

        periods = self._build_profile(steps, speed_sps, accel, decel)

        start = time.perf_counter()

        for period in periods:

            if MOVE_TIMEOUT_SECONDS is not None:
                if time.perf_counter() - start > MOVE_TIMEOUT_SECONDS:
                    raise RuntimeError("timeout mouvement")

            self._emit_step(period)

    # =============================================================================

    def _emit_step(self, period: float) -> None:

        high = min(PULSE_HIGH_SECONDS, period / 2)
        low = max(period - high, PULSE_LOW_MIN_SECONDS)

        lgpio.gpio_write(self._h, self._pins.pul, 1)
        self._sleep(high)

        lgpio.gpio_write(self._h, self._pins.pul, 0)
        self._sleep(low)

    # =============================================================================

    def _build_profile(self, total_steps, target_speed, accel, decel):

        steps_accel = int((target_speed ** 2) / (2 * accel))
        steps_decel = int((target_speed ** 2) / (2 * decel))

        if steps_accel + steps_decel < total_steps:

            steps_const = total_steps - steps_accel - steps_decel
            peak = target_speed

        else:

            peak = math.sqrt(
                (2 * total_steps * accel * decel) / (accel + decel)
            )

            steps_accel = int((peak ** 2) / (2 * accel))
            steps_decel = total_steps - steps_accel
            steps_const = 0

        periods = []

        for i in range(1, steps_accel + 1):

            speed = min(math.sqrt(2 * accel * i), peak)
            periods.append(1 / speed)

        for _ in range(steps_const):

            periods.append(1 / peak)

        for i in range(steps_decel, 0, -1):

            speed = min(math.sqrt(2 * decel * i), peak)
            periods.append(1 / speed)

        if len(periods) > total_steps:
            periods = periods[:total_steps]

        if len(periods) < total_steps:
            periods += [1 / peak] * (total_steps - len(periods))

        return periods

    # =============================================================================

    def _sleep(self, duration):

        if duration <= 0:
            return

        if duration > 0.002:
            time.sleep(duration - 0.001)

        end = time.perf_counter() + min(duration, 0.001)

        while time.perf_counter() < end:
            pass


# =============================================================================
# TEST
# =============================================================================

def main():

    print("Test moteur")

    with StepperMotorController() as motor:

        print("ouverture")
        motor.ouverture(MOTOR_NAME)

        time.sleep(1)

        print("fermeture")
        motor.fermeture(MOTOR_NAME)

        time.sleep(1)

        print("ouverture")
        motor.ouverture(MOTOR_NAME)

    print("fin test")


if __name__ == "__main__":
    main()