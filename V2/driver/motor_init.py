# driver/motor_init.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from driver.motors import Motors


@dataclass(frozen=True)
class MotorInitConfig:
    enabled: bool = True

    # comportement par défaut
    mode: str = "open_all"          # "open_all" / "close_all" / "none"
    turns: float = 10.0             # 10 tours = ouverture complète typique chez toi
    max_rpm: float = 30.0
    accel_rpm_s: float = 60.0

    # disable moteurs après init
    disable_after: bool = True


class MotorInitializer:
    def __init__(self, motors: Motors, cfg: MotorInitConfig):
        self.motors = motors
        self.cfg = cfg

    def run(self) -> None:
        if not self.cfg.enabled or self.cfg.mode == "none":
            return

        if self.cfg.mode == "open_all":
            self.motors.open_all(
                turns=self.cfg.turns,
                max_rpm=self.cfg.max_rpm,
                accel_rpm_s=self.cfg.accel_rpm_s,
            )
            self.motors.wait_all()

        elif self.cfg.mode == "close_all":
            self.motors.close_all(
                turns=self.cfg.turns,
                max_rpm=self.cfg.max_rpm,
                accel_rpm_s=self.cfg.accel_rpm_s,
            )
            self.motors.wait_all()

        else:
            raise ValueError(f"mode init moteurs inconnu: {self.cfg.mode}")

        if self.cfg.disable_after:
            self.motors.disable_all()
