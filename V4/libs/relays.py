"""
relays.py — Driver relais critiques (POMPE et AIR).

Responsabilité : piloter les deux relais de sécurité.
Les deux relais ont un comportement identique : ON ou OFF simple.
Le relais AIR supporte en plus un timer d'auto-extinction via tick().

Le chip lgpio est fourni par gpio_handle (singleton partagé).
La méthode tick() doit être appelée dans la boucle principale
uniquement si set_air_on(time_s=...) est utilisé.

Usage :
    import libs.gpio_handle as gpio_handle
    from libs.relays import Relays

    gpio_handle.init()
    relays = Relays()
    relays.open()

    relays.set_pompe_on()             # POMPE ON
    relays.set_pompe_off()            # POMPE OFF
    relays.set_air_on(time_s=5.0)    # AIR ON pendant 5s (non-bloquant)

    # dans la boucle principale (uniquement si timer AIR utilisé) :
    relays.tick()

    relays.close()
"""

from __future__ import annotations

import time
from typing import Optional

import config
import libs.gpio_handle as gpio_handle

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio est requis. Installer python3-lgpio.") from e


# ============================================================
# Exceptions
# ============================================================

class RelaysError(Exception):
    """Erreur de base du driver relais."""


class RelaysNotInitializedError(RelaysError):
    """Levée si open() n'a pas été appelé."""


# ============================================================
# Driver
# ============================================================

class Relays:
    """
    Relais critiques : POMPE (GPIO 16) et AIR (GPIO 20).

    Les deux relais ont un comportement ON/OFF simple.
    Le relais AIR supporte en plus un timer d'auto-extinction.

    Relais actifs haut (ACTIVE_LOW = False).
    État par défaut = OFF au démarrage et à la fermeture.
    """

    # Niveau logique (câblage actif haut par défaut)
    _ACTIVE_LOW: bool = False

    def __init__(
        self,
        gpio_pompe: int = config.RELAY_POMPE_OFF_GPIO,
        gpio_air: int = config.RELAY_AIR_GPIO,
    ) -> None:
        self.gpio_pompe = int(gpio_pompe)
        self.gpio_air = int(gpio_air)

        self._chip: Optional[int] = None
        self._air_deadline: Optional[float] = None

    # ---- lifecycle ----

    def open(self) -> None:
        """
        Récupère le chip handle, claim les deux pins relais en sortie
        et force l'état OFF.
        Idempotent.
        """
        if self._chip is not None:
            return
        try:
            chip = gpio_handle.get()
            lgpio.gpio_claim_output(chip, self.gpio_pompe, self._lvl_off())
            lgpio.gpio_claim_output(chip, self.gpio_air, self._lvl_off())
            self._chip = chip
            self._air_deadline = None
            # état sûr explicite
            self._write(self.gpio_pompe, False)
            self._write(self.gpio_air, False)
        except Exception as e:
            self._chip = None
            raise RelaysError(
                f"Impossible d'initialiser les relais: {e}"
            ) from e

    def close(self) -> None:
        """Coupe les deux relais, libère les pins. Ne ferme pas le chip handle."""
        if self._chip is None:
            return
        try:
            self._write(self.gpio_pompe, False)
            self._write(self.gpio_air, False)
        except Exception:
            pass
        try:
            lgpio.gpio_free(self._chip, self.gpio_pompe)
            lgpio.gpio_free(self._chip, self.gpio_air)
        except Exception:
            pass
        finally:
            self._chip = None
            self._air_deadline = None

    def __enter__(self) -> "Relays":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise RelaysNotInitializedError(
                "Relays non initialisé. Appeler open() d'abord."
            )
        return self._chip

    # ---- bas-niveau ----

    def _lvl_on(self) -> int:
        return 0 if self._ACTIVE_LOW else 1

    def _lvl_off(self) -> int:
        return 1 if self._ACTIVE_LOW else 0

    def _write(self, gpio: int, on: bool) -> None:
        chip = self._require_open()
        lgpio.gpio_write(chip, gpio, self._lvl_on() if on else self._lvl_off())

    # ---- API publique ----

    def set_air_on(self, time_s: Optional[float] = None) -> None:
        """
        Active le relais AIR.

        Args:
            time_s : durée en secondes puis auto-OFF via tick().
                     None = ON indéfini jusqu'à set_air_off().
        """
        self._write(self.gpio_air, True)
        if time_s is None:
            self._air_deadline = None
        else:
            if time_s <= 0:
                raise ValueError("time_s doit être > 0 ou None")
            self._air_deadline = time.monotonic() + float(time_s)

    def set_air_off(self) -> None:
        """Désactive le relais AIR immédiatement."""
        self._write(self.gpio_air, False)
        self._air_deadline = None

    def set_pompe_on(self) -> None:
        """Active le relais POMPE."""
        self._write(self.gpio_pompe, True)

    def set_pompe_off(self) -> None:
        """Désactive le relais POMPE."""
        self._write(self.gpio_pompe, False)

    def tick(self) -> None:
        """
        À appeler périodiquement dans la boucle principale.
        Gère l'auto-extinction du relais AIR si set_air_on(time_s=...) a été utilisé.
        """
        if self._air_deadline is not None and time.monotonic() >= self._air_deadline:
            self.set_air_off()

    # ---- état ----

    @property
    def pompe_is_on(self) -> bool:
        """True si le relais POMPE est actuellement actif."""
        if self._chip is None:
            return False
        try:
            return lgpio.gpio_read(self._chip, self.gpio_pompe) == self._lvl_on()
        except Exception:
            return False

    @property
    def air_is_on(self) -> bool:
        """True si le relais AIR est actuellement actif."""
        if self._chip is None:
            return False
        try:
            return lgpio.gpio_read(self._chip, self.gpio_air) == self._lvl_on()
        except Exception:
            return False
