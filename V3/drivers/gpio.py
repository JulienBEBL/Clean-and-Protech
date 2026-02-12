# drivers/gpio.py
"""
Ultra-simple GPIO wrapper for Raspberry Pi using lgpio only.

Goals:
- Keep API minimal and easy to use.
- Be robust: explicit open/close, track claimed GPIOs, safe cleanup.
- Support input callbacks (used for flowmeter on GPIO21, falling edge).

Notes:
- Uses BCM numbering.
- Does NOT import project config (main.py should pass GPIO numbers).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Set

import lgpio


class GpioError(RuntimeError):
    """Raised for GPIO-related errors."""


@dataclass(frozen=True)
class CallbackHandle:
    """Small wrapper around an lgpio callback object."""
    gpio: int
    _cb: object  # lgpio callback object (has .cancel())


class GPIOController:
    """
    Minimal GPIO controller using lgpio.

    Typical usage:
        gpio = GPIOController()
        gpio.apply_known_outputs({16: 0, 20: 0, 26: 0})
        gpio.claim_input(21)
        gpio.add_callback(21, edge="falling", fn=on_pulse)
        ...
        gpio.close()
    """

    def __init__(self, chip: int = 0) -> None:
        """
        Args:
            chip: gpiochip index (usually 0 on Raspberry Pi).
        """
        self._chip = chip
        self._h: Optional[int] = None
        self._claimed: Set[int] = set()
        self._callbacks: Dict[int, CallbackHandle] = {}

        try:
            self._h = lgpio.gpiochip_open(self._chip)
        except Exception as e:
            raise GpioError(f"Failed to open gpiochip{chip}: {e}") from e

    # ---------- lifecycle ----------

    def close(self) -> None:
        """Cancel callbacks, free claimed GPIOs, close chip handle."""
        if self._h is None:
            return

        # Cancel callbacks first
        for cb in list(self._callbacks.values()):
            try:
                cb._cb.cancel()
            except Exception:
                pass
        self._callbacks.clear()

        # Free claimed GPIOs
        for gpio in list(self._claimed):
            try:
                lgpio.gpio_free(self._h, gpio)
            except Exception:
                pass
        self._claimed.clear()

        # Close chip
        try:
            lgpio.gpiochip_close(self._h)
        finally:
            self._h = None

    def __enter__(self) -> "GPIOController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ---------- claiming pins ----------

    def apply_known_outputs(self, outputs: Dict[int, int]) -> None:
        """
        Claim multiple GPIOs as outputs and drive them to a known state immediately.

        Args:
            outputs: dict {gpio_bcm: level(0/1)}
        """
        for gpio, level in outputs.items():
            self.claim_output(gpio, level)

    def claim_output(self, gpio: int, initial: int = 0) -> None:
        """Claim a GPIO as output and set initial level."""
        self._ensure_open()
        level = self._coerce_level(initial)

        try:
            # claim output and immediately drive initial level
            lgpio.gpio_claim_output(self._h, gpio, level)
            self._claimed.add(gpio)
        except Exception as e:
            raise GpioError(f"Failed to claim output GPIO{gpio}: {e}") from e

    def claim_input(self, gpio: int) -> None:
        """Claim a GPIO as input."""
        self._ensure_open()
        try:
            lgpio.gpio_claim_input(self._h, gpio)
            self._claimed.add(gpio)
        except Exception as e:
            raise GpioError(f"Failed to claim input GPIO{gpio}: {e}") from e

    # ---------- I/O ----------

    def write(self, gpio: int, level: int) -> None:
        """Write 0/1 to an output GPIO."""
        self._ensure_open()
        level = self._coerce_level(level)

        try:
            lgpio.gpio_write(self._h, gpio, level)
        except Exception as e:
            raise GpioError(f"Failed to write GPIO{gpio}={level}: {e}") from e

    def read(self, gpio: int) -> int:
        """Read current level (0/1) from a GPIO."""
        self._ensure_open()
        try:
            v = lgpio.gpio_read(self._h, gpio)
            return 1 if v else 0
        except Exception as e:
            raise GpioError(f"Failed to read GPIO{gpio}: {e}") from e

    # ---------- callbacks / interrupts ----------

    def add_callback(
        self,
        gpio: int,
        edge: str,
        fn: Callable[[int, int, int], None],
    ) -> None:
        """
        Register a callback on a GPIO.

        Args:
            gpio: BCM GPIO number (must be claimed as input before).
            edge: "falling" | "rising" | "both"
            fn: callback signature: fn(gpio: int, level: int, tick: int) -> None
                - gpio: GPIO number
                - level: 0/1
                - tick: timestamp from lgpio (microseconds tick counter)
        """
        self._ensure_open()

        if gpio in self._callbacks:
            raise GpioError(f"Callback already registered for GPIO{gpio}")

        edge_const = self._edge_to_const(edge)

        try:
            cb = lgpio.callback(self._h, gpio, edge_const, fn)
            self._callbacks[gpio] = CallbackHandle(gpio=gpio, _cb=cb)
        except Exception as e:
            raise GpioError(f"Failed to add callback on GPIO{gpio} ({edge}): {e}") from e

    def remove_callback(self, gpio: int) -> None:
        """Remove a previously registered callback."""
        cb = self._callbacks.pop(gpio, None)
        if cb is None:
            return
        try:
            cb._cb.cancel()
        except Exception:
            pass

    # ---------- helpers ----------

    def _ensure_open(self) -> None:
        if self._h is None:
            raise GpioError("GPIOController is closed")

    @staticmethod
    def _coerce_level(level: int) -> int:
        if level in (0, 1):
            return level
        if isinstance(level, bool):
            return 1 if level else 0
        raise GpioError(f"Invalid GPIO level: {level} (expected 0/1)")

    @staticmethod
    def _edge_to_const(edge: str) -> int:
        e = edge.strip().lower()
        if e == "falling":
            return lgpio.FALLING_EDGE
        if e == "rising":
            return lgpio.RISING_EDGE
        if e == "both":
            return lgpio.BOTH_EDGES
        raise GpioError(f"Invalid edge '{edge}' (use: falling/rising/both)")
