"""
vic.py — Contrôleur VIC (Vanne d'Injection et de Circuit) — V5.

Driver dédié à la VIC, motorisée par un driver JK-DM860H.
En V5, les signaux STEP/DIR/ENA sont câblés directement sur GPIO RPi 5
(plus de MCP3 intermédiaire comme en V4).

Positions de la VIC :
    DEPART  =   0 pas  (butée fermeture)
    NEUTRE  =  50 pas  (position milieu)
    RETOUR  = 100 pas  (butée ouverture)

Sens de déplacement (config.py) :
    fermeture → GPIO DIR = VIC_DIR_FERMETURE (0) → vers DEPART
    ouverture → GPIO DIR = VIC_DIR_OUVERTURE (1) → vers RETOUR

ENA actif bas (DM860H) :
    VIC_ENA_ACTIVE_LEVEL   = 0 → driver actif
    VIC_ENA_INACTIVE_LEVEL = 1 → driver désactivé (état sûr)

Usage :
    import libs.gpio_handle as gpio_handle
    from libs.vic import VICController

    gpio_handle.init()
    vic = VICController()
    vic.open()
    vic.homing()           # ancrage + positionnement NEUTRE
    vic.move_to(0)         # déplace vers DEPART
    vic.move_to(50)        # déplace vers NEUTRE
    vic.close()
"""

from __future__ import annotations

import time
from typing import Optional

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

class VICError(Exception):
    """Erreur de base du contrôleur VIC."""


class VICNotInitializedError(VICError):
    """Levée si open() n'a pas été appelé."""


# ============================================================
# Contrôleur VIC
# ============================================================

class VICController:
    """
    Contrôleur moteur pas-à-pas pour la VIC — GPIO direct RPi 5.

    Toutes les constantes hardware viennent de config.py.
    Un seul VICController est instancié par application.
    """

    def __init__(
        self,
        gpio_step: int = config.VIC_STEP_GPIO,
        gpio_dir:  int = config.VIC_DIR_GPIO,
        gpio_ena:  int = config.VIC_ENA_GPIO,
    ) -> None:
        self.gpio_step = int(gpio_step)
        self.gpio_dir  = int(gpio_dir)
        self.gpio_ena  = int(gpio_ena)

        self._chip: Optional[int] = None
        self._steps: int = 0  # position inconnue — valide uniquement après homing

    # ---- lifecycle ----

    def open(self) -> None:
        """
        Récupère le chip handle, claim les 3 pins VIC en sortie,
        force l'état sûr (driver désactivé).
        Idempotent.
        """
        if self._chip is not None:
            return
        try:
            chip = gpio_handle.get()
            lgpio.gpio_claim_output(chip, self.gpio_step, 0)
            lgpio.gpio_claim_output(chip, self.gpio_dir,  0)
            lgpio.gpio_claim_output(chip, self.gpio_ena,  config.VIC_ENA_INACTIVE_LEVEL)
            self._chip = chip
        except Exception as e:
            self._chip = None
            raise VICError(
                f"Impossible d'initialiser la VIC "
                f"(step={self.gpio_step}, dir={self.gpio_dir}, ena={self.gpio_ena}): {e}"
            ) from e

    def close(self) -> None:
        """Désactive le driver, libère les pins. Ne ferme pas le chip handle."""
        if self._chip is None:
            return
        try:
            self._disable()
        except Exception:
            pass
        try:
            lgpio.gpio_free(self._chip, self.gpio_step)
            lgpio.gpio_free(self._chip, self.gpio_dir)
            lgpio.gpio_free(self._chip, self.gpio_ena)
        except Exception:
            pass
        finally:
            self._chip = None

    def __enter__(self) -> "VICController":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise VICNotInitializedError(
                "VICController non initialisé. Appeler open() d'abord."
            )
        return self._chip

    # ---- contrôle driver ----

    def _enable(self) -> None:
        """Active le driver DM860H (ENA bas). Attend le délai de stabilisation."""
        chip = self._require_open()
        lgpio.gpio_write(chip, self.gpio_ena, config.VIC_ENA_ACTIVE_LEVEL)
        time.sleep(config.MOTOR_ENA_SETTLE_MS / 1000.0)

    def _disable(self) -> None:
        """Désactive le driver DM860H (ENA haut). État sûr."""
        chip = self._require_open()
        lgpio.gpio_write(chip, self.gpio_ena, config.VIC_ENA_INACTIVE_LEVEL)

    def disable(self) -> None:
        """API publique — désactive le driver (état sûr)."""
        if self._chip is not None:
            self._disable()

    def _set_dir(self, direction: str) -> None:
        """
        Configure la broche DIR.
        direction : 'ouverture' (vers RETOUR) ou 'fermeture' (vers DEPART)
        """
        chip = self._require_open()
        d = direction.strip().lower()
        if d == "ouverture":
            lgpio.gpio_write(chip, self.gpio_dir, config.VIC_DIR_OUVERTURE)
        elif d == "fermeture":
            lgpio.gpio_write(chip, self.gpio_dir, config.VIC_DIR_FERMETURE)
        else:
            raise VICError(f"Direction invalide : '{direction}'. Valeurs : 'ouverture' / 'fermeture'")

    # ---- génération de pas ----

    def _move_steps(self, steps: int, direction: str, speed_sps: float = config.VIC_SPEED_SPS) -> None:
        """
        Génère N pas à vitesse constante dans la direction donnée.
        Active le driver avant le premier pas, le désactive après le dernier.
        """
        if steps <= 0:
            return
        chip = self._require_open()
        speed = max(config.MOTOR_MIN_SPEED_SPS, min(config.MOTOR_MAX_SPEED_SPS, float(speed_sps)))
        # Demi-période en secondes (impulsion haute + impulsion basse)
        half_s = max(config.MOTOR_MIN_PULSE_US, int(500_000 / speed)) / 1_000_000.0
        self._set_dir(direction)
        self._enable()
        for _ in range(steps):
            lgpio.gpio_write(chip, self.gpio_step, 1)
            time.sleep(half_s)
            lgpio.gpio_write(chip, self.gpio_step, 0)
            time.sleep(half_s)
        self._disable()

    # ---- API publique — déplacement ----

    def move_to(self, target_steps: int) -> None:
        """
        Déplace la VIC vers la position absolue cible (en pas).
        No-op si déjà à la position cible.

        Args:
            target_steps : 0 (DEPART), 50 (NEUTRE), 100 (RETOUR)
        """
        delta = target_steps - self._steps
        if delta == 0:
            return
        direction = "ouverture" if delta > 0 else "fermeture"
        self._move_steps(abs(delta), direction)
        self._steps = target_steps
        log.info(f"VIC → {target_steps} pas")

    def move_relative(self, delta: int) -> None:
        """
        Déplace la VIC de delta pas relativement à la position courante.
        Positif = ouverture (vers RETOUR), négatif = fermeture (vers DEPART).
        Utile pour les tests et le diagnostic manuel.
        """
        if delta == 0:
            return
        direction = "ouverture" if delta > 0 else "fermeture"
        self._move_steps(abs(delta), direction)
        self._steps += delta

    @property
    def position(self) -> int:
        """Position courante en pas (fiable uniquement après homing)."""
        return self._steps

    # ---- homing ----

    def homing(self) -> None:
        """
        Séquence de homing VIC — ancrage mécanique sur les deux butées.

        Avec VIC_HOMING_CYCLES = 3, la séquence complète est :
            DEPART → RETOUR → DEPART → RETOUR → DEPART → RETOUR → NEUTRE
        (ancrage initial en fermeture, N cycles alternés RETOUR/DEPART,
         le dernier cycle finit en RETOUR, puis 50 pas fermeture vers NEUTRE)

        L'overcourse de MOTOR_HOMING_FIRST_CLOSE_FACTOR garantit l'ancrage
        en butée quelle que soit la position initiale.

        À l'issue du homing, self._steps = VIC_NEUTRE_STEPS (50).
        """
        overcourse = int(config.VIC_TOTAL_STEPS * config.MOTOR_HOMING_FIRST_CLOSE_FACTOR)
        n = config.VIC_HOMING_CYCLES
        log.info(f"VIC homing — {n} cycles, overcourse={overcourse} pas")

        # Ancrage initial en butée DEPART (fermeture)
        self._move_steps(overcourse, "fermeture")
        log.info("VIC homing — ancrage DEPART OK")

        for i in range(n):
            # RETOUR (ouverture)
            self._move_steps(overcourse, "ouverture")
            log.info(f"VIC homing — cycle {i + 1}/{n} RETOUR")
            if i < n - 1:
                # DEPART (fermeture) — sauf au dernier cycle
                self._move_steps(overcourse, "fermeture")
                log.info(f"VIC homing — cycle {i + 1}/{n} DEPART")

        # Depuis la butée RETOUR : 50 pas fermeture → NEUTRE
        self._move_steps(config.VIC_NEUTRE_STEPS, "fermeture")
        self._steps = config.VIC_NEUTRE_STEPS
        log.info(f"VIC homing — terminé, position NEUTRE ({config.VIC_NEUTRE_STEPS} pas)")

    def anchor_depart(self) -> None:
        """
        Mini-homing : ancrage mécanique en butée DEPART + recalage compteur à 0.

        Effectue une overcourse en fermeture pour garantir l'ancrage physique
        en butée DEPART quelle que soit la position courante réelle.
        Remet self._steps = 0 après l'ancrage.

        Appelée au début de chaque start() de programme pour garantir
        la position physique réelle avant tout déplacement vers la cible.
        """
        overcourse = int(config.VIC_TOTAL_STEPS * config.MOTOR_HOMING_FIRST_CLOSE_FACTOR)
        log.info(f"VIC mini-homing — ancrage DEPART ({overcourse} pas overcourse)")
        self._move_steps(overcourse, "fermeture")
        self._steps = 0
        log.info("VIC mini-homing — butée DEPART atteinte, compteur recalé à 0")

    def anchor_retour(self) -> None:
        """
        Mini-homing : ancrage mécanique en butée RETOUR + recalage compteur.

        Effectue une overcourse en ouverture pour garantir l'ancrage physique
        en butée RETOUR quelle que soit la position courante réelle.
        Remet self._steps = VIC_RETOUR_STEPS après l'ancrage.

        Utilisée dans les séquences de rodage pour valider l'ancrage mécanique
        en butée RETOUR.
        """
        overcourse = int(config.VIC_TOTAL_STEPS * config.MOTOR_HOMING_FIRST_CLOSE_FACTOR)
        log.info(f"VIC mini-homing — ancrage RETOUR ({overcourse} pas overcourse)")
        self._move_steps(overcourse, "ouverture")
        self._steps = config.VIC_RETOUR_STEPS
        log.info(f"VIC mini-homing — butée RETOUR atteinte, compteur recalé à {config.VIC_RETOUR_STEPS}")
