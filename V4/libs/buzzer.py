"""
buzzer.py — Driver buzzer passif piézo via lgpio PWM.

Responsabilité : piloter le buzzer (fréquence, duty, séquences).
Le chip lgpio est fourni par gpio_handle (singleton partagé).

Usage :
    import libs.gpio_handle as gpio_handle
    from libs.buzzer import Buzzer

    gpio_handle.init()
    bz = Buzzer()
    bz.open()
    bz.beep(time_ms=100, power_pct=70, repeat=3)
    bz.ringtone_startup()
    bz.close()
"""

from __future__ import annotations

import time
from typing import Optional, Sequence, Tuple

import config
import libs.gpio_handle as gpio_handle

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio est requis. Installer python3-lgpio.") from e


# ============================================================
# Exceptions
# ============================================================

class BuzzerError(Exception):
    """Erreur de base du driver buzzer."""


class BuzzerNotInitializedError(BuzzerError):
    """Levée si open() n'a pas été appelé."""


# ============================================================
# Driver
# ============================================================

class Buzzer:
    """
    Buzzer passif piloté par PWM (lgpio.tx_pwm).

    La fréquence et le duty cycle sont les deux paramètres
    de contrôle (puissance sonore ≈ duty, hauteur ≈ fréquence).
    """

    def __init__(self, gpio: int = config.BUZZER_GPIO) -> None:
        self.gpio = int(gpio)
        self._chip: Optional[int] = None

    # ---- lifecycle ----

    def open(self) -> None:
        """
        Récupère le chip handle et claim la pin buzzer en sortie.
        Idempotent.
        """
        if self._chip is not None:
            return
        try:
            chip = gpio_handle.get()
            lgpio.gpio_claim_output(chip, self.gpio, 0)
            self._chip = chip
            self._apply_pwm(config.BUZZER_DEFAULT_FREQ_HZ, 0)  # silencieux
        except Exception as e:
            self._chip = None
            raise BuzzerError(
                f"Impossible d'initialiser le buzzer sur gpio={self.gpio}: {e}"
            ) from e

    def close(self) -> None:
        """Coupe le son, libère la pin. Ne ferme pas le chip handle."""
        if self._chip is None:
            return
        try:
            self.off()
        except Exception:
            pass
        try:
            lgpio.gpio_free(self._chip, self.gpio)
        except Exception:
            pass
        finally:
            self._chip = None

    def __enter__(self) -> "Buzzer":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise BuzzerNotInitializedError(
                "Buzzer non initialisé. Appeler open() d'abord."
            )
        return self._chip

    # ---- bas-niveau ----

    def _apply_pwm(self, freq_hz: int, duty_pct: int) -> None:
        chip = self._require_open()
        f = max(config.BUZZER_FREQ_MIN_HZ, min(config.BUZZER_FREQ_MAX_HZ, int(freq_hz)))
        d = max(0, min(100, int(duty_pct)))
        try:
            lgpio.tx_pwm(chip, self.gpio, f, d)
        except Exception as e:
            raise BuzzerError(
                f"tx_pwm échoué (gpio={self.gpio}, freq={f}Hz, duty={d}%): {e}"
            ) from e

    # ---- API publique ----

    def on(self, freq_hz: int = config.BUZZER_DEFAULT_FREQ_HZ, power_pct: int = 80) -> None:
        """Active le buzzer en continu."""
        self._apply_pwm(freq_hz, power_pct)

    def off(self) -> None:
        """Coupe le buzzer (duty=0)."""
        self._apply_pwm(config.BUZZER_DEFAULT_FREQ_HZ, 0)

    def beep(
        self,
        time_ms: int = config.BUZZER_BEEP_TIME_MS,
        power_pct: int = config.BUZZER_BEEP_POWER_PCT,
        repeat: int = config.BUZZER_BEEP_REPEAT,
        freq_hz: int = config.BUZZER_DEFAULT_FREQ_HZ,
        gap_ms: int = config.BUZZER_BEEP_GAP_MS,
    ) -> None:
        """
        Émet un ou plusieurs bips.

        Args:
            time_ms   : durée ON de chaque bip (ms)
            power_pct : duty cycle (0..100)
            repeat    : nombre de répétitions
            freq_hz   : fréquence (Hz)
            gap_ms    : pause OFF entre bips (ms)
        """
        self._require_open()
        t_ms = max(1, min(10_000, int(time_ms)))
        r    = max(1, min(100, int(repeat)))
        gap  = max(0, min(10_000, int(gap_ms)))

        for i in range(r):
            self._apply_pwm(freq_hz, power_pct)
            time.sleep(t_ms / 1000.0)
            self.off()
            if gap > 0 and i < r - 1:
                time.sleep(gap / 1000.0)

    def play(self, sequence: Sequence[Tuple[int, int, int, int]]) -> None:
        """
        Joue une séquence de notes.

        Chaque élément : (freq_hz, time_ms, power_pct, gap_ms)

        Exemple :
            bz.play([(2000, 80, 70, 40), (2500, 80, 70, 80)])
        """
        self._require_open()
        for freq_hz, time_ms, power_pct, gap_ms in sequence:
            self._apply_pwm(int(freq_hz), int(power_pct))
            time.sleep(max(1, int(time_ms)) / 1000.0)
            self.off()
            if int(gap_ms) > 0:
                time.sleep(int(gap_ms) / 1000.0)

    def ringtone_startup(self) -> None:
        """Sonnerie de démarrage (~5 secondes, montée progressive)."""
        self.play([
            (1500, 500, 60, 120),
            (1650, 500, 60, 120),
            (1800, 500, 65, 150),
            (1700, 400, 55, 200),
            (1850, 600, 70, 120),
            (2050, 600, 75, 200),
            (1900, 900, 55,   0),
        ])
