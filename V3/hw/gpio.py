# hw/gpio.py
# -*- coding: utf-8 -*-
"""
Wrapper UNIQUE autour de lgpio (Raspberry Pi 5).

Objectifs:
- Une seule lib GPIO dans tout le projet: lgpio
- API simple, stable, sans sur-architecture
- Gestion propre: open/close du chip, claim input/output, write/read
- Support callbacks (alerts) pour débitmètre, boutons, etc.
- Options anti-bruit si disponibles (glitch filter / debounce au niveau lgpio)

Usage typique (dans un device, pas dans main à terme):
    from hw.gpio import open_chip, close_chip, setup_output, write

    h = open_chip(0)
    setup_output(h, 20, initial=0)
    write(h, 20, 1)
    close_chip(h)

Note:
- lgpio gère le GPIO chip via un "handle" (int).
- On conserve les références des callbacks pour éviter qu'ils soient GC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Literal, Any

import lgpio


Edge = Literal["rising", "falling", "both"]
Pull = Literal["off", "up", "down"]


@dataclass
class GpioChip:
    """Handle lgpio + stockage des callbacks pour éviter le garbage collection."""
    chip: int
    handle: int
    _callbacks: Dict[int, Any] = field(default_factory=dict)  # gpio -> lgpio.callback object


# ---------------------------
# Ouverture / fermeture chip
# ---------------------------

def open_chip(chip: int = 0) -> GpioChip:
    """
    Ouvre gpiochip (par défaut 0) et retourne un handle.
    """
    h = lgpio.gpiochip_open(int(chip))
    if h < 0:
        raise RuntimeError(f"Impossible d'ouvrir gpiochip {chip} (handle={h})")
    return GpioChip(chip=int(chip), handle=h)


def close_chip(g: GpioChip) -> None:
    """
    Ferme le gpiochip. Libère aussi les callbacks connus.
    """
    # Stop callbacks (si existants)
    for gpio, cb in list(g._callbacks.items()):
        try:
            cb.cancel()
        except Exception:
            pass
        g._callbacks.pop(gpio, None)

    lgpio.gpiochip_close(g.handle)


# ---------------------------
# Configuration des broches
# ---------------------------

def setup_output(g: GpioChip, gpio: int, initial: int = 0) -> None:
    """
    Configure un GPIO en sortie, avec niveau initial (0/1).
    """
    gpio = int(gpio)
    initial = 1 if int(initial) else 0
    lgpio.gpio_claim_output(g.handle, gpio, initial)


def setup_input(g: GpioChip, gpio: int, pull: Pull = "up") -> None:
    """
    Configure un GPIO en entrée + pull-up/down si supporté.
    pull: "up" | "down" | "off"
    """
    gpio = int(gpio)
    lgpio.gpio_claim_input(g.handle, gpio)
    _set_pull(g, gpio, pull)


def free_gpio(g: GpioChip, gpio: int) -> None:
    """
    Libère un GPIO (utile si tu veux re-claim proprement).
    """
    gpio = int(gpio)
    # Annule callback si présent
    if gpio in g._callbacks:
        try:
            g._callbacks[gpio].cancel()
        except Exception:
            pass
        g._callbacks.pop(gpio, None)

    lgpio.gpio_free(g.handle, gpio)


def _set_pull(g: GpioChip, gpio: int, pull: Pull) -> None:
    pud = {
        "off": lgpio.SET_PULL_NONE,
        "down": lgpio.SET_PULL_DOWN,
        "up": lgpio.SET_PULL_UP,
    }[pull]
    try:
        lgpio.gpio_set_pull_up_down(g.handle, int(gpio), pud)
    except Exception as e:
        # Sur certaines configs, l'appel peut échouer (droits / état pin).
        raise RuntimeError(f"Impossible de configurer pull={pull} sur GPIO{gpio}: {e}") from e


# ---------------------------
# Lecture / écriture
# ---------------------------

def write(g: GpioChip, gpio: int, level: int) -> None:
    """
    Ecrit un niveau (0/1) sur une sortie.
    """
    gpio = int(gpio)
    level = 1 if int(level) else 0
    lgpio.gpio_write(g.handle, gpio, level)


def read(g: GpioChip, gpio: int) -> int:
    """
    Lit un niveau (0/1) sur une entrée/sortie.
    """
    gpio = int(gpio)
    return int(lgpio.gpio_read(g.handle, gpio))


# ---------------------------
# Callbacks / Alerts
# ---------------------------

def set_alert(
    g: GpioChip,
    gpio: int,
    edge: Edge,
    callback: Callable[[int, int, int], None],
    *,
    glitch_filter_us: int = 0,
    debounce_us: int = 0,
) -> None:
    """
    Active une alert (callback) sur un GPIO.

    callback signature: callback(gpio, level, tick)
      - gpio : numéro BCM
      - level: 0/1 (ou 2 selon certains événements)
      - tick : timestamp µs (source lgpio)

    Paramètres anti-bruit (si supportés par lgpio):
    - glitch_filter_us : ignore les pulses plus courts que ce temps (µs)
    - debounce_us      : regroupe les transitions rapides (µs)

    IMPORTANT:
    - Conserve la référence callback côté module (on stocke l'objet lgpio.callback)
      pour éviter que Python le garbage-collect.
    """
    gpio = int(gpio)
    edge_flag = {
        "rising": lgpio.RISING_EDGE,
        "falling": lgpio.FALLING_EDGE,
        "both": lgpio.BOTH_EDGES,
    }[edge]

    # Claim alert
    lgpio.gpio_claim_alert(g.handle, gpio, edge_flag)

    # Filtres si disponibles (selon version lgpio)
    if glitch_filter_us and glitch_filter_us > 0:
        try:
            lgpio.gpio_set_glitch_filter(g.handle, gpio, int(glitch_filter_us))
        except AttributeError:
            pass  # fonction non dispo -> ignore
        except Exception as e:
            raise RuntimeError(f"Erreur glitch_filter GPIO{gpio}: {e}") from e

    if debounce_us and debounce_us > 0:
        try:
            lgpio.gpio_set_debounce(g.handle, gpio, int(debounce_us))
        except AttributeError:
            pass
        except Exception as e:
            raise RuntimeError(f"Erreur debounce GPIO{gpio}: {e}") from e

    # Crée callback et stocke-le
    cb_obj = lgpio.callback(g.handle, gpio, edge_flag, callback)
    g._callbacks[gpio] = cb_obj


def clear_alert(g: GpioChip, gpio: int) -> None:
    """
    Désactive une alert sur un GPIO (annule callback + free pin).
    """
    free_gpio(g, gpio)
