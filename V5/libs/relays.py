"""
relays.py — Driver relais (POMPE, AIR, PURGE et 4 vannes US Solid) — V5.

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

Relais PURGE (GPIO 23, relais V5) :
    Pilote l'EV de purge d'air de la pompe (230V, normalement fermée, contact NO).
    GPIO HIGH → EV alimentée → purge ouverte.
    Ouverte automatiquement à chaque mise en marche de la pompe
    (set_pompe_on, transition OFF → ON), refermée après config.PURGE_TIME_S
    par une minuterie (threading.Timer) indépendante de la boucle principale.
    set_pompe_off() referme la purge immédiatement si elle est encore ouverte.

    Pourquoi une minuterie et pas tick() : la boucle principale est souvent
    bloquée (bip long 2,5 s après start(), relance pompe PRG5 de 10 s par
    phase). Une fermeture pilotée par tick() tomberait en retard.
    La minuterie n'écrit QUE la broche PURGE, sous verrou, et ne touche
    jamais au bus I2C. tick() sert de filet de sécurité si elle échouait.

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
    relays.set_purge_on(time_s=5.0)          # PURGE ouverte 5s (non-bloquant, test)

    # dans la boucle principale (timer AIR + filet de sécurité PURGE) :
    relays.tick()

    relays.close()
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional

import config
import libs.gpio_handle as gpio_handle
from logger import log

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

# Toutes les GPIO gérées par ce driver (ordre de claim/free).
# PURGE est toujours claimée et forcée LOW, même si PURGE_ENABLED = False.
_ALL_GPIO: list[int] = [
    config.RELAY_POMPE_GPIO,
    config.RELAY_AIR_GPIO,
    config.RELAY_PURGE_GPIO,
    *_VALVE_GPIO.values(),
]

# Filet de sécurité PURGE : si la minuterie n'a pas refermé l'EV
# _PURGE_BACKUP_MARGIN_S après l'échéance, tick() la referme.
_PURGE_BACKUP_MARGIN_S: float = 1.0


# ============================================================
# Driver
# ============================================================

class Relays:
    """
    Pilotage des relais GPIO : POMPE, AIR, PURGE et 4 vannes US Solid.

    Tous les relais sont actifs haut (GPIO HIGH = ON).
    État par défaut = OFF (GPIO LOW) au démarrage et à la fermeture.
    """

    def __init__(
        self,
        gpio_pompe: int = config.RELAY_POMPE_GPIO,
        gpio_air:   int = config.RELAY_AIR_GPIO,
        gpio_purge: int = config.RELAY_PURGE_GPIO,
    ) -> None:
        self.gpio_pompe = int(gpio_pompe)
        self.gpio_air   = int(gpio_air)
        self.gpio_purge = int(gpio_purge)

        self._chip: Optional[int] = None
        self._air_deadline: Optional[float] = None

        # État logiciel de la pompe — sert à détecter la transition OFF → ON
        # qui déclenche la purge (ne dépend pas d'une relecture GPIO).
        self._pompe_on: bool = False

        # --- PURGE ---
        # Le verrou protège tout l'état purge ET chaque écriture de la broche
        # PURGE : la minuterie tourne dans un autre thread. Il n'est jamais
        # tenu pendant une attente — seulement le temps d'un gpio_write.
        self._purge_lock = threading.Lock()
        self._purge_timer: Optional[threading.Timer] = None
        self._purge_deadline: Optional[float] = None
        self._purge_open: bool = False
        # Numéro d'ouverture : une minuterie périmée (purge refermée ou
        # rouverte entre-temps) le compare et ne fait alors rien.
        self._purge_gen: int = 0

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
            self._pompe_on = False
            with self._purge_lock:
                self._reset_purge_state_locked()
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
        # Neutralise la minuterie PURGE avant de toucher aux broches :
        # elle ne pourra plus écrire, même si elle se déclenche maintenant.
        with self._purge_lock:
            self._reset_purge_state_locked()
        self._pompe_on = False
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
        """
        Active la pompe (GPIO HIGH → relais ON → variateur ON).

        Si la pompe était à l'arrêt, ouvre la purge en même temps pour
        PURGE_TIME_S (non bloquant). Un défaut de purge n'empêche jamais
        la pompe de démarrer : il est seulement journalisé.
        """
        was_on = self._pompe_on
        self._write_gpio(self.gpio_pompe, True)
        self._pompe_on = True
        if not was_on:
            self._start_pump_purge()

    def set_pompe_off(self) -> None:
        """
        Coupe la pompe (GPIO LOW → relais OFF → variateur OFF).
        Referme la purge immédiatement si elle est encore ouverte.
        """
        try:
            self._write_gpio(self.gpio_pompe, False)
            self._pompe_on = False
        finally:
            self.set_purge_off(reason="pompe arrêtée")

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

    # ---- PURGE ----

    def _start_pump_purge(self) -> None:
        """Ouvre la purge au démarrage pompe, selon config. Ne lève jamais."""
        if not config.PURGE_ENABLED:
            return
        if config.PURGE_TIME_S <= 0:
            log.warning(f"Purge — PURGE_TIME_S={config.PURGE_TIME_S} invalide, purge ignorée")
            return
        try:
            self.set_purge_on(time_s=config.PURGE_TIME_S)
            log.info(f"Purge — EV ouverte ({config.PURGE_TIME_S:g}s) au démarrage pompe")
        except Exception as e:
            log.error(f"Purge — échec ouverture EV : {e} (pompe maintenue en marche)")

    def set_purge_on(self, time_s: Optional[float] = None) -> None:
        """
        Ouvre l'EV purge (GPIO HIGH).

        Args:
            time_s : durée en secondes puis fermeture automatique par une
                     minuterie indépendante de la boucle principale.
                     None = ouverte jusqu'à set_purge_off() (tests uniquement).

        Une ouverture pendant une purge en cours repart de zéro (nouvelle durée).
        """
        if time_s is not None and time_s <= 0:
            raise ValueError("time_s doit être > 0 ou None")
        chip = self._require_open()
        with self._purge_lock:
            self._reset_purge_state_locked()       # annule une minuterie en cours
            lgpio.gpio_write(chip, self.gpio_purge, 1)
            self._purge_open = True
            if time_s is None:
                return
            self._purge_deadline = time.monotonic() + float(time_s)
            timer = threading.Timer(
                float(time_s), self._purge_timer_expired, args=(self._purge_gen,)
            )
            timer.daemon = True                    # ne retient jamais l'arrêt du process
            timer.name = "purge-timer"
            try:
                timer.start()
            except Exception:
                # Minuterie impossible : on ne laisse pas la purge ouverte
                lgpio.gpio_write(chip, self.gpio_purge, 0)
                self._purge_open = False
                self._purge_deadline = None
                raise
            self._purge_timer = timer

    def set_purge_off(self, reason: str = "commande") -> None:
        """Ferme l'EV purge immédiatement (GPIO LOW) et annule la minuterie."""
        chip = self._require_open()
        with self._purge_lock:
            was_open = self._purge_open
            # Écriture AVANT la remise à zéro : si elle échoue, la purge reste
            # marquée ouverte et le filet de sécurité de tick() retentera.
            lgpio.gpio_write(chip, self.gpio_purge, 0)
            self._reset_purge_state_locked()
        if was_open:
            log.info(f"Purge — EV fermée ({reason})")

    @property
    def purge_is_on(self) -> bool:
        """True si la purge est actuellement commandée ouverte."""
        return self._purge_open

    def _reset_purge_state_locked(self) -> None:
        """
        Annule la minuterie et oublie l'ouverture en cours. N'écrit pas la broche.
        Appelant : doit tenir self._purge_lock.
        """
        if self._purge_timer is not None:
            self._purge_timer.cancel()             # sans attente, même depuis la minuterie
            self._purge_timer = None
        self._purge_gen += 1                       # périme toute minuterie déjà lancée
        self._purge_deadline = None
        self._purge_open = False

    def _purge_timer_expired(self, gen: int) -> None:
        """Exécutée dans le thread de la minuterie : referme la purge à l'échéance."""
        try:
            with self._purge_lock:
                if gen != self._purge_gen or self._chip is None:
                    return                         # purge déjà refermée / rouverte
                lgpio.gpio_write(self._chip, self.gpio_purge, 0)
                self._purge_timer = None
                self._purge_gen += 1
                self._purge_deadline = None
                self._purge_open = False
            log.info("Purge — EV fermée (fin temporisation)")
        except Exception as e:
            # La purge reste marquée ouverte : tick() retentera la fermeture
            log.error(f"Purge — échec fermeture par minuterie : {e}")

    def tick(self) -> None:
        """
        À appeler périodiquement dans la boucle principale.
        Gère l'auto-extinction du relais AIR si set_air_on(time_s=...) a été utilisé.
        Filet de sécurité PURGE : referme l'EV si la minuterie a échoué.
        """
        if self._air_deadline is not None and time.monotonic() >= self._air_deadline:
            self.set_air_off()

        deadline = self._purge_deadline
        if deadline is not None and time.monotonic() >= deadline + _PURGE_BACKUP_MARGIN_S:
            log.warning("Purge — minuterie en retard, fermeture par tick()")
            self.set_purge_off(reason="filet de sécurité")

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
