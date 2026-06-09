"""
stepper.py — Pilotage moteurs pas-à-pas pour le rodage industriel.

Standalone — aucun import depuis V4/. Code inspiré de V4/libs/moteur.py
et V4/libs/io_board.py. Constantes extraites de V4/config.py (lecture seule).

4 vannes classiques — même type mécanique, même course :

    POMPE        — driver ID 8  PUL GPIO BCM 25  ENA B7  DIR A0
    RETOUR       — driver ID 1  PUL GPIO BCM 17  ENA B0  DIR A7
    CUVE_TRAVAIL — driver ID 4  PUL GPIO BCM  5  ENA B3  DIR A4
    EAU_PROPRE   — driver ID 7  PUL GPIO BCM 24  ENA B6  DIR A1

Course commune (V4 MOTOR_OUVERTURE/FERMETURE_STEPS) :
    Ouverture : 3 830 pas  rampe 50→800→700 sps
    Fermeture : 4 000 pas  rampe 600→1600→1200 sps

Microstepping : 400 pas/tour — DM860H DIP 11011111 (V4 DRIVER_MICROSTEP)
ENA actif bas : ENA=0 → driver ON  (V4 ENA_ACTIVE_LEVEL=0)
DIR           : OUVERTURE=1  FERMETURE=0  (V4 io_board.py set_dir)
MCP3 (0x25)   : Port B = ENA1..ENA8 (B0..B7)  Port A = DIR1..DIR8 (A7..A0)
I2C bus 1, gpiochip4 (RPi 5)

Hardware cible : Raspberry Pi 5, Python 3.11+, lgpio + smbus2.
"""

from __future__ import annotations

import time
from typing import NamedTuple, Optional

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

_GPIO_CHIP  = 4        # gpiochip4 — Raspberry Pi 5 uniquement
_I2C_BUS_ID = 1
_MCP3_ADDR  = 0x25     # MCP23017 drivers moteurs : ENA (Port B) + DIR (Port A)

# ENA : actif bas (câblage inversé — ENA=0 → driver ON, ENA=1 → driver OFF)
_ENA_ON  = 0
_ENA_OFF = 1

# Course commune — identique pour les 4 vannes (V4 MOTOR_OUVERTURE/FERMETURE_STEPS)
_OUV_STEPS = 3_830
_FER_STEPS = 4_000
_OUV_SPS   =   800.0   # vitesse croisière ouverture
_OUV_ACC   =    50.0   # vitesse départ rampe montante ouverture
_OUV_DEC   =   700.0   # vitesse fin rampe descendante ouverture
_FER_SPS   = 1_600.0
_FER_ACC   =   600.0
_FER_DEC   = 1_200.0

# Timing bas-niveau (V4 MOTOR_MIN_PULSE_US, MOTOR_ENA_SETTLE_MS)
_MIN_PULSE_US      =  50   # µs — demi-impulsion minimale
_ENA_SETTLE_MS     =   5   # ms — délai ENA → premier pas

# Profil rampe (V4 MOTOR_RAMP_ACCEL/DECEL_TIME_S)
_RAMP_ACCEL_TIME_S = 2.0
_RAMP_DECEL_TIME_S = 0.5

# MCP23017 registres (BANK=0 — mode par défaut)
_REG_IOCON  = 0x0A
_REG_IODIRA = 0x00
_REG_IODIRB = 0x01
_REG_OLATA  = 0x14
_REG_OLATB  = 0x15


# ============================================================
# Définition des vannes
# ============================================================

class ValveDef(NamedTuple):
    """Définition hardware d'une vanne classique."""
    name:      str   # nom métier (V4 MOTOR_NAME_TO_ID)
    bcm:       int   # GPIO BCM (PUL)
    ena_pin:   int   # MCP3 Port B, pin Bn  (ENA = ID driver − 1)
    dir_pin:   int   # MCP3 Port A, pin An  (DIR = 8 − ID driver)
    driver_id: int   # ID driver 1..8 — info pour le câblage physique


# 4 vannes classiques — ordre d'activation dans le cycle de rodage
#
#  Câblage : connecter le câble PUL de chaque driver selon driver_id.
#  +--------------+-----------+---------+---------+---------+
#  | Nom          | Driver ID | GPIO BCM | ENA MCP3| DIR MCP3|
#  +--------------+-----------+---------+---------+---------+
#  | POMPE        |     8     |   BCM 25 |   B7    |   A0    |
#  | RETOUR       |     1     |   BCM 17 |   B0    |   A7    |
#  | CUVE_TRAVAIL |     4     |   BCM  5 |   B3    |   A4    |
#  | EAU_PROPRE   |     7     |   BCM 24 |   B6    |   A1    |
#  +--------------+-----------+---------+---------+---------+
VALVES: list = [
    ValveDef("POMPE",        bcm=25, ena_pin=7, dir_pin=0, driver_id=8),
    ValveDef("RETOUR",       bcm=17, ena_pin=0, dir_pin=7, driver_id=1),
    ValveDef("CUVE_TRAVAIL", bcm= 5, ena_pin=3, dir_pin=4, driver_id=4),
    ValveDef("EAU_PROPRE",   bcm=24, ena_pin=6, dir_pin=1, driver_id=7),
]


# ============================================================
# RodageDriver
# ============================================================

class RodageDriver:
    """
    Contrôleur pour les 4 vannes du rodage industriel.

    Inspiré de V4/libs/moteur.py et V4/libs/io_board.py.
    Standalone — aucun import depuis V4/.

    Usage :
        with RodageDriver() as drv:
            for valve in VALVES:
                drv.move_valve(valve, "fermeture")
                drv.move_valve(valve, "ouverture")
            drv.disable_all()
    """

    def __init__(self) -> None:
        self._chip: Optional[int] = None
        self._bus:  Optional[SMBus] = None
        self._olat_a = 0x00   # cache latch MCP3 Port A (DIR)
        self._olat_b = 0xFF   # cache latch MCP3 Port B (ENA) — tout OFF (actif bas)

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
            for v in VALVES:
                lgpio.gpio_claim_output(chip, v.bcm, 0)
        except Exception as exc:
            lgpio.gpiochip_close(chip)
            raise RuntimeError(f"Claim GPIO échoué: {exc}") from exc

        try:
            bus = SMBus(_I2C_BUS_ID)
        except Exception as exc:
            for v in VALVES:
                try:
                    lgpio.gpio_free(chip, v.bcm)
                except Exception:
                    pass
            lgpio.gpiochip_close(chip)
            raise RuntimeError(
                f"Impossible d'ouvrir I2C bus {_I2C_BUS_ID}: {exc}"
            ) from exc

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
        for v in VALVES:
            try:
                lgpio.gpio_write(chip, v.bcm, 0)
            except Exception:
                pass
            try:
                lgpio.gpio_free(chip, v.bcm)
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
        """Désactive tous les drivers (état sûr — ENA_OFF=1 actif bas)."""
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

    def move_valve(self, valve: ValveDef, direction: str) -> None:
        """
        Course complète d'une vanne avec profil rampe.

        Args:
            valve     : ValveDef (depuis VALVES)
            direction : 'ouverture' ou 'fermeture'
        """
        ouv = direction.strip().lower().startswith("o")
        self._set_dir(valve.dir_pin, ouv)
        self._set_ena(valve.ena_pin, _ENA_ON)
        time.sleep(_ENA_SETTLE_MS / 1000.0)
        if ouv:
            self._move_ramp(valve.bcm, _OUV_STEPS, _OUV_SPS, _OUV_ACC, _OUV_DEC)
        else:
            self._move_ramp(valve.bcm, _FER_STEPS, _FER_SPS, _FER_ACC, _FER_DEC)
