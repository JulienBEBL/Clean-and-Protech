"""
fake_lgpio.py — Faux module lgpio pour simuler la VIC sur PC (V5).

Remplace `lgpio` dans sys.modules AVANT tout import de libs.* :

    from tests.sim.fake_lgpio import install, VICPhysique
    phys = install(travel_steps=500)

Chaque gpio_write est journalisé. Un modèle physique de la VIC est branché sur
les broches STEP / DIR / ENA :
    - deux piges rigides à 0 et `travel_steps` (course réelle, réglable) ;
    - position de départ quelconque (inconnue du programme) ;
    - un front montant de STEP avec ENA actif déplace la VIC d'un pas dans le
      sens de DIR, sauf contre une pige : le pas est alors compté « forcé » ;
    - avec ENA inactif, `push_water()` peut faire tourner la VIC (driver libre).
"""

from __future__ import annotations

import sys
import types

import config


class VICPhysique:
    def __init__(self, travel_steps: int = 500, start: int = 250) -> None:
        self.travel = int(travel_steps)
        self.pos = int(start)            # position physique réelle (pas)
        self.levels: dict[int, int] = {}
        self.writes: list[tuple[int, int]] = []
        self.steps_ok = 0
        self.steps_forced = 0            # pas commandés contre une pige
        self.forced_at_0 = 0
        self.forced_at_travel = 0
        self.ena_toggles = 0             # passages actif → inactif
        self.steps_while_disabled = 0

    # --- état ---
    @property
    def ena_active(self) -> bool:
        return self.levels.get(config.VIC_ENA_GPIO, config.VIC_ENA_INACTIVE_LEVEL) == config.VIC_ENA_ACTIVE_LEVEL

    def reset_counters(self) -> None:
        self.steps_ok = self.steps_forced = self.forced_at_0 = self.forced_at_travel = 0
        self.ena_toggles = self.steps_while_disabled = 0

    def push_water(self, delta: int) -> None:
        """L'eau fait tourner la VIC — seulement si le driver est libre."""
        if not self.ena_active:
            self.pos = max(0, min(self.travel, self.pos + int(delta)))

    # --- câblage ---
    def write(self, gpio: int, level: int) -> None:
        prev = self.levels.get(gpio)
        self.levels[gpio] = int(level)
        self.writes.append((gpio, int(level)))
        if gpio == config.VIC_ENA_GPIO:
            if prev == config.VIC_ENA_ACTIVE_LEVEL and level == config.VIC_ENA_INACTIVE_LEVEL:
                self.ena_toggles += 1
        elif gpio == config.VIC_STEP_GPIO and prev == 0 and level == 1:
            self._on_step()

    def _on_step(self) -> None:
        if not self.ena_active:
            self.steps_while_disabled += 1
            return
        up = self.levels.get(config.VIC_DIR_GPIO, 0) == config.VIC_DIR_OUVERTURE
        if up and self.pos >= self.travel:
            self.steps_forced += 1
            self.forced_at_travel += 1
        elif not up and self.pos <= 0:
            self.steps_forced += 1
            self.forced_at_0 += 1
        else:
            self.pos += 1 if up else -1
            self.steps_ok += 1


def install(travel_steps: int = 500, start: int = 250) -> VICPhysique:
    phys = VICPhysique(travel_steps, start)
    m = types.ModuleType("lgpio")
    m.FALLING_EDGE = 1
    m.RISING_EDGE = 0
    m.BOTH_EDGES = 2
    m.gpiochip_open = lambda idx: 0
    m.gpiochip_close = lambda h: 0
    m.gpio_claim_output = lambda h, g, lvl=0, *a: phys.write(g, lvl) or 0
    m.gpio_claim_input = lambda h, g, *a: 0
    m.gpio_claim_alert = lambda *a: 0
    m.gpio_free = lambda h, g: 0
    m.gpio_write = lambda h, g, lvl: phys.write(g, lvl) or 0
    m.gpio_read = lambda h, g: phys.levels.get(g, 0)
    m.gpio_set_debounce = lambda *a: 0
    m.gpio_set_glitch_filter = lambda *a: 0
    m.tx_pwm = lambda *a: 0
    m.callback = lambda *a, **k: types.SimpleNamespace(cancel=lambda: None)
    m._phys = phys
    sys.modules["lgpio"] = m
    return phys


def set_physique(phys: VICPhysique) -> None:
    """Remplace le modèle physique branché sur le faux lgpio (nouveau scénario)."""
    m = sys.modules["lgpio"]
    m._phys = phys
    m.gpio_claim_output = lambda h, g, lvl=0, *a: phys.write(g, lvl) or 0
    m.gpio_write = lambda h, g, lvl: phys.write(g, lvl) or 0
    m.gpio_read = lambda h, g: phys.levels.get(g, 0)
