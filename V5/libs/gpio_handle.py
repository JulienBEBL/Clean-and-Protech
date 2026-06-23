"""
gpio_handle.py — Handle lgpio partagé (singleton).

Un seul gpiochip est ouvert pour toute l'application.
Tous les drivers GPIO importent ce module pour obtenir le chip handle
au lieu d'ouvrir chacun leur propre connexion au gpiochip.

Cela évite les conflits de claims GPIO et centralise la gestion
du cycle de vie matériel.

Usage typique (main.py) :
    import libs.gpio_handle as gpio_handle
    gpio_handle.init()          # une seule fois au démarrage
    ...
    gpio_handle.close()         # au shutdown

Usage dans les drivers :
    import libs.gpio_handle as gpio_handle
    chip = gpio_handle.get()    # retourne le handle actif
"""

from __future__ import annotations

from typing import Optional

import config

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio est requis. Installer python3-lgpio.") from e


# ============================================================
# Exceptions
# ============================================================

class GPIOError(Exception):
    """Erreur de base du handle GPIO."""


class GPIONotInitializedError(GPIOError):
    """Levée quand get() est appelé avant init()."""


# ============================================================
# État module (singleton)
# ============================================================

_handle: Optional[int] = None
_chip_index: Optional[int] = None


# ============================================================
# API publique
# ============================================================

def init(chip_index: int = config.GPIO_CHIP) -> int:
    """
    Ouvre le gpiochip si pas encore ouvert.
    Idempotent : appels multiples sans effet.

    Args:
        chip_index: index du gpiochip (défaut : config.GPIO_CHIP = 4 sur RPi 5)

    Returns:
        chip handle (entier lgpio)

    Raises:
        GPIOError si l'ouverture échoue.
    """
    global _handle, _chip_index

    if _handle is not None:
        return _handle

    try:
        _handle = lgpio.gpiochip_open(chip_index)
        _chip_index = chip_index
    except Exception as e:
        _handle = None
        _chip_index = None
        raise GPIOError(f"Impossible d'ouvrir gpiochip{chip_index}: {e}") from e

    return _handle


def get() -> int:
    """
    Retourne le chip handle actif.

    Raises:
        GPIONotInitializedError si init() n'a pas encore été appelé.
    """
    if _handle is None:
        raise GPIONotInitializedError(
            "GPIO handle non initialisé. Appeler gpio_handle.init() d'abord."
        )
    return _handle


def is_open() -> bool:
    """Retourne True si le handle est actuellement ouvert."""
    return _handle is not None


def close() -> None:
    """
    Ferme le chip handle et libère toutes les ressources GPIO.
    À appeler une seule fois au shutdown de l'application.
    Idempotent.
    """
    global _handle, _chip_index

    if _handle is None:
        return

    try:
        lgpio.gpiochip_close(_handle)
    except Exception:
        pass
    finally:
        _handle = None
        _chip_index = None
