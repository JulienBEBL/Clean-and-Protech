"""
relays.py — Driver relais (POMPE, AIR et 4 vannes US Solid) — V5.

Responsabilité : piloter les relais GPIO de la machine.

Tous les relais sont câblés en actif haut :
    GPIO HIGH → relais ON
    GPIO LOW  → relais OFF (état sûr)

Relais POMPE (GPIO 19) :
    Pilote le câble de commande ON du variateur de vitesse.
    GPIO HIGH → relais ON → commande ON variateur active → pompe tourne.
    GPIO LOW  → relais OFF → commande ON variateur inactive → pompe à l'arrêt.
    NOTE : câblage sujet à évolution selon comportement terrain du variateur.
    DIFFÉRENCE V4→V5 : en V4, la logique était inversée (relais commandait
    le câble "OFF" du variateur). En V5, le relais commande directement le
    câble "ON" — GPIO HIGH = pompe ON (comportement intuitif).

Relais AIR (GPIO 26) :
    Pilote l'électrovanne d'injection d'air (contact NO).
    GPIO HIGH → EV ouverte → injection ON.

Vannes US Solid (GPIO 7, 8, 25, 24) :
    Vannes 24VDC à contact NO, actives haute.
    GPIO HIGH → relais ON → contact NO fermé → vanne ouverte.

Le chip lgpio est fourni par gpio_handle (singleton partagé).
La méthode tick() doit être appelée dans la boucle principale
si set_air_on(time_s=...) est utilisé.

Usage :
    import libs.gpio_handle as gpio_handle
    from libs.relays import Relays

    gpio_handle.init()
    relays = Relays()
    relays.open()

    relays.set_pompe_on()                    # POMPE ON
    relays.set_pompe_off()                   # POMPE OFF
    relays.set_valve("POT_A_BOUE", True)     # vanne POT_A_BOUE ouverte
    relays.set_valve("EGOUTS", False)        # vanne EGOUTS fermée
    relays.set_air_on(time_s=5.0)            # AIR ON pendant 5s (non-bloquant)

    # dans la boucle principale (uniquement si timer AIR utilisé) :
    relays.tick()

    relays.close()
"""

from __future__ import annotations

import time
from typing import Dict, Optional

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
# Mapping GPIO des vannes US Solid
# ============================================================

_VALVE_GPIO: Dict[str, int] = {
    "POT_A_BOUE":  config.RELAY_POT_A_BOUE_GPIO,
    "EGOUTS":      config.RELAY_EGOUTS_GPIO,
    "CUVE_TRAVAIL": config.RELAY_CUVE_TRAVAIL_GPIO,
    "EAU_PROPRE":  config.RELAY_EAU_PROPRE_GPIO,
}

# Toutes les GPIO gérées par ce driver (ordre de claim/free)
_ALL_GPIO: list[int] = [
    config.RELAY_POMPE_GPIO,
    config.RELAY_AIR_GPIO,
    *_VALVE_GPIO.values(),
]


# ============================================================
# Driver
# ============================================================

class Relays:
    """
    Pilotage des relais GPIO : POMPE, AIR, et 4 vannes US Solid.

    Tous les relais sont actifs haut (GPIO HIGH = ON).
    État par défaut = OFF (GPIO LOW) au démarrage et à la fermeture.
    """

    def __init__(
        self,
        gpio_pompe: int = config.RELAY_POMPE_GPIO,
        gpio_air:   int = config.RELAY_AIR_GPIO,
    ) -> None:
        self.gpio_pompe = int(gpio_pompe)
        self.gpio_air   = int(gpio_air)

        self._chip: Optional[int] = None
        self._air_deadline: Optional[float] = None

    # ---- lifecycle ----

    def open(self) -> None:
        """
        Récupère le chip handle, claim toutes les pins relais en sortie
        et force l'état OFF (GPIO LOW) sur chacune.
        Idempotent.
        """
        if self._chip is not None:
            return
        try:
            chip = gpio_handle.get()
            for gpio in _ALL_GPIO:
                lgpio.gpio_claim_output(chip, gpio, 0)  # LOW = OFF
            self._chip = chip
            self._air_deadline = None
            # État sûr explicite
            for gpio in _ALL_GPIO:
                lgpio.gpio_write(chip, gpio, 0)
        except Exception as e:
            self._chip = None
            raise RelaysError(f"Impossible d'initialiser les relais: {e}") from e

    def close(self) -> None:
        """Coupe tous les relais, libère les pins. Ne ferme pas le chip handle."""
        if self._chip is None:
            return
        try:
            for gpio in _ALL_GPIO:
                lgpio.gpio_write(self._chip, gpio, 0)
        except Exception:
            pass
        try:
            for gpio in _ALL_GPIO:
                lgpio.gpio_free(self._chip, gpio)
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

    def _write_gpio(self, gpio: int, on: bool) -> None:
        chip = self._require_open()
        lgpio.gpio_write(chip, gpio, 1 if on else 0)

    # ---- POMPE ----

    def set_pompe_on(self) -> None:
        """Active la pompe (GPIO HIGH → relais ON → variateur ON)."""
        self._write_gpio(self.gpio_pompe, True)

    def set_pompe_off(self) -> None:
        """Coupe la pompe (GPIO LOW → relais OFF → variateur OFF)."""
        self._write_gpio(self.gpio_pompe, False)

    @property
    def pompe_is_on(self) -> bool:
        """True si le relais POMPE est actuellement actif."""
        if self._chip is None:
            return False
        try:
            return lgpio.gpio_read(self._chip, self.gpio_pompe) == 1
        except Exception:
            return False

    # ---- AIR ----

    def set_air_on(self, time_s: Optional[float] = None) -> None:
        """
        Active le relais AIR (EV ouverte).

        Args:
            time_s : durée en secondes puis auto-OFF via tick().
                     None = ON indéfini jusqu'à set_air_off().
        """
        self._write_gpio(self.gpio_air, True)
        if time_s is None:
            self._air_deadline = None
        else:
            if time_s <= 0:
                raise ValueError("time_s doit être > 0 ou None")
            self._air_deadline = time.monotonic() + float(time_s)

    def set_air_off(self) -> None:
        """Désactive le relais AIR immédiatement (EV fermée)."""
        self._write_gpio(self.gpio_air, False)
        self._air_deadline = None

    @property
    def air_is_on(self) -> bool:
        """True si le relais AIR est actuellement actif."""
        if self._chip is None:
            return False
        try:
            return lgpio.gpio_read(self._chip, self.gpio_air) == 1
        except Exception:
            return False

    def tick(self) -> None:
        """
        À appeler périodiquement dans la boucle principale.
        Gère l'auto-extinction du relais AIR si set_air_on(time_s=...) a été utilisé.
        """
        if self._air_deadline is not None and time.monotonic() >= self._air_deadline:
            self.set_air_off()

    # ---- Vannes US Solid ----

    def set_valve(self, name: str, on: bool) -> None:
        """
        Commande une vanne US Solid par nom.

        Args:
            name : 'POT_A_BOUE', 'EGOUTS', 'CUVE_TRAVAIL' ou 'EAU_PROPRE'
            on   : True = ouverte (GPIO HIGH), False = fermée (GPIO LOW)
        """
        gpio = _VALVE_GPIO.get(name)
        if gpio is None:
            raise ValueError(
                f"Vanne inconnue : '{name}'. "
                f"Noms valides : {list(_VALVE_GPIO.keys())}"
            )
        self._write_gpio(gpio, on)

    def open_valve(self, name: str) -> None:
        """Ouvre une vanne US Solid (raccourci)."""
        self.set_valve(name, True)

    def close_valve(self, name: str) -> None:
        """Ferme une vanne US Solid (raccourci)."""
        self.set_valve(name, False)

    def open_all_valves(self) -> None:
        """Ouvre toutes les vannes US Solid (charge initiale condensateurs)."""
        for name in _VALVE_GPIO:
            self.set_valve(name, True)

    def close_all_valves(self) -> None:
        """Ferme toutes les vannes US Solid (état sûr)."""
        for name in _VALVE_GPIO:
            self.set_valve(name, False)

    def valve_is_open(self, name: str) -> bool:
        """True si la vanne est actuellement ouverte (relais ON)."""
        gpio = _VALVE_GPIO.get(name)
        if gpio is None or self._chip is None:
            return False
        try:
            return lgpio.gpio_read(self._chip, gpio) == 1
        except Exception:
            return False
