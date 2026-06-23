"""
programs.py — Définition des 5 programmes de Clean & Protech V5.

Chaque programme expose 4 méthodes :
    start(ctx)               — met les vannes dans l'état requis, démarre pompe / air / VIC
    stop(ctx)                — arrête pompe et air uniquement, vannes et VIC laissées en place
    tick(ctx) -> bool        — appelée à ~10 Hz ; True=continuer, False=sécurité débit (arrêt forcé)
    lcd_info(ctx, elapsed_s) — retourne 4 lignes de 20 chars pour le LCD en état RUNNING

Vannes en V5 :
    4 vannes relais US Solid (actif haut, contact NO) : POT_A_BOUE, EGOUTS, CUVE_TRAVAIL, EAU_PROPRE
    Les vannes RETOUR, DEPART et POMPE-stepper (V4) ont été supprimées.
    La POMPE est un relais séparé piloté par ctx.relays.set_pompe_on/off().

Comportement des vannes :
    start() : ouvre les vannes requises ET ferme les vannes non requises.
              Les vannes déjà dans le bon état ne sont pas re-commandées.
    stop()  : coupe pompe relay + air relay uniquement.
              Vannes et VIC restent dans leur état courant.

Sécurité débit (PRG2, PRG4, PRG5) :
    Si le débit reste sous FLOW_SAFETY_MIN_LPM pendant FLOW_SAFETY_TIMEOUT_S,
    une procédure de relance pompe est déclenchée (FLOW_SAFETY_RESTART_COUNT cycles).
    Si le débit revient à la normale : tick() retourne True, le programme continue.
    Si toutes les tentatives échouent : tick() retourne False → arrêt forcé.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import config
from logger import log

if TYPE_CHECKING:
    from libs.vic import VICController
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

    valve_state : état courant de chaque vanne-relais (True=ouverte).
                  Initialisé à False après homing (relais GPIO LOW par défaut).
    vic_steps   : position absolue VIC en pas (0=DEPART, 50=NEUTRE, 100=RETOUR).
                  Initialisé à 50 (NEUTRE) après homing.
    """
    vic:   "VICController"
    relays: "Relays"
    io:    "IOBoard"
    flow:  "FlowMeter"
    valve_state: dict[str, bool] = field(default_factory=lambda: {
        k: False for k in ("POT_A_BOUE", "EGOUTS", "CUVE_TRAVAIL", "EAU_PROPRE")
    })
    vic_steps: int = 50  # NEUTRE après homing


# ============================================================
# Helpers — vannes relais
# ============================================================

_ALL_VALVES: tuple[str, ...] = ("POT_A_BOUE", "EGOUTS", "CUVE_TRAVAIL", "EAU_PROPRE")


def _open_valve(ctx: MachineContext, name: str) -> None:
    """Ouvre une vanne-relais si elle n'est pas déjà ouverte."""
    if ctx.valve_state.get(name, False):
        return
    ctx.relays.open_valve(name)
    ctx.valve_state[name] = True
    log.info(f"Vanne {name} → ouverte")


def _close_valve(ctx: MachineContext, name: str) -> None:
    """Ferme une vanne-relais si elle n'est pas déjà fermée."""
    if not ctx.valve_state.get(name, False):
        return
    ctx.relays.close_valve(name)
    ctx.valve_state[name] = False
    log.info(f"Vanne {name} → fermée")


def _set_valves(ctx: MachineContext, open_valves: tuple[str, ...]) -> None:
    """
    Met toutes les vannes dans l'état requis par le programme.
    Ouvre les vannes de open_valves, ferme toutes les autres.
    Ne commande que les vannes dont l'état diffère de la cible.
    """
    open_set = set(open_valves)
    for v in _ALL_VALVES:
        if v in open_set:
            _open_valve(ctx, v)
        else:
            _close_valve(ctx, v)


# ============================================================
# Helpers — VIC
# ============================================================

def _move_vic(ctx: MachineContext, target_steps: int) -> None:
    """
    Déplace la VIC vers la position cible en pas (delta).
    No-op si déjà à la position cible.
    """
    ctx.vic.move_to(target_steps)   # move_to() logue et est no-op si déjà en place
    ctx.vic_steps = target_steps


# ============================================================
# Helpers — AIR PRG5
# ============================================================

def _air_cycle_times(mode: int) -> tuple[float, float]:
    """Retourne (on_s, off_s) pour un mode AIR PRG5 (1=faible, 2=moyen)."""
    if mode == 1:
        return config.PRG5_AIR_FAIBLE_ON_S, config.PRG5_AIR_FAIBLE_OFF_S
    if mode == 2:
        return config.PRG5_AIR_MOYEN_ON_S, config.PRG5_AIR_MOYEN_OFF_S
    return 0.0, 0.0


# ============================================================
# Helpers — affichage
# ============================================================

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
# Sécurité débit
# ============================================================

def _pump_restart(ctx: MachineContext) -> bool:
    """
    Procédure de relance pompe après débit insuffisant.
    BLOQUANTE : N cycles pompe OFF→pause→ON→pause→vérification.

    Retourne True si le débit revient à la normale, False si échec total.
    """
    n     = config.FLOW_SAFETY_RESTART_COUNT
    pause = config.FLOW_SAFETY_RESTART_PAUSE_S
    for attempt in range(1, n + 1):
        log.warning(f"Sécurité débit — relance pompe {attempt}/{n}")
        ctx.relays.set_pompe_off()
        time.sleep(pause)
        ctx.relays.set_pompe_on()
        time.sleep(pause)
        lpm = ctx.flow.flow_lpm()
        if lpm >= config.FLOW_SAFETY_MIN_LPM:
            log.info(f"Sécurité débit — relance réussie ({lpm:.1f} L/min)")
            return True
    log.error(f"Sécurité débit — {n} relances sans succès → arrêt forcé")
    return False


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
    def tick(self, ctx: MachineContext) -> bool:
        """
        Appelée à ~10 Hz pendant l'exécution.
        Retourne True pour continuer, False pour arrêt d'urgence (sécurité débit).
        """

    @abstractmethod
    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        """4 chaînes de 20 chars pour l'affichage LCD en état RUNNING."""


# ============================================================
# PRG1 — Première vidange
# ============================================================

class Prg1(ProgramBase):
    """
    Remplissage de la cuve de travail avec l'eau sale de l'installation.

    Vannes  : POT_A_BOUE ouverte. Reste fermé.
    VIC     : DEPART (0 pas).
    Pompe   : OFF.
    AIR     : cycle automatique ON_S / OFF_S.
    Stop    : coupe l'air uniquement. Vannes et VIC laissées en place.
    """

    id        = 1
    name      = "PREM.VIDANGE"
    led_index = 1

    _OPEN_VALVES = ("POT_A_BOUE",)

    def __init__(self) -> None:
        self._air_on: bool        = False
        self._air_deadline: float = 0.0
        self._log_deadline: float = 0.0

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG1 — démarrage")
        ctx.relays.set_pompe_off()  # assure pompe OFF (pas de cycle pompe en PRG1)
        _set_valves(ctx, self._OPEN_VALVES)
        _move_vic(ctx, config.VIC_DEPART_STEPS)
        ctx.relays.set_air_on()
        self._air_on       = True
        self._air_deadline  = time.monotonic() + config.PRG1_AIR_ON_S
        self._log_deadline  = time.monotonic() + 10.0

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG1 — arrêt")
        ctx.relays.set_air_off()
        log.info(f"PRG1 — Volume total utilisé : {ctx.flow.total_liters():.2f} L")

    def tick(self, ctx: MachineContext) -> bool:
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
        if now >= self._log_deadline:
            log.info(f"Debit instantane : {ctx.flow.flow_lpm():.1f} L/min")
            self._log_deadline = now + 10.0
        return True

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        air_str = " ON " if self._air_on else "OFF "
        return (
            _pad(f"PRG1 {self.name}"),
            _pad(f"VIC:A/{_vic_label(ctx.vic_steps)}  AIR:{air_str}"),
            _pad(""),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# PRG2 — Vidange Cuve Travail
# ============================================================

class Prg2(ProgramBase):
    """
    Vidange de la cuve de travail (eau sale) dans les égouts.

    Vannes  : CUVE_TRAVAIL, EGOUTS ouvertes. Reste fermé.
    VIC     : NEUTRE (50 pas).
    Pompe   : ON.
    AIR     : OFF.
    Stop    : coupe la pompe uniquement. Vannes et VIC laissées en place.
    Sécurité débit active.
    """

    id        = 2
    name      = "VIDANGE CUVE"
    led_index = 2

    _OPEN_VALVES = ("CUVE_TRAVAIL", "EGOUTS")

    def __init__(self) -> None:
        self._log_deadline: float           = 0.0
        self._flow_low_since: Optional[float] = None

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG2 — démarrage")
        _set_valves(ctx, self._OPEN_VALVES)
        _move_vic(ctx, config.VIC_NEUTRE_STEPS)
        ctx.relays.set_pompe_on()
        self._log_deadline   = time.monotonic() + 10.0
        self._flow_low_since = None

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG2 — arrêt")
        ctx.relays.set_pompe_off()
        log.info(f"PRG2 — Volume total utilisé : {ctx.flow.total_liters():.2f} L")

    def tick(self, ctx: MachineContext) -> bool:
        now = time.monotonic()

        if now >= self._log_deadline:
            log.info(f"Debit instantane : {ctx.flow.flow_lpm():.1f} L/min")
            self._log_deadline = now + 10.0

        # Sécurité débit
        lpm = ctx.flow.flow_lpm()
        if lpm < config.FLOW_SAFETY_MIN_LPM:
            if self._flow_low_since is None:
                self._flow_low_since = now
            elif now - self._flow_low_since >= config.FLOW_SAFETY_TIMEOUT_S:
                log.warning(
                    f"PRG2 — Débit insuffisant depuis {config.FLOW_SAFETY_TIMEOUT_S:.0f}s "
                    f"({lpm:.1f} L/min < {config.FLOW_SAFETY_MIN_LPM} L/min)"
                )
                if not _pump_restart(ctx):
                    return False
                self._flow_low_since = None
        else:
            self._flow_low_since = None

        return True

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        flow = ctx.flow.flow_lpm()
        return (
            _pad(f"PRG2 {self.name}"),
            _pad(f"VIC:A/{_vic_label(ctx.vic_steps)}  POMPE: ON"),
            _pad(f"Debit:{flow:6.1f} L/min"),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# PRG3 — Séchage
# ============================================================

class Prg3(ProgramBase):
    """
    Séchage de l'installation par injection d'air comprimé.

    Vannes  : toutes fermées au départ.
              EGOUTS : cycle non-bloquant relay (démarre fermé, puis ouv/fer alternée).
    VIC     : DEPART (0 pas).
    Pompe   : OFF.
    AIR     : cycle automatique ON_S / OFF_S (indépendant du cycle EGOUTS).
    Stop    : coupe l'air uniquement. Vannes et VIC laissées en place.

    Différence V4→V5 : EGOUTS géré par relais GPIO (non-bloquant).
                        DEPART et RETOUR supprimés.
    """

    id        = 3
    name      = "SECHAGE"
    led_index = 3

    # EGOUTS exclu : démarre fermé, géré par le cycle dans tick()
    _OPEN_VALVES: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._air_on: bool           = False
        self._air_deadline: float     = 0.0
        self._egouts_open: bool      = False
        self._egouts_deadline: float  = 0.0
        self._log_deadline: float     = 0.0

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG3 — démarrage")
        ctx.relays.set_pompe_off()
        _set_valves(ctx, self._OPEN_VALVES)   # ferme EGOUTS si ouvert
        _move_vic(ctx, config.VIC_DEPART_STEPS)
        # EGOUTS démarre fermé
        self._egouts_open     = False
        self._egouts_deadline = time.monotonic() + config.PRG3_EGOUTS_CLOSED_S
        # AIR démarre ON
        ctx.relays.set_air_on()
        self._air_on       = True
        self._air_deadline  = time.monotonic() + config.PRG3_AIR_ON_S
        self._log_deadline  = time.monotonic() + 10.0

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG3 — arrêt")
        ctx.relays.set_air_off()
        log.info(f"PRG3 — Volume total utilisé : {ctx.flow.total_liters():.2f} L")

    def tick(self, ctx: MachineContext) -> bool:
        now = time.monotonic()

        # Cycle AIR (non-bloquant — commande relay)
        if now >= self._air_deadline:
            if self._air_on:
                ctx.relays.set_air_off()
                self._air_on      = False
                self._air_deadline = now + config.PRG3_AIR_OFF_S
            else:
                ctx.relays.set_air_on()
                self._air_on      = True
                self._air_deadline = now + config.PRG3_AIR_ON_S

        # Cycle EGOUTS — non-bloquant (relay, pas de moteur)
        now = time.monotonic()
        if now >= self._egouts_deadline:
            if self._egouts_open:
                ctx.relays.close_valve("EGOUTS")
                ctx.valve_state["EGOUTS"] = False
                self._egouts_open     = False
                self._egouts_deadline = now + config.PRG3_EGOUTS_CLOSED_S
                log.info("PRG3 — EGOUTS fermé")
            else:
                ctx.relays.open_valve("EGOUTS")
                ctx.valve_state["EGOUTS"] = True
                self._egouts_open     = True
                self._egouts_deadline = now + config.PRG3_EGOUTS_OPEN_S
                log.info("PRG3 — EGOUTS ouvert")

        if now >= self._log_deadline:
            log.info(f"Debit instantane : {ctx.flow.flow_lpm():.1f} L/min")
            self._log_deadline = now + 10.0

        return True

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        air_str = " ON " if self._air_on else "OFF "
        eg_str  = "OUVERT" if self._egouts_open else "FERME "
        return (
            _pad(f"PRG3 {self.name}"),
            _pad(f"VIC:A/{_vic_label(ctx.vic_steps)}  AIR:{air_str}"),
            _pad(f"EGOUTS:   {eg_str}"),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# PRG4 — Remplissage Cuve Travail
# ============================================================

class Prg4(ProgramBase):
    """
    Remplissage de la cuve de travail avec de l'eau propre via le pot à boue.

    Vannes  : EAU_PROPRE, POT_A_BOUE ouvertes. Reste fermé.
    VIC     : NEUTRE (50 pas).
    Pompe   : ON.
    AIR     : OFF.
    Stop    : coupe la pompe uniquement. Vannes et VIC laissées en place.
    Sécurité débit active.
    """

    id        = 4
    name      = "REMPLISSAGE"
    led_index = 4

    _OPEN_VALVES = ("EAU_PROPRE", "POT_A_BOUE")

    def __init__(self) -> None:
        self._log_deadline: float           = 0.0
        self._flow_low_since: Optional[float] = None

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG4 — démarrage")
        _set_valves(ctx, self._OPEN_VALVES)
        _move_vic(ctx, config.VIC_NEUTRE_STEPS)
        ctx.relays.set_pompe_on()
        self._log_deadline   = time.monotonic() + 10.0
        self._flow_low_since = None

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG4 — arrêt")
        ctx.relays.set_pompe_off()
        log.info(f"PRG4 — Volume total utilisé : {ctx.flow.total_liters():.2f} L")

    def tick(self, ctx: MachineContext) -> bool:
        now = time.monotonic()

        if now >= self._log_deadline:
            log.info(f"Debit instantane : {ctx.flow.flow_lpm():.1f} L/min")
            self._log_deadline = now + 10.0

        # Sécurité débit
        lpm = ctx.flow.flow_lpm()
        if lpm < config.FLOW_SAFETY_MIN_LPM:
            if self._flow_low_since is None:
                self._flow_low_since = now
            elif now - self._flow_low_since >= config.FLOW_SAFETY_TIMEOUT_S:
                log.warning(
                    f"PRG4 — Débit insuffisant depuis {config.FLOW_SAFETY_TIMEOUT_S:.0f}s "
                    f"({lpm:.1f} L/min < {config.FLOW_SAFETY_MIN_LPM} L/min)"
                )
                if not _pump_restart(ctx):
                    return False
                self._flow_low_since = None
        else:
            self._flow_low_since = None

        return True

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        flow = ctx.flow.flow_lpm()
        return (
            _pad(f"PRG4 {self.name}"),
            _pad(f"VIC:A/{_vic_label(ctx.vic_steps)}  POMPE: ON"),
            _pad(f"Debit:{flow:6.1f} L/min"),
            _pad(f"Duree   {_fmt_elapsed(elapsed_s)}"),
        )


# ============================================================
# PRG5 — Désembouage
# ============================================================

class Prg5(ProgramBase):
    """
    Circuit fermé : eau cuve de travail → installation → pot à boue → retour.

    Vannes  : POT_A_BOUE, CUVE_TRAVAIL ouvertes. Reste fermé.
    VIC     : piloté par sélecteur VIC en temps réel (3 positions).
    Pompe   : ON.
    AIR     : piloté par sélecteur AIR (0=OFF, 1=faible 2s/2s, 2=moyen 4s/2s, 3=continu).
    Stop    : coupe pompe + air uniquement. Vannes et VIC laissées en place.
    Sécurité débit active.
    """

    id        = 5
    name      = "DESEMBOUAGE"
    led_index = 5

    _OPEN_VALVES = ("POT_A_BOUE", "CUVE_TRAVAIL")

    def __init__(self) -> None:
        self._air_mode: int           = 0
        self._air_on: bool            = False
        self._air_deadline: float     = 0.0
        self._vic_pos: int            = 0   # position sélecteur 1..3 (0 = aucune active)
        self._log_deadline: float     = 0.0
        self._flow_low_since: Optional[float] = None

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG5 — démarrage")
        _set_valves(ctx, self._OPEN_VALVES)
        # VIC — position initiale selon sélecteur
        vic_pos = ctx.io.read_vic_selector()
        target  = config.VIC_POSITIONS.get(vic_pos, config.VIC_DEPART_STEPS)
        _move_vic(ctx, target)
        self._vic_pos = vic_pos
        # AIR — mode initial selon sélecteur
        self._air_mode     = ctx.io.read_air_mode()
        self._air_on       = False
        self._air_deadline = 0.0
        self._apply_air_mode(ctx, self._air_mode)
        # Pompe (après les vannes)
        ctx.relays.set_pompe_on()
        self._log_deadline   = time.monotonic() + 10.0
        self._flow_low_since = None

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG5 — arrêt")
        ctx.relays.set_pompe_off()
        ctx.relays.set_air_off()
        self._air_on = False
        log.info(f"PRG5 — Volume total utilisé : {ctx.flow.total_liters():.2f} L")

    def tick(self, ctx: MachineContext) -> bool:
        now = time.monotonic()

        # VIC MANU — ajustement si le sélecteur change
        vic_pos = ctx.io.read_vic_selector()
        if vic_pos > 0 and vic_pos != self._vic_pos:
            target = config.VIC_POSITIONS[vic_pos]
            _move_vic(ctx, target)
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
            now = time.monotonic()
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

        now = time.monotonic()
        if now >= self._log_deadline:
            log.info(f"Debit instantane : {ctx.flow.flow_lpm():.1f} L/min")
            self._log_deadline = now + 10.0

        # Sécurité débit
        lpm = ctx.flow.flow_lpm()
        if lpm < config.FLOW_SAFETY_MIN_LPM:
            if self._flow_low_since is None:
                self._flow_low_since = now
            elif now - self._flow_low_since >= config.FLOW_SAFETY_TIMEOUT_S:
                log.warning(
                    f"PRG5 — Débit insuffisant depuis {config.FLOW_SAFETY_TIMEOUT_S:.0f}s "
                    f"({lpm:.1f} L/min < {config.FLOW_SAFETY_MIN_LPM} L/min)"
                )
                if not _pump_restart(ctx):
                    return False
                self._flow_low_since = None
        else:
            self._flow_low_since = None

        return True

    def _apply_air_mode(self, ctx: MachineContext, mode: int) -> None:
        """Initialise l'état AIR pour un nouveau mode (appelé au start ou sur changement)."""
        if mode == 0:
            ctx.relays.set_air_off()
            self._air_on = False
        elif mode == 3:                          # continu — ON permanent
            ctx.relays.set_air_on()
            self._air_on = True
            self._air_deadline = float("inf")
        else:                                    # 1=faible ou 2=moyen — démarre phase ON
            on_s, _ = _air_cycle_times(mode)
            ctx.relays.set_air_on()
            self._air_on = True
            self._air_deadline = time.monotonic() + on_s

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        flow = ctx.flow.flow_lpm()
        air_labels = {0: "OFF ", 1: "FAI ", 2: "MOY ", 3: "CON "}
        air_str = air_labels.get(self._air_mode, "    ")
        return (
            _pad(f"PRG5 {self.name}"),
            _pad(f"VIC:M/{_vic_label(ctx.vic_steps)}  AIR:{air_str}"),
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
