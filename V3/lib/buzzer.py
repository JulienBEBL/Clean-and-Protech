"""
buzzer.py — driver buzzer passif via lgpio (Raspberry Pi 5)

- PWM via lgpio.tx_pwm() (simple + précis).
- API haut niveau:
  - beep(time_ms=100, power_pct=80, repeat=5, freq_hz=2000, gap_ms=60)
  - ringtone_startup()

Notes:
- "power_pct" est un duty cycle PWM. La "puissance sonore" n'est pas linéaire.
- Le buzzer magnétique est souvent plus efficace proche de sa fréquence nominale (ici 2 kHz).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple, Optional

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio is required on Raspberry Pi OS (Bookworm). Install python3-lgpio.") from e


# ----------------------------
# Constantes / Config (à adapter)
# ----------------------------
DEFAULT_GPIO_CHIP_INDEX = 0     # /dev/gpiochip0
DEFAULT_BUZZER_GPIO = 26        # BCM 26
DEFAULT_FREQ_HZ = 2000          # nominal buzzer
DEFAULT_GAP_MS = 60

# Si ton étage transistor inverse le signal, mets True
INVERT_OUTPUT = False


# ----------------------------
# Exceptions
# ----------------------------
class BuzzerError(Exception):
    """Base error for buzzer driver."""


class BuzzerNotInitializedError(BuzzerError):
    """Raised when using the buzzer before init/open."""


# ----------------------------
# Config
# ----------------------------
@dataclass(frozen=True)
class BuzzerConfig:
    gpiochip_index: int = DEFAULT_GPIO_CHIP_INDEX
    gpio: int = DEFAULT_BUZZER_GPIO
    default_freq_hz: int = DEFAULT_FREQ_HZ


# ----------------------------
# Driver
# ----------------------------
class Buzzer:
    """
    Buzzer passif piloté par PWM (lgpio.tx_pwm).

    Usage:
        bz = Buzzer()
        bz.open()
        bz.beep(time_ms=100, power_pct=80, repeat=3)
        bz.ringtone_startup()
        bz.close()

    ou:
        with Buzzer() as bz:
            bz.beep(...)
    """

    def __init__(self, config: BuzzerConfig = BuzzerConfig()):
        self.config = config
        self._chip: Optional[int] = None
        self._is_on: bool = False

    # ---- lifecycle ----
    def open(self) -> None:
        if self._chip is not None:
            return

        try:
            chip = lgpio.gpiochip_open(self.config.gpiochip_index)
            # claim output with initial level low
            lgpio.gpio_claim_output(chip, self.config.gpio, 0 if not INVERT_OUTPUT else 1)
            self._chip = chip
            self._is_on = False
            self.off()
        except Exception as e:
            raise BuzzerError(f"Failed to open buzzer on gpiochip{self.config.gpiochip_index}, gpio={self.config.gpio}: {e}") from e

    def close(self) -> None:
        if self._chip is None:
            return
        try:
            self.off()
        finally:
            try:
                lgpio.gpiochip_close(self._chip)
            finally:
                self._chip = None
                self._is_on = False

    def __enter__(self) -> "Buzzer":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise BuzzerNotInitializedError("Buzzer not initialized. Call open() first.")
        return self._chip

    # ---- low level ----
    @staticmethod
    def _clamp_int(v: int, lo: int, hi: int) -> int:
        return lo if v < lo else hi if v > hi else v

    def _apply_pwm(self, freq_hz: int, duty_pct: int) -> None:
        chip = self._require_open()

        f = self._clamp_int(int(freq_hz), 1, 50_000)   # garde-fou
        d = self._clamp_int(int(duty_pct), 0, 100)

        # inversion logique si demandé
        if INVERT_OUTPUT:
            d = 100 - d

        try:
            # lgpio.tx_pwm(handle, gpio, frequency, dutycycle_percent)
            lgpio.tx_pwm(chip, self.config.gpio, f, d)
            self._is_on = d > 0
        except Exception as e:
            raise BuzzerError(f"tx_pwm failed (gpio={self.config.gpio}, f={f}, duty={d}%): {e}") from e

    # ---- public API ----
    def on(self, freq_hz: Optional[int] = None, power_pct: int = 80) -> None:
        """Active le buzzer en continu (PWM)."""
        f = self.config.default_freq_hz if freq_hz is None else int(freq_hz)
        self._apply_pwm(f, power_pct)

    def off(self) -> None:
        """Coupe le buzzer (duty=0)."""
        # duty=0 stoppe l’audio (et évite un état haut continu).
        self._apply_pwm(self.config.default_freq_hz, 0)

    def beep(
        self,
        time_ms: int = 100,
        power_pct: int = 50,
        repeat: int = 1,
        freq_hz: int = DEFAULT_FREQ_HZ,
        gap_ms: int = DEFAULT_GAP_MS,
    ) -> None:
        """
        Bips simples.

        - time_ms: durée ON de chaque bip
        - power_pct: duty cycle (0..100)
        - repeat: nb répétitions
        - freq_hz: fréquence PWM
        - gap_ms: pause OFF entre bips
        """
        chip = self._require_open()  # valide état open

        t_ms = self._clamp_int(int(time_ms), 1, 10_000)
        r = self._clamp_int(int(repeat), 1, 100)
        gap = self._clamp_int(int(gap_ms), 0, 10_000)

        for i in range(r):
            self._apply_pwm(freq_hz, power_pct)
            time.sleep(t_ms / 1000.0)
            self.off()
            if gap > 0 and i < r - 1:
                time.sleep(gap / 1000.0)

    def play(self, sequence: Sequence[Tuple[int, int, int, int]]) -> None:
        """
        Joue une séquence: (freq_hz, time_ms, power_pct, gap_ms)

        Exemple:
            [(2000, 80, 70, 40), (2500, 80, 70, 80)]
        """
        self._require_open()
        for freq_hz, time_ms, power_pct, gap_ms in sequence:
            self._apply_pwm(freq_hz, power_pct)
            time.sleep(max(1, int(time_ms)) / 1000.0)
            self.off()
            if int(gap_ms) > 0:
                time.sleep(int(gap_ms) / 1000.0)

    def ringtone_startup(self) -> None:
        """
        Petite sonnerie "démarrage machine" simple et agréable.
        (Tu personnaliseras ensuite.)
        """
        seq = [
            (1800, 80, 70, 40),
            (2200, 80, 70, 40),
            (2600, 90, 75, 80),
            (2200, 60, 60, 30),
            (3000, 120, 80, 0),
        ]
        self.play(seq)