# hw/i2c.py
# -*- coding: utf-8 -*-
"""
Wrapper I2C UNIQUE autour de smbus2.

Objectifs:
- Accès I2C simple et fiable
- Option: verrou (lock) pour éviter des accès concurrents (threads/callbacks)
- Option: retry simple (bruit / erreurs temporaires)
- API minimale: open/close + read/write byte + read/write block

Ce module ne dépend pas de config.yaml. Les paramètres sont passés explicitement.

Usage typique (dans hw/mcp23017.py ou hw/lcd_...):
    from hw.i2c import I2CBus

    bus = I2CBus(bus_id=1, retries=3, retry_delay_ms=5)
    bus.open()
    bus.write_byte_data(0x26, 0x00, 0xFF)
    v = bus.read_byte_data(0x26, 0x12)
    bus.close()
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar, Any

from smbus2 import SMBus

T = TypeVar("T")


class I2CError(Exception):
    """Erreur I2C (après retries)."""
    pass


@dataclass
class I2CStats:
    ops: int = 0
    errors: int = 0
    retries: int = 0


class I2CBus:
    """
    Bus I2C robuste avec:
    - open/close explicite
    - lock interne (thread-safe)
    - retry simple
    """

    def __init__(self, bus_id: int = 1, *, retries: int = 3, retry_delay_ms: int = 5, use_lock: bool = True):
        self.bus_id = int(bus_id)
        self.retries = max(1, int(retries))
        self.retry_delay_s = max(0.0, float(retry_delay_ms) / 1000.0)
        self._bus: Optional[SMBus] = None
        self._lock = threading.Lock() if use_lock else None
        self.stats = I2CStats()

    # -------------
    # Lifecycle
    # -------------

    def open(self) -> None:
        if self._bus is None:
            self._bus = SMBus(self.bus_id)

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None

    def is_open(self) -> bool:
        return self._bus is not None

    # -------------
    # Primitives
    # -------------

    def read_byte_data(self, addr: int, reg: int) -> int:
        return self._op(lambda b: int(b.read_byte_data(int(addr), int(reg))))

    def write_byte_data(self, addr: int, reg: int, value: int) -> None:
        self._op(lambda b: b.write_byte_data(int(addr), int(reg), int(value) & 0xFF))

    def read_i2c_block_data(self, addr: int, reg: int, length: int) -> list[int]:
        return self._op(lambda b: list(b.read_i2c_block_data(int(addr), int(reg), int(length))))

    def write_i2c_block_data(self, addr: int, reg: int, data: list[int]) -> None:
        # smbus2 attend une liste d'int 0..255
        payload = [int(x) & 0xFF for x in data]
        self._op(lambda b: b.write_i2c_block_data(int(addr), int(reg), payload))

    # -------------
    # Outil: "ping"
    # -------------

    def probe(self, addr: int) -> bool:
        """
        Test rapide si un périphérique répond à l'adresse.
        Méthode volontairement simple: tentative de read d'un registre 0.
        Certains périphériques peuvent NACK selon leur état, donc ce n'est pas
        une preuve absolue, mais utile en debug.
        """
        try:
            _ = self.read_byte_data(addr, 0x00)
            return True
        except Exception:
            return False

    # -------------
    # Interne: retry + lock
    # -------------

    def _op(self, fn: Callable[[SMBus], T]) -> T:
        if self._bus is None:
            raise I2CError("Bus I2C non ouvert. Appelle open() avant usage.")

        def run() -> T:
            last_exc: Optional[Exception] = None
            for attempt in range(1, self.retries + 1):
                try:
                    self.stats.ops += 1
                    return fn(self._bus)  # type: ignore[arg-type]
                except Exception as e:
                    self.stats.errors += 1
                    last_exc = e
                    if attempt < self.retries:
                        self.stats.retries += 1
                        time.sleep(self.retry_delay_s)

            raise I2CError(f"I2C op failed after {self.retries} attempts: {last_exc}") from last_exc

        if self._lock is None:
            return run()
        with self._lock:
            return run()
