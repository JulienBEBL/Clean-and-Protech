"""
stepper.py — Pilotage moteurs pas-à-pas pour le rodage industriel.

Standalone — aucun import depuis V4/. Code inspiré de V4/libs/moteur.py
et V4/libs/io_board.py. Constantes extraites de V4/config.py (lecture seule).

Deux moteurs contrôlés :

    POMPE — driver ID 8, PUL GPIO BCM 25
        ENA : MCP3 Port B, pin B7  (actif bas — ENA=0 → driver ON)
        DIR : MCP3 Port A, pin A0  (OUVERTURE=1, FERMETURE=0)
        Steps ouverture  : 3 830   (V4 MOTOR_OUVERTURE_STEPS)
        Steps fermeture  : 4 000   (V4 MOTOR_FERMETURE_STEPS)

    VIC (V4V 5 positions) — driver ID 3, PUL GPIO BCM 22
        ENA : MCP3 Port B, pin B2  (actif bas — ENA=0 → driver ON)
        DIR : MCP3 Port A, pin A5  (OUVERTURE=1, FERMETURE=0)
        Positions (pas abs) : {1:0, 2:30, 3:50, 4:70, 5:100}  (V4 VIC_POSITIONS)

Hardware cible : Raspberry Pi 5, Python 3.11+, lgpio + smbus2.
"""

from __future__ import annotations

import time
from typing import Optional

try:
    import lgpio  # type: ignore
except ImportError as exc:
    raise ImportError("lgpio requis : sudo apt install python3-lgpio") from exc

try:
    from smbus2 import SMBus  # type: ignore
except ImportError as exc:
    raise ImportError("smbus2 requis : pip install smbus2") from exc


# ============================================================
# Constantes hardware — extraites de V4/config.py (lecture seule)
# ============================================================

# GPIO
_GPIO_CHIP = 4          # gpiochip4 — Raspberry Pi 5 uniquement

# I2C
_I2C_BUS_ID = 1
_MCP3_ADDR  = 0x25      # MCP23017 drivers moteurs : ENA (Port B) + DIR (Port A)

# ENA : actif bas (câblage inversé — ENA=0 → driver ON, ENA=1 → driver OFF)
_ENA_ON  = 0
_ENA_OFF = 1

# POMPE — driver ID 8
_POMPE_BCM     = 25
_POMPE_ENA_PIN = 7      # MCP3 Port B, pin B7 (ID − 1 = 7)
_POMPE_DIR_PIN = 0      # MCP3 Port A, pin A0 (8 − ID = 0)
_POMPE_OUV_STEPS = 3_830
_POMPE_FER_STEPS = 4_000
_POMPE_OUV_SPS   = 800.0
_POMPE_OUV_ACC   =  50.0
_POMPE_OUV_DEC   = 700.0
_POMPE_FER_SPS   = 1_600.0
_POMPE_FER_ACC   =   600.0
_POMPE_FER_DEC   = 1_200.0

# VIC (V4V) — driver ID 3
_VIC_BCM     = 22
_VIC_ENA_PIN = 2        # MCP3 Port B, pin B2 (ID − 1 = 2)
_VIC_DIR_PIN = 5        # MCP3 Port A, pin A5 (8 − ID = 5)
_VIC_SPS     = 20.0     # vitesse constante (lent — précision mécanique)

# Positions absolues V4V (pas) — V4 VIC_POSITIONS
VIC_POSITIONS: dict = {1: 0, 2: 30, 3: 50, 4: 70, 5: 100}

# Timing bas-niveau
_MIN_PULSE_US   = 50    # µs  — demi-impulsion minimale (V4 MOTOR_MIN_PULSE_US)
_ENA_SETTLE_MS  =  5    # ms  — délai ENA → premier pas  (V4 MOTOR_ENA_SETTLE_MS)

# Profil rampe
_RAMP_ACCEL_TIME_S = 2.0    # V4 MOTOR_RAMP_ACCEL_TIME_S
_RAMP_DECEL_TIME_S = 0.5    # V4 MOTOR_RAMP_DECEL_TIME_S

# MCP23017 registres (BANK=0 — mode par défaut)
_REG_IOCON  = 0x0A
_REG_IODIRA = 0x00
_REG_IODIRB = 0x01
_REG_OLATA  = 0x14
_REG_OLATB  = 0x15


# ============================================================
# RodageDriver
# ============================================================

class RodageDriver:
    """
    Contrôleur pour les deux moteurs du rodage : POMPE (vanne classique) et
    VIC (V4V 5 positions).

    Inspiré de V4/libs/moteur.py et V4/libs/io_board.py.
    Standalone — aucun import depuis V4/.

    Usage :
        with RodageDriver() as drv:
            drv.move_vanne("ouverture")
            vic_steps = drv.move_vic_to(0, 2)
            drv.disable_all()
    """

    def __init__(self) -> None:
        self._chip: Optional[int] = None
        self._bus:  Optional[SMBus] = None
        self._olat_a = 0x00   # cache latch MCP3 Port A (DIR)
        self._olat_b = 0xFF   # cache latch MCP3 Port B (ENA) — actif bas → 0xFF = tout OFF

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Ouvre gpiochip + bus I2C, claim les PUL, initialise MCP3 (état sûr)."""
        if self._chip is not None:
            return

        try:
            chip = lgpio.gpiochip_open(_GPIO_CHIP)
        except Exception as exc:
            raise RuntimeError(
                f"Impossible d'ouvrir gpiochip{_GPIO_CHIP}: {exc}"
            ) from exc

        try:
            lgpio.gpio_claim_output(chip, _POMPE_BCM, 0)
            lgpio.gpio_claim_output(chip, _VIC_BCM,   0)
        except Exception as exc:
            lgpio.gpiochip_close(chip)
            raise RuntimeError(f"Claim GPIO échoué: {exc}") from exc

        try:
            bus = SMBus(_I2C_BUS_ID)
        except Exception as exc:
            lgpio.gpio_free(chip, _POMPE_BCM)
            lgpio.gpio_free(chip, _VIC_BCM)
            lgpio.gpiochip_close(chip)
            raise RuntimeError(f"Impossible d'ouvrir I2C bus {_I2C_BUS_ID}: {exc}") from exc

        # MCP3 init — BANK=0, Port A et B en sorties, drivers OFF
        bus.write_byte_data(_MCP3_ADDR, _REG_IOCON,  0x00)
        bus.write_byte_data(_MCP3_ADDR, _REG_IODIRA, 0x00)
        bus.write_byte_data(_MCP3_ADDR, _REG_IODIRB, 0x00)
        self._olat_a = 0x00
        self._olat_b = 0xFF   # ENA_OFF=1 sur tous les bits → tous drivers OFF
        bus.write_byte_data(_MCP3_ADDR, _REG_OLATA, self._olat_a)
        bus.write_byte_data(_MCP3_ADDR, _REG_OLATB, self._olat_b)

        self._chip = chip
        self._bus  = bus

    def close(self) -> None:
        """Désactive drivers, met PUL à 0, libère GPIO et ferme I2C."""
        if self._chip is None:
            return
        chip = self._chip
        bus  = self._bus
        try:
            self.disable_all()
        except Exception:
            pass
        for bcm in (_POMPE_BCM, _VIC_BCM):
            try:
                lgpio.gpio_write(chip, bcm, 0)
            except Exception:
                pass
            try:
                lgpio.gpio_free(chip, bcm)
            except Exception:
                pass
        try:
            lgpio.gpiochip_close(chip)
        except Exception:
            pass
        try:
            bus.close()
        except Exception:
            pass
        self._chip = None
        self._bus  = None

    def __enter__(self) -> "RodageDriver":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ── ENA ──────────────────────────────────────────────────────────────────

    def _set_ena(self, pin: int, state: int) -> None:
        bit = 1 << pin
        if state:
            self._olat_b |= bit
        else:
            self._olat_b &= (~bit & 0xFF)
        self._bus.write_byte_data(_MCP3_ADDR, _REG_OLATB, self._olat_b)

    def disable_all(self) -> None:
        """Désactive les deux drivers (état sûr — ENA_OFF=1 actif bas)."""
        self._olat_b = 0xFF
        self._bus.write_byte_data(_MCP3_ADDR, _REG_OLATB, self._olat_b)

    # ── DIR ──────────────────────────────────────────────────────────────────

    def _set_dir(self, pin: int, ouverture: bool) -> None:
        bit = 1 << pin
        if ouverture:
            self._olat_a |= bit
        else:
            self._olat_a &= (~bit & 0xFF)
        self._bus.write_byte_data(_MCP3_ADDR, _REG_OLATA, self._olat_a)

    # ── Génération d'impulsions ───────────────────────────────────────────────

    @staticmethod
    def _half_us(sps: float) -> int:
        """Demi-période en µs pour une vitesse sps donnée."""
        return max(int(500_000.0 / sps), _MIN_PULSE_US)

    @staticmethod
    def _sleep_us(us: int) -> None:
        time.sleep(max(0, us) / 1_000_000.0)

    def _pulse_n(self, bcm: int, n: int, half_us: int) -> None:
        """Émet n impulsions PUL à demi-période constante."""
        chip = self._chip
        for _ in range(n):
            lgpio.gpio_write(chip, bcm, 1); self._sleep_us(half_us)
            lgpio.gpio_write(chip, bcm, 0); self._sleep_us(half_us)

    # ── Rampe linéaire ────────────────────────────────────────────────────────

    def _compute_ramp(
        self, nsteps: int, accel: float, speed: float, decel: float
    ) -> tuple:
        """
        Calcule les 3 phases (acc, cruise, dec) en nombre de pas.
        Inspiré de V4/libs/moteur.py _compute_ramp_phases().
        """
        s_acc_nom = int(0.5 * (accel + speed) * _RAMP_ACCEL_TIME_S)
        s_dec_nom = int(0.5 * (speed + decel) * _RAMP_DECEL_TIME_S)
        if s_acc_nom + s_dec_nom <= nsteps:
            return s_acc_nom, nsteps - s_acc_nom - s_dec_nom, s_dec_nom
        total_nom = max(1, s_acc_nom + s_dec_nom)
        s_acc = max(0, min(int(nsteps * (s_acc_nom / total_nom)), nsteps))
        return s_acc, 0, nsteps - s_acc

    def _run_ramp(
        self,
        bcm: int,
        s_acc: int,
        s_cruise: int,
        s_dec: int,
        accel: float,
        speed: float,
        decel: float,
    ) -> None:
        """
        Exécute une rampe linéaire : montée → croisière → descente.
        Inspiré de V4/libs/moteur.py _run_ramp().
        """
        chip = self._chip
        # montée : accel → speed
        for i in range(s_acc):
            sps = accel + (speed - accel) * (i + 1) / s_acc
            half_us = self._half_us(sps)
            lgpio.gpio_write(chip, bcm, 1); self._sleep_us(half_us)
            lgpio.gpio_write(chip, bcm, 0); self._sleep_us(half_us)
        # croisière
        if s_cruise > 0:
            self._pulse_n(bcm, s_cruise, self._half_us(speed))
        # descente : speed → decel
        for i in range(s_dec):
            sps = speed + (decel - speed) * (i + 1) / s_dec
            half_us = self._half_us(sps)
            lgpio.gpio_write(chip, bcm, 1); self._sleep_us(half_us)
            lgpio.gpio_write(chip, bcm, 0); self._sleep_us(half_us)

    def _move_ramp(
        self, bcm: int, steps: int, sps: float, accel: float, decel: float
    ) -> None:
        s_acc, s_cruise, s_dec = self._compute_ramp(steps, accel, sps, decel)
        self._run_ramp(bcm, s_acc, s_cruise, s_dec, accel, sps, decel)

    # ── API publique ──────────────────────────────────────────────────────────

    def move_vanne(self, direction: str) -> None:
        """
        Course complète POMPE avec profil rampe.

        Args:
            direction : 'ouverture' ou 'fermeture'
        """
        ouv = direction.strip().lower().startswith("o")
        self._set_dir(_POMPE_DIR_PIN, ouv)
        self._set_ena(_POMPE_ENA_PIN, _ENA_ON)
        time.sleep(_ENA_SETTLE_MS / 1000.0)
        if ouv:
            self._move_ramp(
                _POMPE_BCM,
                _POMPE_OUV_STEPS,
                _POMPE_OUV_SPS,
                _POMPE_OUV_ACC,
                _POMPE_OUV_DEC,
            )
        else:
            self._move_ramp(
                _POMPE_BCM,
                _POMPE_FER_STEPS,
                _POMPE_FER_SPS,
                _POMPE_FER_ACC,
                _POMPE_FER_DEC,
            )

    def move_vic_to(self, current_steps: int, target_pos: int) -> int:
        """
        Déplace la VIC vers target_pos (1..5) à vitesse constante.

        Args:
            current_steps : position absolue courante en pas
            target_pos    : position cible (clé de VIC_POSITIONS)

        Returns:
            Nouvelle position absolue en pas.
        """
        target_steps = VIC_POSITIONS[target_pos]
        delta = target_steps - current_steps
        if delta == 0:
            return current_steps
        ouv = delta > 0
        self._set_dir(_VIC_DIR_PIN, ouv)
        self._set_ena(_VIC_ENA_PIN, _ENA_ON)
        time.sleep(_ENA_SETTLE_MS / 1000.0)
        self._pulse_n(_VIC_BCM, abs(delta), self._half_us(_VIC_SPS))
        return target_steps

    def vic_home(self, init_steps: int = 110) -> int:
        """
        Envoie la VIC à la butée position 1 avec course majorée.
        Garantit la position 1 quelle que soit la position de départ.

        Args:
            init_steps : nombre de pas en fermeture (défaut = 110 = VIC_TOTAL_STEPS + 10 %)

        Returns:
            0  (position absolue = 0 pas = position 1)
        """
        self._set_dir(_VIC_DIR_PIN, False)   # fermeture
        self._set_ena(_VIC_ENA_PIN, _ENA_ON)
        time.sleep(_ENA_SETTLE_MS / 1000.0)
        self._pulse_n(_VIC_BCM, init_steps, self._half_us(_VIC_SPS))
        return 0
