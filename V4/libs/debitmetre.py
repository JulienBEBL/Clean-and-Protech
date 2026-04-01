"""
debitmetre.py — Driver débitmètre à impulsions via lgpio.

Responsabilité : compter les impulsions du débitmètre par interrupt GPIO
et exposer débit instantané et volume cumulé.

Le chip lgpio est fourni par gpio_handle (singleton partagé).
Le callback d'interrupt tourne dans un thread lgpio interne (thread-safe).

Usage :
    import libs.gpio_handle as gpio_handle
    from libs.debitmetre import FlowMeter

    gpio_handle.init()
    fm = FlowMeter()
    fm.open()
    print(fm.flow_lpm())      # débit instantané L/min
    print(fm.total_liters())  # volume cumulé
    fm.close()
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque, Optional

import config
import libs.gpio_handle as gpio_handle

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio est requis. Installer python3-lgpio.") from e


# ============================================================
# Exceptions
# ============================================================

class FlowMeterError(Exception):
    """Erreur de base du driver débitmètre."""


class FlowMeterNotInitializedError(FlowMeterError):
    """Levée si open() n'a pas été appelé."""


# ============================================================
# Driver
# ============================================================

class FlowMeter:
    """
    Débitmètre à impulsions (comptage par front descendant).

    K-factor (impulsions/litre) et filtre anti-rebond configurés dans config.py.
    Thread-safe : le callback lgpio s'exécute dans un thread interne.
    """

    def __init__(
        self,
        gpio: int = config.DEBITMETRE_GPIO,
        pulses_per_liter: float = config.DEBITMETRE_K_FACTOR,
        filter_us: int = config.DEBITMETRE_DEBOUNCE_US,
    ) -> None:
        if pulses_per_liter <= 0:
            raise ValueError("pulses_per_liter doit être > 0")
        if filter_us < 0:
            raise ValueError("filter_us doit être >= 0")

        self.gpio = int(gpio)
        self.pulses_per_liter = float(pulses_per_liter)
        self.filter_us = int(filter_us)

        self._chip: Optional[int] = None
        self._cb = None  # objet callback lgpio

        self._lock = Lock()
        self._pulse_count_total: int = 0
        self._pulse_times: Deque[float] = deque()  # timestamps monotonic

    # ---- lifecycle ----

    def open(self) -> None:
        """
        Récupère le chip handle, configure l'interrupt sur front descendant
        et installe le callback de comptage.
        Idempotent.
        """
        if self._chip is not None:
            return
        try:
            chip = gpio_handle.get()
            lgpio.gpio_claim_alert(chip, self.gpio, lgpio.FALLING_EDGE)
            self._apply_filter(chip)
            self._cb = lgpio.callback(chip, self.gpio, lgpio.FALLING_EDGE, self._on_edge)
            self._chip = chip
        except Exception as e:
            self._cleanup()
            raise FlowMeterError(
                f"Impossible d'initialiser le débitmètre sur gpio={self.gpio}: {e}"
            ) from e

    def close(self) -> None:
        """Annule le callback et libère la pin. Ne ferme pas le chip handle."""
        if self._chip is None:
            return
        self._cleanup()

    def _cleanup(self) -> None:
        """Nettoyage interne (appelable même si partiellement initialisé)."""
        if self._cb is not None:
            try:
                self._cb.cancel()
            except Exception:
                pass
            self._cb = None
        if self._chip is not None:
            try:
                lgpio.gpio_free(self._chip, self.gpio)
            except Exception:
                pass
            self._chip = None

    def __enter__(self) -> "FlowMeter":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._chip is None:
            raise FlowMeterNotInitializedError(
                "FlowMeter non initialisé. Appeler open() d'abord."
            )

    # ---- filtre anti-rebond ----

    def _apply_filter(self, chip: int) -> None:
        """Applique le filtre anti-rebond si l'API lgpio le supporte."""
        if self.filter_us <= 0:
            return
        if hasattr(lgpio, "gpio_set_debounce"):
            lgpio.gpio_set_debounce(chip, self.gpio, self.filter_us)
        elif hasattr(lgpio, "gpio_set_glitch_filter"):
            lgpio.gpio_set_glitch_filter(chip, self.gpio, self.filter_us)
        # sinon : non supporté, pas d'erreur

    # ---- callback (thread interne lgpio) ----

    def _on_edge(self, chip: int, gpio: int, level: int, tick: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._pulse_count_total += 1
            self._pulse_times.append(now)
            # purge pour limiter la mémoire (fenêtre 2x)
            cutoff = now - 2.0
            while self._pulse_times and self._pulse_times[0] < cutoff:
                self._pulse_times.popleft()

    # ---- API publique ----

    def reset_total(self) -> None:
        """Remet à zéro le compteur total et l'historique."""
        with self._lock:
            self._pulse_count_total = 0
            self._pulse_times.clear()

    def total_pulses(self) -> int:
        """Retourne le nombre total d'impulsions depuis le dernier reset."""
        with self._lock:
            return int(self._pulse_count_total)

    def total_liters(self) -> float:
        """Retourne le volume cumulé en litres."""
        with self._lock:
            pulses = self._pulse_count_total
        return float(pulses) / self.pulses_per_liter

    def flow_lpm(self, window_s: float = 1.0) -> float:
        """
        Calcule le débit instantané en L/min sur la fenêtre glissante.

        Args:
            window_s : durée de la fenêtre (secondes, défaut=1.0)

        Returns:
            Débit en litres/minute.
        """
        self._require_open()
        if window_s <= 0:
            raise ValueError("window_s doit être > 0")

        now = time.monotonic()
        cutoff = now - window_s

        with self._lock:
            while self._pulse_times and self._pulse_times[0] < cutoff:
                self._pulse_times.popleft()
            pulses_in_window = len(self._pulse_times)

        liters_per_s = (float(pulses_in_window) / self.pulses_per_liter) / window_s
        return liters_per_s * 60.0
