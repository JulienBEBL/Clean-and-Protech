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
PUL_PIN = 21
DIR_PIN = 20

# sens moteur
DIRECTION_LEVELS = {
    "ouverture": 1,
    "fermeture": 0,
}

# paramètres mouvement
OUVERTURE_STEPS = 30_000
FERMETURE_STEPS = 31_500

OUVERTURE_SPEED_SPS = 9800.0
FERMETURE_SPEED_SPS = 9800.0

OUVERTURE_ACCEL = 3200.0
OUVERTURE_DECEL = 8500.0

FERMETURE_ACCEL = 3200.0
FERMETURE_DECEL = 8500.0

RAMP_ACCEL_TIME_S = 1.5
RAMP_DECEL_TIME_S = 1.5

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

    def open(self) -> None:

        if self._opened:
            return

        self._h = lgpio.gpiochip_open(0)

        lgpio.gpio_claim_output(self._h, self._pins.pul, 0)
        lgpio.gpio_claim_output(self._h, self._pins.dir, 0)

        lgpio.gpio_write(self._h, self._pins.pul, 0)
        lgpio.gpio_write(self._h, self._pins.dir, 0)

        self._opened = True

    def close(self) -> None:

        if self._h is None:
            return

        lgpio.gpio_write(self._h, self._pins.pul, 0)

        lgpio.gpiochip_close(self._h)

        self._h = None
        self._opened = False

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

        if motor_name != MOTOR_NAME:
            raise ValueError("motor_name invalide")

        nsteps = int(steps)
        if nsteps < 0:
            raise ValueError("steps must be >= 0")
        if nsteps == 0:
            return

        if direction not in DIRECTION_LEVELS:
            raise ValueError("direction invalide")

        a = self._validate_speed(accel)
        v = self._validate_speed(speed_sps)
        d_end = self._validate_speed(decel)

        if not (a < d_end):
            raise ValueError("accel must be strictly < decel")
        if v < d_end:
            raise ValueError("speed_sps must be >= decel")

        lgpio.gpio_write(self._h, self._pins.dir, DIRECTION_LEVELS[direction])
        time.sleep(DIR_SETUP_SECONDS)

        s_acc_nom = int(0.5 * (a + v) * RAMP_ACCEL_TIME_S)
        s_dec_nom = int(0.5 * (v + d_end) * RAMP_DECEL_TIME_S)

        if s_acc_nom + s_dec_nom <= nsteps:
            s_acc = s_acc_nom
            s_dec = s_dec_nom
            s_cruise = nsteps - s_acc - s_dec
        else:
            total_nom = max(1, s_acc_nom + s_dec_nom)
            s_acc = int(nsteps * (s_acc_nom / total_nom))
            s_acc = max(0, min(s_acc, nsteps))
            s_dec = nsteps - s_acc
            s_cruise = 0

        # accel
        if s_acc > 0:
            for i in range(s_acc):
                frac = (i + 1) / s_acc
                sps = a + (v - a) * frac
                half_us = self._compute_half_period_us(sps)

                lgpio.gpio_write(self._h, self._pins.pul, 1)
                self._sleep_us(half_us)
                lgpio.gpio_write(self._h, self._pins.pul, 0)
                self._sleep_us(half_us)

        # cruise
        if s_cruise > 0:
            half_us = self._compute_half_period_us(v)
            for _ in range(s_cruise):
                lgpio.gpio_write(self._h, self._pins.pul, 1)
                self._sleep_us(half_us)
                lgpio.gpio_write(self._h, self._pins.pul, 0)
                self._sleep_us(half_us)

        # decel
        if s_dec > 0:
            for i in range(s_dec):
                frac = (i + 1) / s_dec
                sps = v + (d_end - v) * frac
                half_us = self._compute_half_period_us(sps)

                lgpio.gpio_write(self._h, self._pins.pul, 1)
                self._sleep_us(half_us)
                lgpio.gpio_write(self._h, self._pins.pul, 0)
                self._sleep_us(half_us)

        lgpio.gpio_write(self._h, self._pins.pul, 0)

    def _emit_step(self, period: float) -> None:

        high = min(PULSE_HIGH_SECONDS, period / 2)
        low = max(period - high, PULSE_LOW_MIN_SECONDS)

        lgpio.gpio_write(self._h, self._pins.pul, 1)
        self._sleep(high)

        lgpio.gpio_write(self._h, self._pins.pul, 0)
        self._sleep(low)

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

    def _sleep_us(self, duration_us: int) -> None:

        if duration_us <= 0:
            return

        duration_s = duration_us / 1_000_000.0

        if duration_s > 0.002:
            time.sleep(duration_s - 0.001)

        end = time.perf_counter() + min(duration_s, 0.001)

        while time.perf_counter() < end:
            pass

    def _validate_speed(self, value: float) -> float:
        v = float(value)
        if v <= 0:
            raise ValueError("speed must be > 0")
        return v

    def _compute_half_period_us(self, sps: float) -> int:
        sps = self._validate_speed(sps)
        half_period_us = int(500000.0 / sps)

        min_half_us = int(max(PULSE_HIGH_SECONDS, PULSE_LOW_MIN_SECONDS) * 1_000_000)
        if half_period_us < min_half_us:
            half_period_us = min_half_us

        return half_period_us

# =============================================================================
# TEST
# =============================================================================

def main():

    # -----------------------------
    # PARAMETRES
    # -----------------------------

    cycles = 100        # nombre de cycles ouverture/fermeture
    pause_s = 2      # pause entre mouvements (secondes)

    print("=================================")
    print("TEST MOTEUR VANNE")
    print("cycles :", cycles)
    print("pause  :", pause_s, "s")
    print("=================================")

    with StepperMotorController() as motor:

        # --------------------------------
        # TEST SIMPLE
        # --------------------------------

        #print("\nTest initial")

        # print("Fermeture")
        # motor.move_steps_ramp(MOTOR_NAME, steps=31_500, direction="fermeture", speed_sps=9800.0, accel=3200.0, decel=8500.0)
        # time.sleep(pause_s)
        # print("Ouverture")
        # motor.move_steps_ramp(MOTOR_NAME, steps=30_000, direction="ouverture", speed_sps=9800.0, accel=3200.0, decel=8500.0)
        # time.sleep(pause_s)
        # print("Fermeture")
        # motor.move_steps_ramp(MOTOR_NAME, steps=31_500, direction="fermeture", speed_sps=9800.0, accel=3200.0, decel=8500.0)
        # time.sleep(pause_s)
        # print("Ouverture")
        # motor.move_steps_ramp(MOTOR_NAME, steps=30_000, direction="ouverture", speed_sps=9800.0, accel=3200.0, decel=8500.0)
        # time.sleep(pause_s)
        # print("END")
        # time.sleep(90_000_000)

        # --------------------------------
        # RODAGE AUTOMATIQUE
        # --------------------------------

        print("\nDébut cycles automatiques")

        for i in range(cycles):

            print(f"\nCycle {i+1}/{cycles}")
            print(time.strftime("%H:%M:%S"))
            
            # print("F")
            # motor.move_steps_ramp(MOTOR_NAME, steps=900, direction="fermeture", speed_sps=400, accel=300, decel=350)
            # time.sleep(pause_s)
            # print("O")
            # motor.move_steps_ramp(MOTOR_NAME, steps=900, direction="ouverture", speed_sps=400, accel=300, decel=350)
            # time.sleep(pause_s)

            print("Fermeture")
            motor.fermeture(MOTOR_NAME)
            time.sleep(pause_s)

            print("Ouverture")
            motor.ouverture(MOTOR_NAME)
            time.sleep(pause_s)

    print("\nRodage terminé")

if __name__ == "__main__":
    main()
