"""
led_blinker.py — Animation des LEDs programme (Clean & Protech V5).

Responsabilité : piloter l'état visuel de la LED associée au programme courant,
selon la convention machine :

    IDLE                          → toutes les LEDs éteintes
    Transitions (CONFIRM, écran   → LED du programme CLIGNOTANTE
      avant-programme, démarrage,
      arrêt)
    RUNNING                       → LED du programme ALLUMÉE FIXE
    Sécurité / défaut             → LED CLIGNOTANTE

Une seule LED est pilotée à la fois : celle du programme concerné.

--- Pourquoi cette classe existe ---

La quasi-totalité des phases « entre IDLE et RUNNING » est BLOQUANTE :
manœuvre des vannes (15-16 s chacune), mini-homing VIC (~15 s), écran
avant-programme (10 s), relance pompe (jusqu'à 30 s), écran d'arrêt (10 s).
Pendant ces phases la boucle principale ne tourne pas.

Une LED pilotée uniquement depuis la boucle resterait donc figée pendant
l'essentiel du démarrage. Deux mécanismes permettent de l'animer quand même,
SANS introduire de thread (pas de concurrence I2C sur un automate) :

    1. sleep()  — attente découpée qui anime la LED, remplace time.sleep()
                  dans les phases bloquantes.
    2. tick()   — appelable depuis n'importe quelle boucle interne, notamment
                  via VICController.set_step_callback() pour couvrir les
                  déplacements moteur.

Usage :
    leds = LedBlinker(io)
    leds.attach(prg.led_index)      # sélectionne la LED du programme
    leds.blink(time.monotonic())    # phase de transition
    ...
    leds.tick(time.monotonic())     # à chaque itération de boucle
    leds.sleep(16.0)                # attente bloquante animée
    leds.fixed()                    # passage en RUNNING
    leds.off()                      # retour IDLE
"""

from __future__ import annotations

import time
from typing import Optional, TYPE_CHECKING

import config

if TYPE_CHECKING:
    from libs.io_board import IOBoard


# Granularité de découpage de sleep() — compromis entre précision du front
# de clignotement et nombre d'itérations.
_SLEEP_SLICE_S: float = 0.05


class LedBlinker:
    """
    Pilote la LED du programme courant : éteinte, fixe ou clignotante.

    Les erreurs I2C sont absorbées : une LED est un organe d'affichage, son
    échec ne doit jamais interrompre un programme machine en cours.
    """

    def __init__(self, io: "IOBoard", period_s: float = config.LED_BLINK_PERIOD_S) -> None:
        self._io      = io
        self._period  = float(period_s)
        self._index   = 0          # 0 = aucune LED pilotée
        self._mode    = "off"      # 'off' | 'fixed' | 'blink'
        self._is_on   = False
        self._deadline = 0.0

    # ---- écriture bas niveau ----

    def _write(self, on: bool) -> None:
        """Écrit l'état de la LED pilotée. Absorbe les erreurs I2C."""
        self._is_on = on
        if not self._index:
            return
        try:
            self._io.set_led(self._index, 1 if on else 0)
        except Exception:
            pass

    # ---- API publique ----

    def attach(self, led_index: int) -> None:
        """
        Sélectionne la LED à piloter (index 1..6, celle du programme courant).
        Éteint la LED précédente si elle était différente.
        """
        idx = int(led_index)
        if self._index and self._index != idx:
            self.off()
        self._index = idx

    def off(self) -> None:
        """Éteint la LED pilotée et arrête l'animation. Idempotente."""
        self._write(False)
        self._index = 0
        self._mode  = "off"

    def fixed(self) -> None:
        """Allumage fixe — état RUNNING."""
        self._mode = "fixed"
        self._write(True)

    def blink(self, now: Optional[float] = None) -> None:
        """
        Démarre le clignotement — transitions et sécurité.
        Commence par la phase allumée.
        """
        if now is None:
            now = time.monotonic()
        self._mode     = "blink"
        self._deadline = now + self._period
        self._write(True)

    def tick(self, now: Optional[float] = None) -> None:
        """
        Fait avancer le clignotement. No-op si le mode n'est pas 'blink'.
        À appeler depuis la boucle principale ET depuis toute boucle interne
        d'une phase bloquante.
        """
        if self._mode != "blink":
            return
        if now is None:
            now = time.monotonic()
        if now < self._deadline:
            return
        self._write(not self._is_on)
        self._deadline = now + self._period

    def sleep(self, duration_s: float) -> None:
        """
        Attente bloquante qui continue d'animer la LED.
        Remplace time.sleep() dans les phases bloquantes.
        """
        if duration_s <= 0:
            return
        end = time.monotonic() + duration_s
        while True:
            now = time.monotonic()
            if now >= end:
                return
            self.tick(now)
            time.sleep(min(_SLEEP_SLICE_S, end - now))

    # ---- introspection (tests / diagnostic) ----

    @property
    def mode(self) -> str:
        """'off', 'fixed' ou 'blink'."""
        return self._mode

    @property
    def led_index(self) -> int:
        """Index de la LED pilotée, 0 si aucune."""
        return self._index

    @property
    def is_on(self) -> bool:
        """État courant de la LED pilotée."""
        return self._is_on
