# hal/gpio_lgpio.py
from __future__ import annotations

import lgpio


class GpioLgpio:
    """
    Accès GPIO Raspberry Pi via lgpio (/dev/gpiochip*).
    Utilisation recommandée en root (service systemd root) pour éviter les soucis de permissions.
    """

    def __init__(self, chip: int = 0):
        self.chip = chip
        self.h = lgpio.gpiochip_open(chip)

    def close(self) -> None:
        try:
            lgpio.gpiochip_close(self.h)
        except Exception:
            pass

    def claim_output(self, bcm: int, initial: int = 0) -> None:
        lgpio.gpio_claim_output(self.h, bcm, int(initial))

    def claim_input(self, bcm: int) -> None:
        lgpio.gpio_claim_input(self.h, bcm)

    def write(self, bcm: int, level: int) -> None:
        lgpio.gpio_write(self.h, bcm, int(level))

    def read(self, bcm: int) -> int:
        return int(lgpio.gpio_read(self.h, bcm))
