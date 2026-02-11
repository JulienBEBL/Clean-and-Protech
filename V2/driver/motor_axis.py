# driver/motor_axis.py
from __future__ import annotations

import time
from dataclasses import dataclass

from hw.mcp_hub import MCPHub
from driver.stepgen_lgpio import StepGenLgpio, MotionProfile


@dataclass(frozen=True)
class MotorConfig:
    motor_id: str            # "M1"
    index: int               # 1..8
    microsteps_per_rev: int  # 3200
    invert_dir: bool = False
    ena_settle_ms: int = 10
    dir_setup_us: int = 5


class MotorAxis:
    """
    Abstraction moteur:
    - DIR/ENA sur MCP3 via MCPHub
    - STEP sur GPIO via StepGen
    """

    def __init__(self, cfg: MotorConfig, mcp: MCPHub, stepgen: StepGenLgpio):
        self.cfg = cfg
        self.mcp = mcp
        self.stepgen = stepgen

    def enable(self) -> None:
        self.mcp.motor_set_enable(self.cfg.index, True)
        time.sleep(self.cfg.ena_settle_ms / 1000.0)

    def disable(self) -> None:
        self.mcp.motor_set_enable(self.cfg.index, False)

    def set_dir(self, direction: int) -> None:
        self.mcp.motor_set_dir(self.cfg.index, direction, invert=self.cfg.invert_dir)
        # DM860H demande ~2 us min, on met un peu plus (dir_setup_us)
        time.sleep(self.cfg.dir_setup_us / 1_000_000.0)

    def is_busy(self) -> bool:
        return self.stepgen.is_busy(self.cfg.motor_id)

    def stop(self) -> None:
        self.stepgen.stop(self.cfg.motor_id)

    def wait(self, timeout_s: float | None = None) -> bool:
        return self.stepgen.wait(self.cfg.motor_id, timeout_s=timeout_s)

    def move_steps(self, steps: int, max_steps_s: float, accel_steps_s2: float) -> None:
        """
        Mouvement relatif:
        - steps >0 => direction 1
        - steps <0 => direction 0
        """
        if steps == 0:
            return

        direction = 1 if steps > 0 else 0
        nsteps = abs(int(steps))

        self.enable()
        self.set_dir(direction)

        prof = MotionProfile(max_steps_s=float(max_steps_s), accel_steps_s2=float(accel_steps_s2))
        self.stepgen.move_steps(self.cfg.motor_id, nsteps, prof)

    def move_turns(self, turns: float, max_rpm: float, accel_rpm_s: float) -> None:
        """
        Mouvement en tours (turns peut être négatif).
        max_rpm: vitesse max
        accel_rpm_s: accélération en rpm/s (douce => couple)
        """
        steps = int(round(turns * self.cfg.microsteps_per_rev))

        # rpm -> steps/s
        max_steps_s = (max_rpm * self.cfg.microsteps_per_rev) / 60.0

        # rpm/s -> steps/s²
        accel_steps_s2 = (accel_rpm_s * self.cfg.microsteps_per_rev) / 60.0

        self.move_steps(steps=steps, max_steps_s=max_steps_s, accel_steps_s2=accel_steps_s2)