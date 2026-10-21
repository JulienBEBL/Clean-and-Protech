"""
vic.py — Contrôleur VIC (Vanne d'Injection et de Circuit) — V5.

Driver dédié à la VIC, motorisée par un driver JK-DM860H.
En V5, les signaux STEP/DIR/ENA sont câblés directement sur GPIO RPi 5
(plus de MCP3 intermédiaire comme en V4).

Positions de la VIC (réducteur 5:1, 400 pas/tour moteur → 0.18° de VIC par pas) :
    DEPART  =   0 pas  (butée fermeture, pige)   →  0°
    NEUTRE  = 250 pas  (position milieu)         → 45°
    RETOUR  = 500 pas  (butée ouverture, pige)   → 90°

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
    vic.homing()           # ancrage + cycles progressifs + positionnement NEUTRE
    vic.move_to(0)         # déplace vers DEPART
    vic.move_to(250)       # déplace vers NEUTRE
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
        self._step_cb = None  # callback optionnel appelé après chaque pas
        self._step_sign: int = 0  # sens de la série pas-à-pas en cours (+1 / -1)

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

    # ---- callback de pas ----

    def set_step_callback(self, cb) -> None:
        """
        Installe un callback appelé après chaque pas généré par _move_steps().

        Permet d'animer un organe d'affichage (LED, buzzer) pendant les
        déplacements bloquants, qui peuvent durer plus de 10 s.
        Passer None pour désactiver.

        ⚠️ Le callback est appelé à la cadence des pas (VIC_SPEED_SPS) et doit
           donc être très bref. Ses exceptions sont absorbées : un défaut
           d'affichage ne doit jamais interrompre un déplacement moteur.
        """
        self._step_cb = cb

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
            if self._step_cb is not None:
                try:
                    self._step_cb()
                except Exception:
                    pass
        self._disable()

    # ---- API publique — déplacement ----

    def move_to(self, target_steps: int) -> None:
        """
        Déplace la VIC vers la position absolue cible (en pas).
        No-op si déjà à la position cible.

        Args:
            target_steps : 0 (DEPART), 250 (NEUTRE), 500 (RETOUR)
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

    # ---- API publique — déplacement pas-à-pas NON BLOQUANT ----
    #
    # Permet d'étaler une traversée sur plusieurs itérations de la boucle
    # principale, au lieu de la bloquer pendant toute la durée du déplacement.
    # Le driver reste actif entre les pas (couple de maintien conservé) :
    # il ne faut donc PAS enchaîner begin/end à chaque pas.
    #
    # Usage :
    #     vic.begin_stepping("ouverture")
    #     ... à chaque tick : vic.step_once()
    #     vic.end_stepping()
    #     vic.set_position(config.VIC_RETOUR_STEPS)   # recalage après butée

    def begin_stepping(self, direction: str) -> None:
        """
        Démarre une série de pas non bloquante : fixe DIR et active le driver.

        Args:
            direction : 'ouverture' (vers RETOUR) ou 'fermeture' (vers DEPART)
        """
        self._require_open()
        self._set_dir(direction)
        self._step_sign = 1 if direction.strip().lower() == "ouverture" else -1
        self._enable()

    def step_once(self, speed_sps: float = config.VIC_SPEED_SPS) -> None:
        """
        Génère UN seul pas (durée ≈ 1/speed_sps seconde).

        begin_stepping() doit avoir été appelé au préalable.
        Le compteur de position suit chaque pas commandé, borné à la course
        [0, VIC_TOTAL_STEPS] : une série interrompue (arrêt PRG3 en pleine
        traversée) laisse donc une position exploitable par l'ancrage suivant.
        L'appelant recale tout de même via set_position() une fois en butée.
        """
        chip  = self._require_open()
        speed = max(config.MOTOR_MIN_SPEED_SPS, min(config.MOTOR_MAX_SPEED_SPS, float(speed_sps)))
        half_s = max(config.MOTOR_MIN_PULSE_US, int(500_000 / speed)) / 1_000_000.0
        lgpio.gpio_write(chip, self.gpio_step, 1)
        time.sleep(half_s)
        lgpio.gpio_write(chip, self.gpio_step, 0)
        time.sleep(half_s)
        self._steps = max(0, min(config.VIC_TOTAL_STEPS, self._steps + self._step_sign))

    def end_stepping(self) -> None:
        """
        Termine une série de pas non bloquante : désactive le driver (état sûr).
        Idempotente — appelable même si aucune série n'est en cours.
        """
        self._step_sign = 0
        if self._chip is not None:
            self._disable()

    def set_position(self, steps: int) -> None:
        """
        Recale le compteur de position sans déplacer le moteur.
        À utiliser après un ancrage en butée réalisé en pas-à-pas.
        """
        self._steps = int(steps)

    # ---- homing ----

    @staticmethod
    def homing_amplitudes() -> list[int]:
        """
        Amplitudes (en pas) des cycles progressifs du homing, dans l'ordre.

        Cycle k : VIC_HOMING_FIRST_PCT + (k-1) × VIC_HOMING_STEP_PCT % de la course,
        plafonné à 100 %. Les VIC_HOMING_ANCHOR_CYCLES derniers cycles ne sont pas
        dans cette liste : ce sont les cycles butée à butée.
        Valeurs actuelles : [150, 200, 250, 300, 350, 400, 450, 500].
        """
        n_anchor = max(0, min(config.VIC_HOMING_ANCHOR_CYCLES, config.VIC_HOMING_CYCLES))
        n_prog   = config.VIC_HOMING_CYCLES - n_anchor
        amps = []
        for k in range(n_prog):
            pct = min(100, config.VIC_HOMING_FIRST_PCT + k * config.VIC_HOMING_STEP_PCT)
            amps.append(round(config.VIC_TOTAL_STEPS * pct / 100))
        return amps

    def homing(self) -> None:
        """
        Séquence de homing VIC au démarrage machine (position inconnue).

            1. Ancrage DEPART sur toute la course + dépassement → compteur à 0.
            2. Cycles progressifs centrés sur NEUTRE (30 %, 40 %, … 100 %) :
               montée vers NEUTRE + A/2, descente vers NEUTRE - A/2.
               Ils ne touchent pas les piges (100 % = arrivée pile en butée).
            3. VIC_HOMING_ANCHOR_CYCLES cycles butée à butée : ancrage RETOUR
               puis ancrage DEPART, avec VIC_ANCHOR_OVERCOURSE_STEPS de dépassement.
            4. Déplacement vers NEUTRE.

        Seul l'ancrage initial peut forcer longtemps contre une pige (si la VIC
        est déjà près de DEPART) : c'est inévitable sans capteur de position.
        À l'issue du homing, self._steps = VIC_NEUTRE_STEPS (250).
        """
        amps     = self.homing_amplitudes()
        n_anchor = config.VIC_HOMING_CYCLES - len(amps)
        n        = config.VIC_HOMING_CYCLES
        log.info(
            f"VIC homing — {n} cycles ({len(amps)} progressifs {amps} pas, "
            f"{n_anchor} butée à butée), dépassement {config.VIC_ANCHOR_OVERCOURSE_STEPS} pas"
        )

        # 1. Ancrage initial — position inconnue : toute la course
        self.anchor_depart(full_travel=True)
        log.info("VIC homing — ancrage initial DEPART OK")

        # 2. Cycles progressifs centrés sur NEUTRE
        for k, amp in enumerate(amps, start=1):
            low  = max(config.VIC_DEPART_STEPS, config.VIC_NEUTRE_STEPS - amp // 2)
            high = min(config.VIC_RETOUR_STEPS, low + amp)
            self.move_to(high)
            self.move_to(low)
            log.info(f"VIC homing — cycle {k}/{n} amplitude {amp} pas ({low} ↔ {high})")

        # 3. Cycles butée à butée — dépassement court
        for k in range(len(amps) + 1, n + 1):
            self.anchor_retour()
            self.anchor_depart()
            log.info(f"VIC homing — cycle {k}/{n} butée RETOUR puis DEPART")

        # 4. Position finale NEUTRE
        self.move_to(config.VIC_NEUTRE_STEPS)
        log.info(f"VIC homing — terminé, position NEUTRE ({config.VIC_NEUTRE_STEPS} pas)")

    def _anchor_distance(self, to_depart: bool, full_travel: bool) -> int:
        """
        Nombre de pas d'un ancrage : distance jusqu'à la butée + dépassement.
        Distance = toute la course si full_travel ou VIC_ANCHOR_FULL_TRAVEL,
        sinon la distance depuis la position connue (bornée à la course).
        """
        if full_travel or config.VIC_ANCHOR_FULL_TRAVEL:
            dist = config.VIC_TOTAL_STEPS
        else:
            pos  = max(0, min(config.VIC_TOTAL_STEPS, self._steps))
            dist = pos if to_depart else config.VIC_TOTAL_STEPS - pos
        return dist + config.VIC_ANCHOR_OVERCOURSE_STEPS

    def anchor_depart(self, full_travel: bool = False) -> None:
        """
        Mini-homing : ancrage mécanique en butée DEPART + recalage compteur à 0.
        Parcourt la distance jusqu'à DEPART + VIC_ANCHOR_OVERCOURSE_STEPS, pour
        garantir l'arrivée physique en butée malgré d'éventuels pas perdus.
        Remet self._steps = 0 après l'ancrage.
        Appelée au début de chaque start() de programme pour garantir
        la position physique réelle avant tout déplacement vers la cible.

        Args:
            full_travel : True = toute la course (position inconnue, homing).
        """
        steps = self._anchor_distance(to_depart=True, full_travel=full_travel)
        log.info(f"VIC mini-homing — ancrage DEPART ({steps} pas dont "
                 f"{config.VIC_ANCHOR_OVERCOURSE_STEPS} de dépassement)")
        self._move_steps(steps, "fermeture")
        self._steps = config.VIC_DEPART_STEPS
        log.info("VIC mini-homing — butée DEPART atteinte, compteur recalé à 0")

    def anchor_retour(self, full_travel: bool = False) -> None:
        """
        Mini-homing : ancrage mécanique en butée RETOUR + recalage compteur.
        Parcourt la distance jusqu'à RETOUR + VIC_ANCHOR_OVERCOURSE_STEPS.
        Remet self._steps = VIC_RETOUR_STEPS après l'ancrage.
        Utilisée par le homing et les séquences de rodage.

        Args:
            full_travel : True = toute la course (position inconnue).
        """
        steps = self._anchor_distance(to_depart=False, full_travel=full_travel)
        log.info(f"VIC mini-homing — ancrage RETOUR ({steps} pas dont "
                 f"{config.VIC_ANCHOR_OVERCOURSE_STEPS} de dépassement)")
        self._move_steps(steps, "ouverture")
        self._steps = config.VIC_RETOUR_STEPS
        log.info(f"VIC mini-homing — butée RETOUR atteinte, compteur recalé à {config.VIC_RETOUR_STEPS}")