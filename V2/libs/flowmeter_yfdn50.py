#!/usr/bin/env python3
# --------------------------------------
# flowmeter_yfdn50.py
# Débitmètre YF-DN50-S (Hall) sur Raspberry Pi via RPi.GPIO
#
# Objectifs:
#  - Comptage par interruptions (faible charge CPU)
#  - Mesure débit (L/min) + totalisateur (L)
#  - Thread interne pour calcul périodique (ne bloque pas le main)
#  - Paramètres ajustables: pulses_per_liter, edge, period, bouncetime
# --------------------------------------

import time
import threading
from dataclasses import dataclass

import RPi.GPIO as GPIO


@dataclass(frozen=True)
class FlowMeterConfig:
    gpio_bcm: int = 21
    pulses_per_liter: float = 12.0     # YF-DN50(-S) souvent: 12 pulses/L (f=0.2*Q)
    edge: int = GPIO.FALLING           # souvent FALLING si sortie NPN + pull-up externe
    sample_period_s: float = 1.0       # période de mise à jour débit
    bouncetime_ms: int = 2             # anti-rebond logiciel minimal
    gpio_pull: int = GPIO.PUD_OFF      # tu as déjà un pull-up externe


class FlowMeterYFDN50:
    def __init__(self, cfg: FlowMeterConfig = FlowMeterConfig(), gpio_mode=GPIO.BCM, warnings: bool = False):
        self.cfg = cfg
        self._gpio_mode = gpio_mode
        self._warnings = warnings

        self._lock = threading.RLock()
        self._running = False

        self._pulse_total = 0
        self._pulse_since = 0

        self._flow_l_min = 0.0
        self._last_update_t = time.monotonic()

        self._thread: threading.Thread | None = None

    # -----------------
    # Lifecycle
    # -----------------
    def start(self) -> None:
        """Initialise GPIO + démarre le calcul périodique."""
        with self._lock:
            if self._running:
                return

            GPIO.setwarnings(self._warnings)
            GPIO.setmode(self._gpio_mode)

            GPIO.setup(self.cfg.gpio_bcm, GPIO.IN, pull_up_down=self.cfg.gpio_pull)

            self._pulse_total = 0
            self._pulse_since = 0
            self._flow_l_min = 0.0
            self._last_update_t = time.monotonic()

            GPIO.add_event_detect(
                self.cfg.gpio_bcm,
                self.cfg.edge,
                callback=self._on_pulse,
                bouncetime=self.cfg.bouncetime_ms,
            )

            self._running = True
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stoppe le comptage et le thread. Ne fait pas GPIO.cleanup() global."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        # Retire l'interruption proprement (hors lock)
        try:
            GPIO.remove_event_detect(self.cfg.gpio_bcm)
        except Exception:
            pass

        th = self._thread
        if th is not None:
            th.join(timeout=1.0)

    def cleanup(self) -> None:
        """
        Optionnel: libère TOUT le module GPIO.
        À n'utiliser que si ton programme ne pilote plus rien d'autre.
        """
        self.stop()
        GPIO.cleanup()

    # -----------------
    # API lecture
    # -----------------
    def get_flow_l_min(self) -> float:
        """Dernière valeur débit (L/min), mise à jour périodiquement."""
        with self._lock:
            return float(self._flow_l_min)

    def get_total_liters(self) -> float:
        """Totalisateur (L)."""
        with self._lock:
            return self._pulse_total / self.cfg.pulses_per_liter

    def get_total_pulses(self) -> int:
        with self._lock:
            return int(self._pulse_total)

    def reset_total(self) -> None:
        with self._lock:
            self._pulse_total = 0
            self._pulse_since = 0
            self._flow_l_min = 0.0
            self._last_update_t = time.monotonic()

    # -----------------
    # Internals
    # -----------------
    def _on_pulse(self, _channel: int) -> None:
        # Callback d'interruption -> doit être très court
        with self._lock:
            self._pulse_total += 1
            self._pulse_since += 1

    def _worker(self) -> None:
        # Thread périodique: calcule flow à partir des pulses sur une fenêtre sample_period_s
        while True:
            with self._lock:
                if not self._running:
                    return
                period = float(self.cfg.sample_period_s)

            time.sleep(period)

            now = time.monotonic()
            with self._lock:
                dt = now - self._last_update_t
                pulses = self._pulse_since
                self._pulse_since = 0
                self._last_update_t = now

                if dt <= 0 or self.cfg.pulses_per_liter <= 0:
                    self._flow_l_min = 0.0
                else:
                    liters = pulses / self.cfg.pulses_per_liter
                    l_per_s = liters / dt
                    self._flow_l_min = l_per_s * 60.0
