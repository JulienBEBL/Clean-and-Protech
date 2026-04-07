"""
moteur.py — Contrôleur moteurs pas-à-pas (DM860H, lgpio).

Responsabilité : générer les impulsions PUL via GPIO et contrôler
ENA/DIR via IOBoard. Toutes les constantes matérielles viennent de config.py.

Le chip lgpio est fourni par gpio_handle (singleton partagé).
L'IOBoard est injecté en paramètre du constructeur.

Usage :
    import libs.gpio_handle as gpio_handle
    from libs.i2c_bus import I2CBus
    from libs.io_board import IOBoard
    from libs.moteur import MotorController

    gpio_handle.init()
    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()
        mc = MotorController(io)
        mc.open()
        mc.ouverture("CUVE_TRAVAIL")
        mc.fermeture("CUVE_TRAVAIL")
        mc.close()
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

class MotorError(Exception):
    """Erreur de base du contrôleur moteur."""


class MotorNotInitializedError(MotorError):
    """Levée si open() n'a pas été appelé."""


# ============================================================
# MotorController
# ============================================================

class MotorController:
    """
    Contrôleur pour 8 drivers pas-à-pas DM860H.

    - PUL (impulsion step) : GPIO BCM via lgpio (chip handle partagé)
    - ENA (enable driver)  : IOBoard MCP3 Port B
    - DIR (direction)      : IOBoard MCP3 Port A

    Toutes les constantes (pins, vitesses, courses) proviennent de config.py.
    """

    def __init__(self, io) -> None:
        """
        Args:
            io: instance IOBoard déjà initialisée.
        """
        self.io = io
        self._chip: Optional[int] = None

    # ============================================================
    # Lifecycle
    # ============================================================

    def open(self) -> None:
        """
        Récupère le chip handle (gpio_handle) et claim les pins PUL.
        Idempotent.

        Raises:
            MotorError si gpio_handle n'est pas initialisé ou si le claim échoue.
        """
        if self._chip is not None:
            return
        try:
            chip = gpio_handle.get()
            for _, bcm in config.MOTOR_PUL_PINS.items():
                lgpio.gpio_claim_output(chip, bcm, 0)
            self._chip = chip
        except Exception as e:
            self._chip = None
            raise MotorError(f"Impossible d'initialiser MotorController: {e}") from e

    def close(self) -> None:
        """
        Met les PUL à 0, désactive tous les drivers, libère les claims GPIO.
        Ne ferme PAS le chip handle (géré par gpio_handle).
        """
        if self._chip is None:
            return
        chip = self._chip
        try:
            for _, bcm in config.MOTOR_PUL_PINS.items():
                try:
                    lgpio.gpio_write(chip, bcm, 0)
                except Exception:
                    pass
                try:
                    lgpio.gpio_free(chip, bcm)
                except Exception:
                    pass
            try:
                self.disable_all_drivers()
            except Exception:
                pass
        finally:
            self._chip = None

    def __enter__(self) -> "MotorController":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ============================================================
    # API publique — ENA (activation drivers)
    # ============================================================

    def enable_driver(self, motor_name: str) -> None:
        """Active le driver d'un moteur."""
        self.io.set_ena(self.motor_id(motor_name), config.ENA_ACTIVE_LEVEL)

    def disable_driver(self, motor_name: str) -> None:
        """Désactive le driver d'un moteur."""
        self.io.set_ena(self.motor_id(motor_name), config.ENA_INACTIVE_LEVEL)

    def enable_all_drivers(self) -> None:
        """Active tous les drivers (1..8)."""
        for m in range(1, 9):
            self.io.set_ena(m, config.ENA_ACTIVE_LEVEL)

    def disable_all_drivers(self) -> None:
        """Désactive tous les drivers (état sûr)."""
        for m in range(1, 9):
            self.io.set_ena(m, config.ENA_INACTIVE_LEVEL)

    # ============================================================
    # API publique — Mouvements
    # ============================================================

    def move_steps(
        self,
        motor_name: str,
        steps: int,
        direction: str,
        speed_sps: float = config.MOTOR_DEFAULT_CONST_SPEED_SPS,
    ) -> None:
        """
        Déplace un moteur à vitesse constante.

        Args:
            motor_name : nom métier (ex. "CUVE_TRAVAIL")
            steps      : nombre de pas
            direction  : 'ouverture' ou 'fermeture'
            speed_sps  : vitesse en steps/seconde (défaut : config.MOTOR_DEFAULT_CONST_SPEED_SPS)
        """
        chip = self._require_open()
        nsteps = int(steps)
        if nsteps <= 0:
            return

        v = self._validate_speed(speed_sps)
        m = self.motor_id(motor_name)
        d = self._norm_direction(direction)
        pul = config.MOTOR_PUL_PINS[m]

        self.io.set_dir(m, d)
        self.io.set_ena(m, config.ENA_ACTIVE_LEVEL)
        if config.MOTOR_ENA_SETTLE_MS > 0:
            time.sleep(config.MOTOR_ENA_SETTLE_MS / 1000.0)

        half_us = self._half_period_us(v)
        for _ in range(nsteps):
            lgpio.gpio_write(chip, pul, 1)
            self._sleep_us(half_us)
            lgpio.gpio_write(chip, pul, 0)
            self._sleep_us(half_us)

    def move_steps_ramp(
        self,
        motor_name: str,
        steps: int,
        direction: str,
        speed_sps: float,
        accel: float,
        decel: float,
    ) -> None:
        """
        Déplace un moteur avec rampe linéaire accel → vitesse croisière → decel.

        Args:
            motor_name : nom métier
            steps      : nombre de pas total
            direction  : 'ouverture' ou 'fermeture'
            speed_sps  : vitesse de croisière (sps)
            accel      : vitesse de départ de la rampe montante (sps)
            decel      : vitesse de fin de la rampe descendante (sps)
        """
        chip = self._require_open()
        nsteps = int(steps)
        if nsteps <= 0:
            return

        a = self._validate_speed(accel)
        v = self._validate_speed(speed_sps)
        d_end = self._validate_speed(decel)

        if a >= d_end:
            raise ValueError("accel doit être strictement inférieur à decel")
        if v < d_end:
            raise ValueError("speed_sps doit être >= decel")

        m = self.motor_id(motor_name)
        dir_norm = self._norm_direction(direction)
        pul = config.MOTOR_PUL_PINS[m]

        self.io.set_dir(m, dir_norm)
        self.io.set_ena(m, config.ENA_ACTIVE_LEVEL)
        if config.MOTOR_ENA_SETTLE_MS > 0:
            time.sleep(config.MOTOR_ENA_SETTLE_MS / 1000.0)

        s_acc, s_dec, s_cruise = self._compute_ramp_phases(nsteps, a, v, d_end)
        self._run_ramp(chip, pul, s_acc, s_cruise, s_dec, a, v, d_end)

    def ouverture(self, motor_name: str) -> None:
        """Course complète d'ouverture avec rampe (paramètres depuis config.py)."""
        self.move_steps_ramp(
            motor_name=motor_name,
            steps=config.MOTOR_OUVERTURE_STEPS,
            direction="ouverture",
            speed_sps=config.MOTOR_OUVERTURE_SPEED_SPS,
            accel=config.MOTOR_OUVERTURE_ACCEL_SPS,
            decel=config.MOTOR_OUVERTURE_DECEL_SPS,
        )

    def fermeture(self, motor_name: str) -> None:
        """Course complète de fermeture avec rampe (paramètres depuis config.py)."""
        self.move_steps_ramp(
            motor_name=motor_name,
            steps=config.MOTOR_FERMETURE_STEPS,
            direction="fermeture",
            speed_sps=config.MOTOR_FERMETURE_SPEED_SPS,
            accel=config.MOTOR_FERMETURE_ACCEL_SPS,
            decel=config.MOTOR_FERMETURE_DECEL_SPS,
        )

    def homing(self) -> None:
        """
        Homing de la machine au démarrage (séquentiel).

        Séquence :
            1. VIC → fermeture vers position 0 (DEPART) à VIC_SPEED_SPS.
               Course : VIC_TOTAL_STEPS × MOTOR_HOMING_FIRST_CLOSE_FACTOR.
            2. Moteurs 1..8 sauf VIC → fermeture séquentielle avec course majorée
               (MOTOR_FERMETURE_STEPS × MOTOR_HOMING_FIRST_CLOSE_FACTOR).
               Garantit la butée quelle que soit la position initiale.
            3. Moteurs 1..8 sauf VIC → ouverture séquentielle (course standard).
            4. MOTOR_HOMING_RODAGE_CYCLES fois (fermeture standard + ouverture standard)
               sur les 7 moteurs — rôdage des joints.

        État après homing :
            - Toutes les vannes-moteurs (sauf VIC) : OUVERTES.
            - VIC : position 3 (NEUTRE, 50 pas).

        Raises:
            MotorNotInitializedError si open() n'a pas été appelé.
        """
        self._require_open()

        import logging
        log = logging.getLogger("cleanprotech")

        first_close_steps = int(config.MOTOR_FERMETURE_STEPS * config.MOTOR_HOMING_FIRST_CLOSE_FACTOR)
        vic_homing_steps  = int(config.VIC_TOTAL_STEPS * config.MOTOR_HOMING_FIRST_CLOSE_FACTOR)
        n_cycles          = config.MOTOR_HOMING_RODAGE_CYCLES

        # Ordre d'exécution : ID driver croissant, VIC exclu du cycle fermeture/ouverture
        motor_order = sorted(
            [(name, mid) for name, mid in config.MOTOR_NAME_TO_ID.items() if name != "VIC"],
            key=lambda x: x[1],
        )

        # ── 1. VIC → butée position 0 puis neutre (position 3 = 50 pas)
        log.info(f"Homing VIC — fermeture {vic_homing_steps} pas @ {config.VIC_SPEED_SPS} sps")
        t0 = __import__("time").monotonic()
        self.move_steps("VIC", vic_homing_steps, "fermeture", config.VIC_SPEED_SPS)
        log.info(f"Homing VIC — butée 0 OK ({__import__('time').monotonic() - t0:.1f}s)")

        vic_neutral_steps = config.VIC_POSITIONS[3]
        log.info(f"Homing VIC — ouverture vers neutre {vic_neutral_steps} pas @ {config.VIC_SPEED_SPS} sps")
        t0 = __import__("time").monotonic()
        self.move_steps("VIC", vic_neutral_steps, "ouverture", config.VIC_SPEED_SPS)
        log.info(f"Homing VIC — neutre OK ({__import__('time').monotonic() - t0:.1f}s)")

        # ── 2. Première fermeture — course majorée (butée garantie)
        log.info(f"Homing — fermeture initiale {first_close_steps} pas (+{int((config.MOTOR_HOMING_FIRST_CLOSE_FACTOR - 1)*100)}%)")
        for name, mid in motor_order:
            log.info(f"  [{mid}/8] {name} → fermeture")
            t0 = __import__("time").monotonic()
            self.move_steps_ramp(
                name,
                first_close_steps,
                "fermeture",
                config.MOTOR_FERMETURE_SPEED_SPS,
                config.MOTOR_FERMETURE_ACCEL_SPS,
                config.MOTOR_FERMETURE_DECEL_SPS,
            )
            log.info(f"  [{mid}/8] {name} — OK ({__import__('time').monotonic() - t0:.1f}s)")

        # ── 3. Première ouverture
        log.info("Homing — ouverture initiale")
        for name, mid in motor_order:
            log.info(f"  [{mid}/8] {name} → ouverture")
            t0 = __import__("time").monotonic()
            self.ouverture(name)
            log.info(f"  [{mid}/8] {name} — OK ({__import__('time').monotonic() - t0:.1f}s)")

        # ── 4. Cycles de rodage (fermeture standard + ouverture)
        for cycle in range(1, n_cycles + 1):
            log.info(f"Homing — rodage cycle {cycle}/{n_cycles} — fermeture")
            for name, mid in motor_order:
                log.info(f"  [{mid}/8] {name} → fermeture")
                t0 = __import__("time").monotonic()
                self.fermeture(name)
                log.info(f"  [{mid}/8] {name} — OK ({__import__('time').monotonic() - t0:.1f}s)")

            log.info(f"Homing — rodage cycle {cycle}/{n_cycles} — ouverture")
            for name, mid in motor_order:
                log.info(f"  [{mid}/8] {name} → ouverture")
                t0 = __import__("time").monotonic()
                self.ouverture(name)
                log.info(f"  [{mid}/8] {name} — OK ({__import__('time').monotonic() - t0:.1f}s)")

    # ============================================================
    # Internals — résolution noms
    # ============================================================

    @staticmethod
    def _norm_name(name: str) -> str:
        n = name.strip().upper().replace("-", "_")
        if n in config.MOTOR_ALIASES:
            n = config.MOTOR_ALIASES[n]
        else:
            n = n.replace(" ", "_")
        return n

    def motor_id(self, motor_name: str) -> int:
        """Retourne l'ID (1..8) à partir du nom métier."""
        n = self._norm_name(motor_name)
        if n not in config.MOTOR_NAME_TO_ID:
            valid = ", ".join(sorted(config.MOTOR_NAME_TO_ID.keys()))
            raise ValueError(f"Moteur inconnu '{motor_name}'. Valides : {valid}")
        return config.MOTOR_NAME_TO_ID[n]

    @staticmethod
    def _norm_direction(direction: str) -> str:
        d = direction.strip().upper()
        if d in ("OUVERTURE", "OPEN", "O"):
            return "ouverture"
        if d in ("FERMETURE", "CLOSE", "F"):
            return "fermeture"
        raise ValueError("direction doit être 'ouverture' ou 'fermeture'")

    def _require_open(self) -> int:
        if self._chip is None:
            raise MotorNotInitializedError(
                "MotorController non initialisé. Appeler open() d'abord."
            )
        return self._chip

    # ============================================================
    # Internals — timing bas-niveau
    # ============================================================

    @staticmethod
    def _sleep_us(us: int) -> None:
        time.sleep(max(0, int(us)) / 1_000_000.0)

    @staticmethod
    def _validate_speed(sps: float) -> float:
        s = float(sps)
        if s < config.MOTOR_MIN_SPEED_SPS or s > config.MOTOR_MAX_SPEED_SPS:
            raise ValueError(
                f"Vitesse hors plage [{config.MOTOR_MIN_SPEED_SPS}, "
                f"{config.MOTOR_MAX_SPEED_SPS}] sps : {s}"
            )
        return s

    def _half_period_us(self, speed_sps: float) -> int:
        """Calcule la demi-période en µs pour une vitesse donnée."""
        half_us = int((1_000_000.0 / float(speed_sps)) / 2.0)
        return max(half_us, config.MOTOR_MIN_PULSE_US)

    # ============================================================
    # Internals — calcul et exécution rampe
    # ============================================================

    def _compute_ramp_phases(
        self, nsteps: int, accel: float, speed: float, decel: float
    ) -> tuple[int, int, int]:
        """Calcule les 3 phases (acc, dec, cruise) en nombre de pas."""
        s_acc_nom = int(0.5 * (accel + speed) * config.MOTOR_RAMP_ACCEL_TIME_S)
        s_dec_nom = int(0.5 * (speed + decel) * config.MOTOR_RAMP_DECEL_TIME_S)

        if s_acc_nom + s_dec_nom <= nsteps:
            s_acc = s_acc_nom
            s_dec = s_dec_nom
            s_cruise = nsteps - s_acc - s_dec
        else:
            total_nom = max(1, s_acc_nom + s_dec_nom)
            s_acc = int(nsteps * (s_acc_nom / total_nom))
            s_acc = max(0, min(s_acc, nsteps))
            s_dec = nsteps - s_acc
            s_cruise = 0

        return s_acc, s_dec, s_cruise

    def _run_ramp(
        self,
        chip: int,
        pul: int,
        s_acc: int,
        s_cruise: int,
        s_dec: int,
        accel: float,
        speed: float,
        decel: float,
    ) -> None:
        """Exécute les 3 phases de rampe pour un seul moteur."""
        # montée
        for i in range(s_acc):
            frac = (i + 1) / s_acc
            sps = accel + (speed - accel) * frac
            half_us = self._half_period_us(sps)
            lgpio.gpio_write(chip, pul, 1); self._sleep_us(half_us)
            lgpio.gpio_write(chip, pul, 0); self._sleep_us(half_us)

        # croisière
        if s_cruise > 0:
            half_us = self._half_period_us(speed)
            for _ in range(s_cruise):
                lgpio.gpio_write(chip, pul, 1); self._sleep_us(half_us)
                lgpio.gpio_write(chip, pul, 0); self._sleep_us(half_us)

        # descente
        for i in range(s_dec):
            frac = (i + 1) / s_dec
            sps = speed + (decel - speed) * frac
            half_us = self._half_period_us(sps)
            lgpio.gpio_write(chip, pul, 1); self._sleep_us(half_us)
            lgpio.gpio_write(chip, pul, 0); self._sleep_us(half_us)
