# driver/stepgen_lgpio.py
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from hal.gpio_lgpio import GpioLgpio


@dataclass(frozen=True)
class StepTiming:
    pulse_high_us: int = 2
    pulse_low_us: int = 2


@dataclass(frozen=True)
class MotionProfile:
    max_steps_s: float
    accel_steps_s2: float


class StepGenLgpio:
    """
    Générateur de pulses STEP.
    - Utilise lgpio pour toggler les GPIO STEP.
    - Timing basé sur time.monotonic_ns() (busy-wait léger).
    - Aucun I2C ici.

    Limitation: pas de synchronisation fine inter-moteurs, mais démarrage quasi simultané possible.
    """

    def __init__(self, gpio: GpioLgpio, step_pins: Dict[str, int], timing: StepTiming):
        self.gpio = gpio
        self.step_pins = step_pins
        self.timing = timing

        self._threads: Dict[str, threading.Thread] = {}
        self._stop_flags: Dict[str, threading.Event] = {}

        for mid, bcm in self.step_pins.items():
            self.gpio.claim_output(bcm, initial=0)

    def is_busy(self, motor_id: str) -> bool:
        t = self._threads.get(motor_id)
        return bool(t and t.is_alive())

    def stop(self, motor_id: str) -> None:
        ev = self._stop_flags.get(motor_id)
        if ev:
            ev.set()

    def stop_all(self) -> None:
        for ev in self._stop_flags.values():
            ev.set()

    def move_steps(self, motor_id: str, steps: int, profile: MotionProfile) -> None:
        """
        Lance un mouvement (asynchrone).
        steps peut être >0 (sens déjà géré ailleurs) - ici c'est juste le nombre d'impulsions.
        """
        if steps <= 0:
            return
        if self.is_busy(motor_id):
            raise RuntimeError(f"Moteur {motor_id} déjà en mouvement")

        stop_ev = threading.Event()
        self._stop_flags[motor_id] = stop_ev

        th = threading.Thread(
            target=self._run_move,
            name=f"stepgen-{motor_id}",
            args=(motor_id, steps, profile, stop_ev),
            daemon=True,
        )
        self._threads[motor_id] = th
        th.start()

    def wait(self, motor_id: str, timeout_s: Optional[float] = None) -> bool:
        t = self._threads.get(motor_id)
        if not t:
            return True
        t.join(timeout=timeout_s)
        return not t.is_alive()

    def wait_all(self, timeout_s: Optional[float] = None) -> bool:
        ok = True
        for mid in list(self._threads.keys()):
            ok = self.wait(mid, timeout_s=timeout_s) and ok
        return ok

    # -------------------- interne --------------------

    def _run_move(self, motor_id: str, total_steps: int, profile: MotionProfile, stop_ev: threading.Event) -> None:
        bcm = self.step_pins[motor_id]

        # Trapezoïde simple: accel / plateau / decel.
        vmax = float(profile.max_steps_s)
        a = float(profile.accel_steps_s2)

        if vmax <= 0 or a <= 0:
            raise ValueError("profile invalide")

        # nb steps pour atteindre vmax: v^2 = 2 a s => s = v^2 / (2a)
        accel_steps = int((vmax * vmax) / (2.0 * a))
        if accel_steps < 1:
            accel_steps = 1

        # si move trop court, profil triangulaire
        if 2 * accel_steps > total_steps:
            accel_steps = total_steps // 2
            cruise_steps = total_steps - 2 * accel_steps
        else:
            cruise_steps = total_steps - 2 * accel_steps

        # bornes timing
        high_ns = int(self.timing.pulse_high_us * 1000)
        low_ns = int(self.timing.pulse_low_us * 1000)
        min_period_ns = high_ns + low_ns

        def busy_wait_until(target_ns: int) -> None:
            while time.monotonic_ns() < target_ns:
                pass

        step_done = 0

        # Accel: on augmente la vitesse => on réduit la période
        # On calcule une vitesse cible par pas (linéaire en steps) pour rester simple.
        for i in range(accel_steps):
            if stop_ev.is_set():
                return
            # v = sqrt(2 a s)
            s = i + 1
            v = (2.0 * a * s) ** 0.5
            if v > vmax:
                v = vmax
            period_ns = int(1e9 / v)
            if period_ns < min_period_ns:
                period_ns = min_period_ns
            self._one_pulse(bcm, high_ns, low_ns, period_ns, busy_wait_until)
            step_done += 1

        # Cruise
        if cruise_steps > 0:
            period_ns = int(1e9 / vmax)
            if period_ns < min_period_ns:
                period_ns = min_period_ns
            for _ in range(cruise_steps):
                if stop_ev.is_set():
                    return
                self._one_pulse(bcm, high_ns, low_ns, period_ns, busy_wait_until)
                step_done += 1

        # Decel (symétrique)
        for i in range(accel_steps, 0, -1):
            if stop_ev.is_set():
                return
            s = i
            v = (2.0 * a * s) ** 0.5
            if v > vmax:
                v = vmax
            period_ns = int(1e9 / v)
            if period_ns < min_period_ns:
                period_ns = min_period_ns
            self._one_pulse(bcm, high_ns, low_ns, period_ns, busy_wait_until)
            step_done += 1

    def _one_pulse(self, bcm: int, high_ns: int, low_ns: int, period_ns: int, busy_wait_until) -> None:
        t0 = time.monotonic_ns()
        # HIGH
        self.gpio.write(bcm, 1)
        busy_wait_until(t0 + high_ns)
        # LOW
        self.gpio.write(bcm, 0)
        busy_wait_until(t0 + high_ns + low_ns)
        # fin de période
        busy_wait_until(t0 + period_ns)
