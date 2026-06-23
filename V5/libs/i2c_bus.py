"""
i2c_bus.py — Couche transport I2C bas-niveau.

Responsabilité unique : ouvrir /dev/i2c-N et exposer des primitives
de lecture/écriture avec retry automatique et exceptions typées.

Ne contient aucune logique de composant.

Usage :
    from libs.i2c_bus import I2CBus, I2CError

    bus = I2CBus()
    bus.open()
    bus.write_u8(0x24, 0x00, 0xFF)
    val = bus.read_u8(0x24, 0x12)
    bus.close()

    # ou avec context manager :
    with I2CBus() as bus:
        ...
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

import config

try:
    from smbus2 import SMBus  # type: ignore
except Exception:  # pragma: no cover
    try:
        from smbus import SMBus  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError(
            "smbus2 non disponible. Installer : pip install smbus2"
        ) from e


# ============================================================
# Exceptions
# ============================================================

class I2CError(Exception):
    """Erreur de base I2C."""


class I2CNotOpenError(I2CError):
    """Bus utilisé avant ouverture."""


class I2CNackError(I2CError):
    """Le device n'a pas répondu (mauvaise adresse, câblage, alimentation)."""


class I2CIOError(I2CError):
    """Erreur I/O générique après épuisement des tentatives."""


# ============================================================
# Configuration
# ============================================================

@dataclass(frozen=True)
class I2CBusConfig:
    bus_id: int = config.I2C_BUS_ID
    freq_hz: int = config.I2C_FREQ_HZ
    retries: int = config.I2C_RETRIES
    retry_delay_s: float = config.I2C_RETRY_DELAY_S


# ============================================================
# Driver
# ============================================================

class I2CBus:
    """
    Driver I2C bas-niveau (SMBus).

    Toutes les opérations lèvent I2CError (ou sous-classe) en cas d'échec.
    """

    def __init__(
        self,
        bus_id: int = config.I2C_BUS_ID,
        freq_hz: int = config.I2C_FREQ_HZ,
        retries: int = config.I2C_RETRIES,
        retry_delay_s: float = config.I2C_RETRY_DELAY_S,
    ) -> None:
        if retries < 0:
            raise ValueError("retries doit être >= 0")
        if retry_delay_s < 0:
            raise ValueError("retry_delay_s doit être >= 0")

        self.config = I2CBusConfig(
            bus_id=bus_id,
            freq_hz=freq_hz,
            retries=retries,
            retry_delay_s=retry_delay_s,
        )
        self._bus: Optional[SMBus] = None

    # ---- lifecycle ----

    def open(self) -> None:
        """Ouvre /dev/i2c-<bus_id>. Idempotent."""
        if self._bus is not None:
            return
        try:
            self._bus = SMBus(self.config.bus_id)
        except FileNotFoundError as e:
            raise I2CIOError(
                f"Bus I2C /dev/i2c-{self.config.bus_id} introuvable"
            ) from e
        except PermissionError as e:
            raise I2CIOError(
                f"Permission refusée sur /dev/i2c-{self.config.bus_id} "
                "(ajouter l'utilisateur au groupe i2c)"
            ) from e
        except Exception as e:
            raise I2CIOError(
                f"Impossible d'ouvrir le bus I2C {self.config.bus_id}: {e}"
            ) from e

    def close(self) -> None:
        """Ferme le bus. Idempotent."""
        if self._bus is not None:
            try:
                self._bus.close()
            finally:
                self._bus = None

    def __enter__(self) -> "I2CBus":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> SMBus:
        if self._bus is None:
            raise I2CNotOpenError(
                "Bus I2C non ouvert. Appeler bus.open() ou utiliser 'with I2CBus() as bus:'"
            )
        return self._bus

    # ---- retry engine ----

    def _run(self, op_name: str, addr: int, fn):
        """Exécute fn() avec retry automatique, lève I2CError en cas d'échec."""
        last_exc: Optional[Exception] = None
        attempts = self.config.retries + 1

        for i in range(attempts):
            try:
                return fn()
            except OSError as e:
                last_exc = e
                if i < attempts - 1:
                    if self.config.retry_delay_s > 0:
                        time.sleep(self.config.retry_delay_s)
                    continue
                msg = (
                    f"I2C {op_name} échoué (addr=0x{addr:02X}, bus={self.config.bus_id}) "
                    f"après {attempts} tentative(s): {e}"
                )
                if getattr(e, "errno", None) in (6, 121):  # ENXIO / EREMOTEIO
                    raise I2CNackError(msg) from e
                raise I2CIOError(msg) from e
            except Exception as e:
                last_exc = e
                break

        raise I2CIOError(
            f"I2C {op_name} échoué (addr=0x{addr:02X}, bus={self.config.bus_id}): {last_exc}"
        ) from last_exc

    # ---- primitives ----

    def write_u8(self, addr: int, reg: int, value: int) -> None:
        """Écrit 1 octet dans le registre d'un device."""
        bus = self._require_open()
        value &= 0xFF
        reg &= 0xFF
        self._run("write_u8", addr, lambda: bus.write_byte_data(addr, reg, value))

    def read_u8(self, addr: int, reg: int) -> int:
        """Lit 1 octet depuis le registre d'un device."""
        bus = self._require_open()
        reg &= 0xFF
        return int(self._run("read_u8", addr, lambda: bus.read_byte_data(addr, reg))) & 0xFF

    def write_block(self, addr: int, reg: int, data: Sequence[int]) -> None:
        """Écrit jusqu'à 32 octets dans des registres consécutifs."""
        bus = self._require_open()
        reg &= 0xFF
        payload = [int(b) & 0xFF for b in data]
        self._run("write_block", addr, lambda: bus.write_i2c_block_data(addr, reg, payload))

    def read_block(self, addr: int, reg: int, length: int) -> List[int]:
        """Lit un bloc d'octets consécutifs depuis un registre."""
        if length <= 0:
            return []
        bus = self._require_open()
        reg &= 0xFF
        return list(
            self._run("read_block", addr, lambda: bus.read_i2c_block_data(addr, reg, length))
        )

    def scan(self, start: int = 0x03, end: int = 0x77) -> List[int]:
        """
        Scan le bus I2C entre start et end.
        Retourne la liste des adresses qui répondent (ACK).
        """
        bus = self._require_open()
        found: List[int] = []
        for addr in range(start, end + 1):
            try:
                bus.read_byte(addr)
                found.append(addr)
            except OSError:
                continue
        return found
