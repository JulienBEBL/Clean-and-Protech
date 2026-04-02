"""
programs.py — Définition des 5 programmes de Clean & Protech V4.

Chaque programme expose 4 méthodes :
    start(ctx)                      — met les vannes dans l'état requis, démarre pompe / air / VIC
    stop(ctx)                       — arrête pompe et air uniquement, vannes et VIC laissées en place
    tick(ctx)                       — appelée à ~10 Hz, gère cycles AIR / EGOUTS / VIC manu
    lcd_info(ctx, elapsed_s)        — retourne 4 lignes de 20 chars pour le LCD en état RUNNING

Comportement des vannes :
  - start() : ouvre les vannes requises ET ferme les vannes non requises.
              Les vannes déjà dans le bon état ne sont pas re-commandées.
  - stop()  : coupe pompe relay + air relay uniquement.
              Vannes et VIC restent dans leur état courant.

MachineContext contient tous les drivers et l'état RAM des vannes.
Cet état est initialisé après le homing (tout fermé, VIC=0) et mis à jour
à chaque mouvement de vanne — jamais persisté sur disque.

Règles :
  - Pompe relay ON uniquement après mise en place des vannes.
  - Pompe relay OFF en premier dans stop() (évite pompe contre vannes fermées).
  - VIC via move_steps() à VIC_SPEED_SPS uniquement (course différente des autres moteurs).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import config
from logger import log

if TYPE_CHECKING:
    from libs.moteur import MotorController
    from libs.relays import Relays
    from libs.io_board import IOBoard
    from libs.debitmetre import FlowMeter


# ============================================================
# MachineContext
# ============================================================

@dataclass
class MachineContext:
    """
    Conteneur partagé passé à toutes les méthodes de programme.

    valve_state : état courant de chaque vanne-moteur (True=ouverte).
                  Initialisé à False après homing. VIC exclu (suivi par vic_steps).
    vic_steps   : position absolue de la VIC en pas (0=DEPART, 50=NEUTRE, 100=RETOUR).
    """
    motors: "MotorController"
    relays: "Relays"
    io: "IOBoard"
    flow: "FlowMeter"
    valve_state: dict[str, bool] = field(default_factory=lambda: {
        k: False for k in (
            "RETOUR", "POT_A_BOUE", "CUVE_TRAVAIL",
            "EGOUTS", "DEPART", "EAU_PROPRE", "POMPE",
        )
    })
    vic_steps: int = 0  # 0 = DEPART, 50 = NEUTRE, 100 = RETOUR


# ============================================================
# Helpers — mouvements
# ============================================================

# Ensemble de toutes les vannes-moteurs (VIC exclue — gérée séparément)
_ALL_VALVES: tuple[str, ...] = (
    "RETOUR", "POT_A_BOUE", "CUVE_TRAVAIL",
    "EGOUTS", "DEPART", "EAU_PROPRE", "POMPE",
)


def _open_valve(ctx: MachineContext, name: str) -> None:
    """Ouvre une vanne-moteur si elle n'est pas déjà ouverte."""
    if ctx.valve_state.get(name, False):
        return
    ctx.motors.ouverture(name)
    ctx.valve_state[name] = True
    log.info(f"Vanne {name} → ouverte")


def _close_valve(ctx: MachineContext, name: str) -> None:
    """Ferme une vanne-moteur si elle n'est pas déjà fermée."""
    if not ctx.valve_state.get(name, False):
        return
    ctx.motors.fermeture(name)
    ctx.valve_state[name] = False
    log.info(f"Vanne {name} → fermée")


def _set_valves(ctx: MachineContext, open_valves: tuple[str, ...]) -> None:
    """
    Met toutes les vannes dans l'état requis par le programme.
    Ouvre les vannes de open_valves, ferme toutes les autres.
    Ne bouge que les vannes dont l'état diffère de la cible.
    """
    open_set = set(open_valves)
    for v in _ALL_VALVES:
        if v in open_set:
            _open_valve(ctx, v)
        else:
            _close_valve(ctx, v)


def _move_vic(ctx: MachineContext, target_steps: int) -> None:
    """
    Déplace la VIC vers la position cible en pas (delta).
    Utilise move_steps() à VIC_SPEED_SPS. No-op si déjà à la position cible.
    """
    delta = target_steps - ctx.vic_steps
    if delta == 0:
        return
    direction = "ouverture" if delta > 0 else "fermeture"
    ctx.motors.move_steps("VIC", abs(delta), direction, config.VIC_SPEED_SPS)
    ctx.vic_steps = target_steps
    log.info(f"VIC → {target_steps} pas")


def _read_vic_selector(io: "IOBoard") -> int:
    """Retourne la position active du sélecteur VIC (1..5), ou 0 si aucune."""
    for i in range(1, 6):
        if io.read_vic_active(i):
            return i
    return 0


def _air_cycle_times(mode: int) -> tuple[float, float]:
    """Retourne (on_s, off_s) pour un mode AIR PRG5 (1=faible, 2=moyen)."""
    if mode == 1:
        return config.PRG5_AIR_FAIBLE_ON_S, config.PRG5_AIR_FAIBLE_OFF_S
    if mode == 2:
        return config.PRG5_AIR_MOYEN_ON_S, config.PRG5_AIR_MOYEN_OFF_S
    return 0.0, 0.0


def _vic_label(steps: int) -> str:
    labels = {
        config.VIC_DEPART_STEPS: "DEP",
        config.VIC_NEUTRE_STEPS: "NEU",
        config.VIC_RETOUR_STEPS: "RET",
    }
    return labels.get(steps, f"{steps}p")


def _fmt_elapsed(elapsed_s: float) -> str:
    m = int(elapsed_s) // 60
    s = int(elapsed_s) % 60
    return f"{m:02d}:{s:02d}"


def _pad(s: str) -> str:
    """Tronque ou complète à 20 caractères pour le LCD."""
    return s[:20].ljust(20)


# ============================================================
# Classe de base
# ============================================================

class ProgramBase(ABC):
    """Interface commune pour les 5 programmes."""

    id: int          # 1..5
    name: str        # affiché sur LCD ligne 1
    led_index: int   # LED à allumer pendant l'exécution (1..5)

    @abstractmethod
    def start(self, ctx: MachineContext) -> None:
        """Met les vannes dans l'état requis, place la VIC, démarre pompe / air."""

    @abstractmethod
    def stop(self, ctx: MachineContext) -> None:
        """Coupe pompe relay et air relay. Vannes et VIC laissées en place."""

    @abstractmethod
    def tick(self, ctx: MachineContext) -> None:
        """Appelée à ~10 Hz pendant l'exécution. Gère cycles et surveillance."""

    @abstractmethod
    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        """4 chaînes de 20 chars pour l'affichage LCD en état RUNNING."""


# ============================================================
# PRG1 — Première vidange
# ============================================================

class Prg1(ProgramBase):
    """
    Remplissage de la cuve de travail avec l'eau sale de l'installation.

    Vannes  : RETOUR, DEPART, POT_A_BOUE ouvertes. Reste fermé.
    VIC     : DEPART (0 pas).
    Pompe   : OFF.
    AIR     : cycle automatique 3s ON / 4s OFF.
    Stop    : coupe l'air uniquement. Vannes et VIC laissées en place.
    """

    id        = 1
    name      = "PREM.VIDANGE"
    led_index = 1

    _OPEN_VALVES = ("RETOUR", "DEPART", "POT_A_BOUE")

    def __init__(self) -> None:
        self._air_on: bool        = False
        self._air_deadline: float = 0.0

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG1 — démarrage")
        ctx.relays.set_pompe_off()  # assure pompe OFF (vannes ouvertes, pas de cycle pompe)
        _set_valves(ctx, self._OPEN_VALVES)
        _move_vic(ctx, config.VIC_DEPART_STEPS)
        ctx.relays.set_air_on()
        self._air_on      = True
        self._air_deadline = time.monotonic() + config.PRG1_AIR_ON_S

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG1 — arrêt")
        ctx.relays.set_air_off()

    def tick(self, ctx: MachineContext) -> None:
        now = time.monotonic()
        if now >= self._air_deadline:
            if self._air_on:
                ctx.relays.set_air_off()
                self._air_on      = False
                self._air_deadline = now + config.PRG1_AIR_OFF_S
            else:
                ctx.relays.set_air_on()
                self._air_on      = True
                self._air_deadline = now + config.PRG1_AIR_ON_S

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        air_str = " ON " if self._air_on else "OFF "
        return (
            _pad(f"PRG1 {self.name}"),
            _pad(f"VIC:{_vic_label(ctx.vic_steps)}  AIR:{air_str}"),
            _pad(""),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# PRG2 — Vidange Cuve Travail
# ============================================================

class Prg2(ProgramBase):
    """
    Vidange de la cuve de travail (eau sale) dans les égouts.

    Vannes  : CUVE_TRAVAIL, POMPE, EGOUTS ouvertes. Reste fermé.
    VIC     : NEUTRE (50 pas).
    Pompe   : ON.
    AIR     : OFF.
    Stop    : coupe la pompe uniquement. Vannes et VIC laissées en place.
    """

    id        = 2
    name      = "VIDANGE CUVE"
    led_index = 2

    _OPEN_VALVES = ("CUVE_TRAVAIL", "POMPE", "EGOUTS")

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG2 — démarrage")
        _set_valves(ctx, self._OPEN_VALVES)
        _move_vic(ctx, config.VIC_NEUTRE_STEPS)
        ctx.relays.set_pompe_on()

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG2 — arrêt")
        ctx.relays.set_pompe_off()

    def tick(self, ctx: MachineContext) -> None:
        pass  # surveillance débit uniquement (affichage LCD)

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        flow = ctx.flow.flow_lpm()
        return (
            _pad(f"PRG2 {self.name}"),
            _pad(f"VIC:{_vic_label(ctx.vic_steps)}  POMPE: ON"),
            _pad(f"Debit:{flow:6.1f} L/min"),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# PRG3 — Séchage
# ============================================================

class Prg3(ProgramBase):
    """
    Séchage de l'installation par injection d'air comprimé.

    Vannes  : DEPART, RETOUR ouvertes. EGOUTS : cycle moteur indépendant
              (démarre fermé, puis ouverture/fermeture alternée). Reste fermé.
    VIC     : DEPART (0 pas).
    Pompe   : OFF.
    AIR     : cycle auto 4s ON / 2s OFF (indépendant du cycle EGOUTS).
    Stop    : coupe l'air uniquement. Vannes et VIC laissées en place.
    """

    id        = 3
    name      = "SECHAGE"
    led_index = 3

    # EGOUTS exclu de _OPEN_VALVES : démarre fermé, géré par le cycle dans tick()
    _OPEN_VALVES = ("DEPART", "RETOUR")

    def __init__(self) -> None:
        self._air_on: bool           = False
        self._air_deadline: float     = 0.0
        self._egouts_open: bool      = False
        self._egouts_deadline: float  = 0.0

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG3 — démarrage")
        # Pompe reste OFF
        ctx.relays.set_pompe_off()
        _set_valves(ctx, self._OPEN_VALVES)   # ferme aussi EGOUTS si ouvert
        _move_vic(ctx, config.VIC_DEPART_STEPS)
        # EGOUTS démarre fermé — initialise le timer de la première pause
        self._egouts_open     = False
        self._egouts_deadline = time.monotonic() + config.PRG3_EGOUTS_CLOSED_S
        # AIR démarre ON
        ctx.relays.set_air_on()
        self._air_on      = True
        self._air_deadline = time.monotonic() + config.PRG3_AIR_ON_S

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG3 — arrêt")
        ctx.relays.set_air_off()

    def tick(self, ctx: MachineContext) -> None:
        now = time.monotonic()

        # Cycle AIR (non bloquant — simple commande relay)
        if now >= self._air_deadline:
            if self._air_on:
                ctx.relays.set_air_off()
                self._air_on      = False
                self._air_deadline = now + config.PRG3_AIR_OFF_S
            else:
                ctx.relays.set_air_on()
                self._air_on      = True
                self._air_deadline = now + config.PRG3_AIR_ON_S

        # Cycle EGOUTS — bloquant (~4-6s) lors du mouvement moteur
        now = time.monotonic()
        if now >= self._egouts_deadline:
            if self._egouts_open:
                ctx.motors.fermeture("EGOUTS")
                ctx.valve_state["EGOUTS"] = False
                self._egouts_open     = False
                self._egouts_deadline = time.monotonic() + config.PRG3_EGOUTS_CLOSED_S
                log.info("PRG3 — EGOUTS fermé")
            else:
                ctx.motors.ouverture("EGOUTS")
                ctx.valve_state["EGOUTS"] = True
                self._egouts_open     = True
                self._egouts_deadline = time.monotonic() + config.PRG3_EGOUTS_OPEN_S
                log.info("PRG3 — EGOUTS ouvert")

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        air_str = " ON " if self._air_on else "OFF "
        eg_str  = "OUVERT" if self._egouts_open else "FERME "
        return (
            _pad(f"PRG3 {self.name}"),
            _pad(f"VIC:{_vic_label(ctx.vic_steps)}  AIR:{air_str}"),
            _pad(f"EGOUTS:   {eg_str}"),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# PRG4 — Remplissage Cuve Travail
# ============================================================

class Prg4(ProgramBase):
    """
    Remplissage de la cuve de travail avec de l'eau propre via le pot à boue.

    Vannes  : EAU_PROPRE, POT_A_BOUE, POMPE ouvertes. Reste fermé.
    VIC     : NEUTRE (50 pas).
    Pompe   : ON.
    AIR     : OFF.
    Stop    : coupe la pompe uniquement. Vannes et VIC laissées en place.
    Note    : arrêt automatique sur cuve pleine à implémenter ultérieurement.
    """

    id        = 4
    name      = "REMPLISSAGE"
    led_index = 4

    _OPEN_VALVES = ("EAU_PROPRE", "POT_A_BOUE", "POMPE")

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG4 — démarrage")
        _set_valves(ctx, self._OPEN_VALVES)
        _move_vic(ctx, config.VIC_NEUTRE_STEPS)
        ctx.relays.set_pompe_on()

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG4 — arrêt")
        ctx.relays.set_pompe_off()

    def tick(self, ctx: MachineContext) -> None:
        pass  # arrêt automatique sur cuve pleine à implémenter ultérieurement

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        flow = ctx.flow.flow_lpm()
        return (
            _pad(f"PRG4 {self.name}"),
            _pad(f"VIC:{_vic_label(ctx.vic_steps)}  POMPE: ON"),
            _pad(f"Debit:{flow:6.1f} L/min"),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# PRG5 — Désembouage
# ============================================================

class Prg5(ProgramBase):
    """
    Circuit fermé : eau cuve de travail → installation → pot à boue → retour.

    Vannes  : RETOUR, POT_A_BOUE, CUVE_TRAVAIL, POMPE, DEPART ouvertes.
              EGOUTS et EAU_PROPRE fermées.
    VIC     : piloté par sélecteur VIC en temps réel (bloquant ≤5s par mouvement).
    Pompe   : ON.
    AIR     : piloté par sélecteur AIR (0=OFF, 1=faible 2s/2s, 2=moyen 4s/4s, 3=continu).
    Stop    : coupe pompe + air uniquement. Vannes et VIC laissées en place.
    """

    id        = 5
    name      = "DESEMBOUAGE"
    led_index = 5

    _OPEN_VALVES = ("RETOUR", "POT_A_BOUE", "CUVE_TRAVAIL", "POMPE", "DEPART")

    def __init__(self) -> None:
        self._air_mode: int       = 0
        self._air_on: bool        = False
        self._air_deadline: float = 0.0
        self._vic_pos: int        = 0   # position sélecteur 1..5 (0 = aucune active)

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG5 — démarrage")
        _set_valves(ctx, self._OPEN_VALVES)
        # VIC — position initiale selon sélecteur
        vic_pos = _read_vic_selector(ctx.io)
        target  = config.VIC_POSITIONS.get(vic_pos, config.VIC_DEPART_STEPS)
        _move_vic(ctx, target)
        self._vic_pos = vic_pos
        # AIR — mode initial selon sélecteur
        self._air_mode    = ctx.io.read_air_mode()
        self._air_on      = False
        self._air_deadline = 0.0
        self._apply_air_mode(ctx, self._air_mode)
        # Pompe (après les vannes)
        ctx.relays.set_pompe_on()

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG5 — arrêt")
        ctx.relays.set_pompe_off()
        ctx.relays.set_air_off()
        self._air_on = False

    def tick(self, ctx: MachineContext) -> None:
        now = time.monotonic()

        # VIC MANU — ajustement si le sélecteur change
        vic_pos = _read_vic_selector(ctx.io)
        if vic_pos > 0 and vic_pos != self._vic_pos:
            target = config.VIC_POSITIONS[vic_pos]
            _move_vic(ctx, target)          # bloquant ≤5s
            self._vic_pos = vic_pos
            log.info(f"PRG5 — VIC pos {vic_pos} ({target} pas)")

        # AIR MANU — changement de mode
        air_mode = ctx.io.read_air_mode()
        if air_mode != self._air_mode:
            self._air_mode = air_mode
            self._apply_air_mode(ctx, air_mode)
            log.info(f"PRG5 — AIR mode {air_mode}")
        elif air_mode in (1, 2):
            # Cycle en cours
            if now >= self._air_deadline:
                if self._air_on:
                    ctx.relays.set_air_off()
                    self._air_on = False
                    _, off_s = _air_cycle_times(air_mode)
                    self._air_deadline = now + off_s
                else:
                    ctx.relays.set_air_on()
                    self._air_on = True
                    on_s, _ = _air_cycle_times(air_mode)
                    self._air_deadline = now + on_s

    def _apply_air_mode(self, ctx: MachineContext, mode: int) -> None:
        """Initialise l'état AIR pour un nouveau mode (appelé au start ou sur changement)."""
        if mode == 0:
            ctx.relays.set_air_off()
            self._air_on = False
        elif mode == 3:                         # continu — ON permanent
            ctx.relays.set_air_on()
            self._air_on = True
            self._air_deadline = float("inf")
        else:                                   # 1=faible ou 2=moyen — démarre phase ON
            on_s, _ = _air_cycle_times(mode)
            ctx.relays.set_air_on()
            self._air_on = True
            self._air_deadline = time.monotonic() + on_s

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        flow = ctx.flow.flow_lpm()
        air_labels = {0: "OFF ", 1: "FAI ", 2: "MOY ", 3: "CON "}
        air_str = air_labels.get(self._air_mode, "    ")
        vic_lbl = str(self._vic_pos) if self._vic_pos > 0 else "-"
        return (
            _pad(f"PRG5 {self.name}"),
            _pad(f"VIC:{vic_lbl}    AIR:{air_str}"),
            _pad(f"Debit:{flow:6.1f} L/min"),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# Registre des programmes
# ============================================================

PROGRAMS: dict[int, ProgramBase] = {
    1: Prg1(),
    2: Prg2(),
    3: Prg3(),
    4: Prg4(),
    5: Prg5(),
}
