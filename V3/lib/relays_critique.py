"""
relays_critique.py — Relais critiques via lgpio (Raspberry Pi 5)

Relais:
- POMPE_OFF (BCM20): impulsion 250 ms pour simuler un appui sur bouton arrêt.
- AIR (BCM16): ON/OFF, avec option durée (auto-OFF) gérée via tick().

Philosophie:
- Pas de threads.
- Pas de blocage inutile (sauf la fonction pompe_off() qui doit *réellement* simuler 250 ms
  -> on propose 2 variantes: bloquante (simple) et non-bloquante (tick)).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio is required. Install python3-lgpio on Raspberry Pi OS.") from e


# ----------------------------
# Config matériel (figé PCB)
# ----------------------------
GPIOCHIP_INDEX = 0
GPIO_POMPE_OFF = 20  # BCM20
GPIO_AIR = 16        # BCM16

# Relais actifs à 1 par défaut (met à True si ton module est actif bas)
ACTIVE_LOW = False


class RelaysError(Exception):
    pass


class RelaysNotInitializedError(RelaysError):
    pass


@dataclass(frozen=True)
class RelaysConfig:
    gpiochip_index: int = GPIOCHIP_INDEX
    gpio_pompe_off: int = GPIO_POMPE_OFF
    gpio_air: int = GPIO_AIR
    active_low: bool = ACTIVE_LOW
    pompe_pulse_s: float = 0.250


class RelaysCritique:
    """
    Driver relais critiques.

    API principale:
      - set_pompe_off()  (impulsion 250 ms)  -> version bloquante
      - set_air_on(time_s: float | None = None)
      - set_air_off()
      - tick()  (à appeler dans la loop pour gérer auto-off air, et option non-bloquante pompe)

    Option avancée:
      - set_pompe_off_async() + tick() (si tu veux absolument éviter tout sleep)
    """

    def __init__(self, config: RelaysConfig = RelaysConfig()):
        if config.pompe_pulse_s <= 0:
            raise ValueError("pompe_pulse_s must be > 0")
        self.config = config
        self._chip: Optional[int] = None

        self._air_deadline: Optional[float] = None  # monotonic timestamp
        self._pompe_deadline: Optional[float] = None
        self._pompe_async_active: bool = False

    # -----------------
    # lifecycle
    # -----------------
    def open(self) -> None:
        if self._chip is not None:
            return
        try:
            chip = lgpio.gpiochip_open(self.config.gpiochip_index)

            # outputs, safe state = OFF
            lgpio.gpio_claim_output(chip, self.config.gpio_pompe_off, self._lvl_off())
            lgpio.gpio_claim_output(chip, self.config.gpio_air, self._lvl_off())

            self._chip = chip
            self._air_deadline = None
            self._pompe_deadline = None
            self._pompe_async_active = False

            # enforce off
            self._write(self.config.gpio_pompe_off, False)
            self._write(self.config.gpio_air, False)

        except Exception as e:
            self._chip = None
            raise RelaysError(f"Failed to open relays on gpiochip{self.config.gpiochip_index}: {e}") from e

    def close(self) -> None:
        if self._chip is None:
            return
        try:
            # safe off
            self._write(self.config.gpio_pompe_off, False)
            self._write(self.config.gpio_air, False)
        finally:
            lgpio.gpiochip_close(self._chip)
            self._chip = None
            self._air_deadline = None
            self._pompe_deadline = None
            self._pompe_async_active = False

    def __enter__(self) -> "RelaysCritique":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise RelaysNotInitializedError("RelaysCritique not initialized. Call open() first.")
        return self._chip

    # -----------------
    # low-level
    # -----------------
    def _lvl_on(self) -> int:
        return 0 if self.config.active_low else 1

    def _lvl_off(self) -> int:
        return 1 if self.config.active_low else 0

    def _write(self, gpio: int, on: bool) -> None:
        chip = self._require_open()
        level = self._lvl_on() if on else self._lvl_off()
        lgpio.gpio_write(chip, gpio, level)

    # -----------------
    # public API (simple)
    # -----------------
    def set_air_on(self, time_s: Optional[float] = None) -> None:
        """
        Active le relais AIR.
        - time_s=None: ON indéfini jusqu'à set_air_off()
        - time_s>0: ON puis auto-OFF géré par tick()
        """
        self._write(self.config.gpio_air, True)
        if time_s is None:
            self._air_deadline = None
        else:
            if time_s <= 0:
                raise ValueError("time_s must be > 0 or None")
            self._air_deadline = time.monotonic() + float(time_s)

    def set_air_off(self) -> None:
        """Désactive AIR immédiatement."""
        self._write(self.config.gpio_air, False)
        self._air_deadline = None

    def set_pompe_off(self) -> None:
        """
        Impulsion bloquante 250 ms (simulateur bouton arrêt).
        Simple et robuste.
        """
        self._write(self.config.gpio_pompe_off, True)
        time.sleep(self.config.pompe_pulse_s)
        self._write(self.config.gpio_pompe_off, False)

    # -----------------
    # option non-bloquante (si besoin)
    # -----------------
    def set_pompe_off_async(self) -> None:
        """
        Lance une impulsion 250 ms sans sleep.
        Doit être finalisée via tick().
        """
        now = time.monotonic()
        self._write(self.config.gpio_pompe_off, True)
        self._pompe_deadline = now + self.config.pompe_pulse_s
        self._pompe_async_active = True

    def tick(self) -> None:
        """
        À appeler périodiquement dans la boucle principale.
        - coupe AIR si time_s expiré
        - termine l'impulsion pompe async si active
        """
        now = time.monotonic()

        if self._air_deadline is not None and now >= self._air_deadline:
            self.set_air_off()

        if self._pompe_async_active and self._pompe_deadline is not None and now >= self._pompe_deadline:
            self._write(self.config.gpio_pompe_off, False)
            self._pompe_deadline = None
            self._pompe_async_active = False