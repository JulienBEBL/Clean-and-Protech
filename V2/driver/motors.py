# driver/motors.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from hw.mcp_hub import MCPHub
from hal.gpio_lgpio import GpioLgpio
from driver.stepgen_lgpio import StepGenLgpio, StepTiming
from driver.motor_axis import MotorAxis, MotorConfig


@dataclass(frozen=True)
class MotorsConfig:
    microsteps_per_rev: int = 3200
    ena_settle_ms: int = 10
    dir_setup_us: int = 5
    invert_dir: Dict[str, bool] = None  # ex {"M1": False, ...}


class Motors:
    def __init__(self, gpio: GpioLgpio, mcp: MCPHub, step_pins: Dict[str, int], cfg: MotorsConfig):
        self.gpio = gpio
        self.mcp = mcp
        self.cfg = cfg

        timing = StepTiming(pulse_high_us=2, pulse_low_us=2)
        self.stepgen = StepGenLgpio(gpio=gpio, step_pins=step_pins, timing=timing)

        inv = cfg.invert_dir or {}

        self.axes: Dict[str, MotorAxis] = {}
        for i in range(1, 9):
            mid = f"M{i}"
            mc = MotorConfig(
                motor_id=mid,
                index=i,
                microsteps_per_rev=cfg.microsteps_per_rev,
                invert_dir=bool(inv.get(mid, False)),
                ena_settle_ms=cfg.ena_settle_ms,
                dir_setup_us=cfg.dir_setup_us,
            )
            self.axes[mid] = MotorAxis(mc, mcp=mcp, stepgen=self.stepgen)

        # accès direct style motors.M1
        for mid, ax in self.axes.items():
            setattr(self, mid, ax)

    def disable_all(self) -> None:
        for ax in self.axes.values():
            ax.disable()

    def stop_all(self) -> None:
        self.stepgen.stop_all()
        # Optionnel: on coupe ENA (safe)
        self.disable_all()

    def wait_all(self, timeout_s: float | None = None) -> bool:
        return self.stepgen.wait_all(timeout_s=timeout_s)

    # ---------------- groupe ----------------

    def move_all_turns(self, turns: float, max_rpm: float, accel_rpm_s: float, motors: List[str] | None = None) -> None:
        """
        Lance les mouvements (quasi simultané) sur une liste de moteurs.
        turns peut être + (ex ouverture) ou - (fermeture) selon ta convention.
        """
        targets = motors or list(self.axes.keys())

        # 1) enable + dir sur tous (I2C), puis 2) pulses sur tous (GPIO)
        # On évite de lancer des pulses avant que tous aient DIR/ENA configurés.
        for mid in targets:
            ax = self.axes[mid]
            ax.enable()

        # dir (0/1) dépend du signe des tours
        direction = 1 if turns > 0 else 0
        for mid in targets:
            ax = self.axes[mid]
            ax.set_dir(direction)

        # lancement pulses
        for mid in targets:
            ax = self.axes[mid]
            ax.move_turns(turns=turns, max_rpm=max_rpm, accel_rpm_s=accel_rpm_s)

    def open_all(self, turns: float = 10.0, max_rpm: float = 50.0, accel_rpm_s: float = 100.0) -> None:
        self.move_all_turns(turns=abs(turns), max_rpm=max_rpm, accel_rpm_s=accel_rpm_s)

    def close_all(self, turns: float = 10.0, max_rpm: float = 50.0, accel_rpm_s: float = 100.0) -> None:
        self.move_all_turns(turns=-abs(turns), max_rpm=max_rpm, accel_rpm_s=accel_rpm_s)