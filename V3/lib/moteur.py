"""
moteur.py — Stepper motors (PUL via lgpio, DIR/ENA via IOBoard i2c.py)

- PUL: GPIO RPi (BCM) par moteur
- DIR/ENA: via IOBoard (MCP) -> io.set_dir(motor_id, ...) / io.set_ena(motor_id, ...)

Spécificités projet:
- API par NOM moteur
- ENA inversé:
    ENA=1 => driver désactivé
    ENA=0 => driver actif
- Ouverture/fermeture complète: 30000 pas (constante)

Vitesse:
- bornée: 50..3200 pas/s (fixe)
- la vitesse réelle peut être plus basse si on atteint la limite min_pulse_us
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List, Sequence

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio is required on Raspberry Pi OS. Install python3-lgpio.") from e

from i2c import IOBoard  # type: ignore


class MotorError(Exception):
    pass


class MotorNotInitializedError(MotorError):
    pass


# ----------------------------
# Paramètres projet (fixes)
# ----------------------------
FULL_TRAVEL_STEPS = 32_000

MIN_SPEED_SPS = 100
MAX_SPEED_SPS = 3000

RAMP_ACCEL_TIME_S = 3.0
RAMP_DECEL_TIME_S = 3.0

# ----------------------------
# Mapping PUL (BCM) — figé PCB
# ----------------------------
PUL_PINS_BCM: Dict[int, int] = {
    1: 17,
    2: 27,
    3: 22,
    4: 5,
    5: 18,
    6: 23,
    7: 24,
    8: 25,
}

# ----------------------------
# Mapping noms moteurs -> ID
# ----------------------------
MOTOR_NAME_TO_ID: Dict[str, int] = {
    "CUVE_TRAVAIL": 4,
    "EAU_PROPRE": 8,
    "POMPE": 2,
    "DEPART": 7,
    "RETOUR": 3,
    "POT_A_BOUE": 1,
    "EGOUTS": 5,
    "VIC": 6,
}

MOTOR_ALIASES: Dict[str, str] = {
    "CUVE TRAVAIL": "CUVE_TRAVAIL",
    "EAU PROPRE": "EAU_PROPRE",
    "POT À BOUE": "POT_A_BOUE",
    "POT A BOUE": "POT_A_BOUE",
    "EGOUT": "EGOUTS",
    "EGOUTS": "EGOUTS",
}

# ENA inversé (spécifique à ton câblage)
ENA_ACTIVE_LEVEL = 0   # driver ON
ENA_INACTIVE_LEVEL = 1 # driver OFF

# Timing robustesse
MIN_PULSE_US = 50
ENA_SETTLE_MS = 5


@dataclass(frozen=True)
class MotorConfig:
    gpiochip_index: int = 0
    min_pulse_us: int = MIN_PULSE_US


class MotorController:
    """
    Contrôleur moteurs:
    - utilise IOBoard pour ENA/DIR (MCP)
    - utilise lgpio pour PUL (GPIO RPi)

    Fonctions:
      - enable_all_drivers()
      - disable_all_drivers()
      - move_steps(motor_name, steps, direction, speed_sps)
      - move_steps_ramp(motor_name, steps, direction, speed_sps, accel, decel)
    """

    def __init__(self, io: IOBoard, config: MotorConfig = MotorConfig()):
        self.io = io
        self.config = config
        self._chip: Optional[int] = None

    # -----------------
    # lifecycle
    # -----------------
    def open(self) -> None:
        if self._chip is not None:
            return
        try:
            chip = lgpio.gpiochip_open(self.config.gpiochip_index)
            for _, bcm in PUL_PINS_BCM.items():
                lgpio.gpio_claim_output(chip, bcm, 0)
            self._chip = chip
        except Exception as e:
            self._chip = None
            raise MotorError(f"Failed to open MotorController: {e}") from e

    def close(self) -> None:
        if self._chip is None:
            return
        try:
            for _, bcm in PUL_PINS_BCM.items():
                try:
                    lgpio.gpio_write(self._chip, bcm, 0)
                except Exception:
                    pass
            try:
                self.disable_all_drivers()
            except Exception:
                pass
        finally:
            lgpio.gpiochip_close(self._chip)
            self._chip = None

    def __enter__(self) -> "MotorController":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise MotorNotInitializedError("MotorController not initialized. Call open() first.")
        return self._chip

    # -----------------
    # name -> id
    # -----------------
    @staticmethod
    def _norm_name(name: str) -> str:
        n = name.strip().upper()
        n = n.replace("-", "_")
        if n in MOTOR_ALIASES:
            n = MOTOR_ALIASES[n]
        else:
            n = n.replace(" ", "_")
        return n

    def motor_id(self, motor_name: str) -> int:
        n = self._norm_name(motor_name)
        if n not in MOTOR_NAME_TO_ID:
            valid = ", ".join(sorted(MOTOR_NAME_TO_ID.keys()))
            raise ValueError(f"Unknown motor_name '{motor_name}'. Valid: {valid}")
        return MOTOR_NAME_TO_ID[n]

    @staticmethod
    def _norm_direction(direction: str) -> str:
        d = direction.strip().upper()
        if d in ("OUVERTURE", "OPEN", "O"):
            return "ouverture"
        if d in ("FERMETURE", "CLOSE", "F"):
            return "fermeture"
        raise ValueError("direction must be 'ouverture' or 'fermeture'")

    # -----------------
    # ENA helpers
    # -----------------
    def enable_driver(self, motor_name: str) -> None:
        m = self.motor_id(motor_name)
        self.io.set_ena(m, ENA_ACTIVE_LEVEL)

    def disable_driver(self, motor_name: str) -> None:
        m = self.motor_id(motor_name)
        self.io.set_ena(m, ENA_INACTIVE_LEVEL)

    def enable_all_drivers(self) -> None:
        for m in range(1, 9):
            self.io.set_ena(m, ENA_ACTIVE_LEVEL)

    def disable_all_drivers(self) -> None:
        for m in range(1, 9):
            self.io.set_ena(m, ENA_INACTIVE_LEVEL)

    # -----------------
    # timing
    # -----------------
    @staticmethod
    def _sleep_us(us: int) -> None:
        time.sleep(max(0, int(us)) / 1_000_000.0)

    def _validate_speed(self, sps: float) -> float:
        s = float(sps)
        if s < MIN_SPEED_SPS or s > MAX_SPEED_SPS:
            raise ValueError(f"speed_sps out of range [{MIN_SPEED_SPS}, {MAX_SPEED_SPS}]")
        return s

    def _compute_half_period_us(self, speed_sps: float) -> int:
        """
        Convertit speed_sps -> demi période (µs) pour un duty ~50%.
        Applique min_pulse_us garde-fou.
        """
        s = float(speed_sps)
        period_s = 1.0 / s
        half_us = int((period_s * 1_000_000.0) / 2.0)
        min_us = int(self.config.min_pulse_us)
        return half_us if half_us >= min_us else min_us

    # -----------------
    # API V1: vitesse constante
    # -----------------
    def move_steps(self, motor_name: str, steps: int, direction: str, speed_sps: float) -> None:
        chip = self._require_open()

        nsteps = int(steps)
        if nsteps < 0:
            raise ValueError("steps must be >= 0")
        if nsteps == 0:
            return

        sps = self._validate_speed(speed_sps)

        m = self.motor_id(motor_name)
        d = self._norm_direction(direction)
        pul_gpio = PUL_PINS_BCM[m]

        self.io.set_dir(m, d)
        self.io.set_ena(m, ENA_ACTIVE_LEVEL)
        if ENA_SETTLE_MS > 0:
            time.sleep(ENA_SETTLE_MS / 1000.0)

        half_us = self._compute_half_period_us(sps)

        for _ in range(nsteps):
            lgpio.gpio_write(chip, pul_gpio, 1)
            self._sleep_us(half_us)
            lgpio.gpio_write(chip, pul_gpio, 0)
            self._sleep_us(half_us)

        # Politique: on laisse ENA actif (utile pour couple/étanchéité).

    # -----------------
    # API V2: rampe linéaire (accel/decel ~5s)
    # -----------------
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
        Déplace un moteur avec rampe linéaire:
        - accel: vitesse de départ (pas/s)
        - speed_sps: vitesse de croisière (pas/s)
        - decel: vitesse de fin (pas/s)
        Contraintes:
        - accel < decel
        - speed_sps >= decel
        - toutes dans [50..3200]

        Rampes:
        - accel -> speed sur ~5s
        - speed -> decel sur ~5s
        Si steps trop petit, les rampes sont compressées pour tenir dans le mouvement.
        """
        chip = self._require_open()

        nsteps = int(steps)
        if nsteps < 0:
            raise ValueError("steps must be >= 0")
        if nsteps == 0:
            return

        a = self._validate_speed(accel)
        v = self._validate_speed(speed_sps)
        d_end = self._validate_speed(decel)

        if not (a < d_end):
            raise ValueError("accel must be strictly < decel")
        if v < d_end:
            raise ValueError("speed_sps must be >= decel")

        m = self.motor_id(motor_name)
        d = self._norm_direction(direction)
        pul_gpio = PUL_PINS_BCM[m]

        self.io.set_dir(m, d)
        self.io.set_ena(m, ENA_ACTIVE_LEVEL)
        if ENA_SETTLE_MS > 0:
            time.sleep(ENA_SETTLE_MS / 1000.0)

        # Estimation du nb de pas nécessaires pour rampes à durée fixe
        # steps = intégrale(v(t)) dt, v(t) linéaire => moyenne * durée
        s_acc_nom = int(0.5 * (a + v) * RAMP_ACCEL_TIME_S)
        s_dec_nom = int(0.5 * (v + d_end) * RAMP_DECEL_TIME_S)

        if s_acc_nom + s_dec_nom <= nsteps:
            s_acc = s_acc_nom
            s_dec = s_dec_nom
            s_cruise = nsteps - s_acc - s_dec
        else:
            # Compression: on répartit proportionnellement, sans dépasser nsteps
            total_nom = max(1, s_acc_nom + s_dec_nom)
            s_acc = int(nsteps * (s_acc_nom / total_nom))
            s_acc = max(0, min(s_acc, nsteps))
            s_dec = nsteps - s_acc
            s_cruise = 0

        # --- phase accel (a -> v) ---
        if s_acc > 0:
            for i in range(s_acc):
                # interpolation linéaire
                frac = (i + 1) / s_acc
                sps = a + (v - a) * frac
                half_us = self._compute_half_period_us(sps)

                lgpio.gpio_write(chip, pul_gpio, 1)
                self._sleep_us(half_us)
                lgpio.gpio_write(chip, pul_gpio, 0)
                self._sleep_us(half_us)

        # --- phase cruise (v constant) ---
        if s_cruise > 0:
            half_us = self._compute_half_period_us(v)
            for _ in range(s_cruise):
                lgpio.gpio_write(chip, pul_gpio, 1)
                self._sleep_us(half_us)
                lgpio.gpio_write(chip, pul_gpio, 0)
                self._sleep_us(half_us)

        # --- phase decel (v -> d_end) ---
        if s_dec > 0:
            for i in range(s_dec):
                frac = (i + 1) / s_dec
                sps = v + (d_end - v) * frac  # descend vers d_end
                half_us = self._compute_half_period_us(sps)

                lgpio.gpio_write(chip, pul_gpio, 1)
                self._sleep_us(half_us)
                lgpio.gpio_write(chip, pul_gpio, 0)
                self._sleep_us(half_us)

        # Politique: ENA reste actif.
    
    def move_steps_multi(
        self,
        motor_names: Sequence[str],
        steps: int,
        direction: str,
        speed_sps: float,
    ) -> None:
        """
        Fait tourner plusieurs moteurs en même temps, même direction, même vitesse.

        Params:
        - motor_names: liste/tuple de noms moteurs (1..7)
        - steps: nb de pas (>=0)
        - direction: "ouverture" / "fermeture"
        - speed_sps: vitesse en pas/s (bornée MIN_SPEED_SPS..MAX_SPEED_SPS)

        Notes:
        - Pas de rampe.
        - Pulses générés "en parallèle" (tous les PUL high puis low).
        """
        chip = self._require_open()

        nsteps = int(steps)
        if nsteps < 0:
            raise ValueError("steps must be >= 0")
        if nsteps == 0:
            return

        names = list(motor_names)
        if not (1 <= len(names) <= 7):
            raise ValueError("motor_names length must be between 1 and 7")

        # Normalise + check doublons
        norm_names: List[str] = [self._norm_name(n) for n in names]
        if len(set(norm_names)) != len(norm_names):
            raise ValueError("motor_names contains duplicates")

        sps = self._validate_speed(speed_sps)
        dir_norm = self._norm_direction(direction)
        half_us = self._compute_half_period_us(sps)

        # Résout IDs + GPIO PUL
        motor_ids: List[int] = [self.motor_id(n) for n in norm_names]
        pul_gpios: List[int] = [PUL_PINS_BCM[mid] for mid in motor_ids]

        # Configure DIR + enable drivers (ENA inversé -> 0 = ON)
        for mid in motor_ids:
            self.io.set_dir(mid, dir_norm)
            self.io.set_ena(mid, ENA_ACTIVE_LEVEL)

        if ENA_SETTLE_MS > 0:
            time.sleep(ENA_SETTLE_MS / 1000.0)

        # Boucle pulses "en parallèle"
        for _ in range(nsteps):
            for g in pul_gpios:
                lgpio.gpio_write(chip, g, 1)
            self._sleep_us(half_us)

            for g in pul_gpios:
                lgpio.gpio_write(chip, g, 0)
            self._sleep_us(half_us)

        # Politique: ENA reste actif (comme move_steps).