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

Sécurités débit — deux logiques distinctes :

    PRG2 et PRG4 — sécurité CUVE VIDE (pas de relance) :
        Ces programmes vident une cuve censée être pleine. Si le débit reste sous
        PRGx_CUVE_VIDE_MIN_LPM pendant PRGx_CUVE_VIDE_TIMEOUT_S, c'est que la cuve
        est vide : la pompe est coupée et le programme s'arrête immédiatement.
        Aucune tentative de relance — il n'y a rien à relancer.
        Un délai de garde PRGx_CUVE_VIDE_GRACE_S après start() évite que la sécurité
        se déclenche pendant la montée en pression.

    PRG5 — sécurité débit avec RELANCE pompe :
        Circuit fermé : une chute de débit peut être passagère. Si le débit reste
        sous PRG5_FLOW_MIN_LPM pendant PRG5_FLOW_TIMEOUT_S, une procédure de relance
        est déclenchée (PRG5_FLOW_RESTART_COUNT cycles).
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
    from libs.lcd2004 import LCD2004
    from libs.buzzer import Buzzer


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
    lcd: Optional["LCD2004"] = None
    bz:  Optional["Buzzer"]  = None


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

    Fermeture séquentielle : une vanne fermée à la fois, puis attente
    VALVE_CLOSE_TRAVEL_S (course mécanique) avant la vanne suivante.
    Ouverture séquentielle : une vanne ouverte à la fois, puis attente
    VALVE_OPEN_CAPACITOR_CHARGE_S (recharge condensateur) avant la vanne suivante.

    Ne commande que les vannes dont l'état diffère de la cible.
    """
    open_set = set(open_valves)

    # 1. Fermeture séquentielle — attente course mécanique après chaque relay OFF
    to_close = [v for v in _ALL_VALVES if v not in open_set and ctx.valve_state.get(v, False)]
    for v in to_close:
        _close_valve(ctx, v)
        time.sleep(config.VALVE_CLOSE_TRAVEL_S)

    # 2. Ouverture séquentielle — recharge condensateur après chaque relay ON
    to_open = [v for v in _ALL_VALVES if v in open_set and not ctx.valve_state.get(v, False)]
    for v in to_open:
        _open_valve(ctx, v)
        time.sleep(config.VALVE_OPEN_CAPACITOR_CHARGE_S)


# ============================================================
# Helpers — VIC
# ============================================================

def _move_vic(ctx: MachineContext, target_steps: int) -> None:
    """
    Déplace la VIC vers la position cible en pas (delta).
    No-op si déjà à la position cible.
    Utilisé dans stop() et tick() — position logicielle fiable à ce stade.
    """
    log.info(f"VIC move : {ctx.vic_steps} pas → {target_steps} pas ({_vic_label(target_steps)}) delta={target_steps - ctx.vic_steps:+d}")
    ctx.vic.move_to(target_steps)
    ctx.vic_steps = target_steps


def _anchor_and_move_vic(ctx: MachineContext, target_steps: int) -> None:
    """
    Mini-homing + déplacement vers cible : ancrage butée DEPART, recalage
    compteur à 0, puis move_to(target_steps).
    Garantit la position physique réelle indépendamment de l'historique.
    Utilisé uniquement dans start() — jamais dans stop() ni tick().
    """
    log.info(f"VIC anchor+move : {ctx.vic_steps} pas → {target_steps} pas ({_vic_label(target_steps)})")
    ctx.vic.anchor_depart()
    ctx.vic_steps = 0
    ctx.vic.move_to(target_steps)
    ctx.vic_steps = target_steps
    log.info(f"VIC anchor+move terminé : position {ctx.vic_steps} pas")


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
    return s[:config.LCD_COLS].ljust(config.LCD_COLS)


def _center(s: str) -> str:
    """Centre le texte sur la largeur du LCD (20 caractères)."""
    t = s[:config.LCD_COLS]
    pad = (config.LCD_COLS - len(t)) // 2
    return (" " * pad + t).ljust(config.LCD_COLS)


def _split_line(left: str, right: str) -> str:
    """
    Compose une ligne avec `left` calé à gauche et `right` calé à droite.
    Utilisé pour "durée / débit" : la valeur ne se décale pas quand
    le nombre de chiffres change (pas de scintillement à 10 Hz).
    """
    space = config.LCD_COLS - len(left) - len(right)
    if space < 0:
        return _pad(f"{left} {right}")
    return f"{left}{' ' * space}{right}"


def _fmt_flow(lpm: float) -> str:
    """Débit formaté à largeur fixe : '123 l/min', ' 45 l/min'."""
    return f"{lpm:3.0f} l/min"


def _blink(text: str, elapsed_s: float) -> str:
    """
    Consigne clignotante : texte centré une période sur deux, ligne vide sinon.

    Cadence donnée par config.LCD_BLINK_PERIOD_S (1 s allumé / 1 s éteint).
    Le rythme est dérivé de `elapsed_s` — aucun état interne à maintenir, et
    plusieurs lignes clignotantes d'un même écran restent naturellement en phase.
    """
    period = config.LCD_BLINK_PERIOD_S
    if period <= 0:
        return _center(text)
    visible = int(elapsed_s / period) % 2 == 0
    return _center(text) if visible else _center("")


def _alternate(text_a: str, text_b: str, elapsed_s: float) -> str:
    """
    Alternance de deux textes sur une même ligne, centrés.

    Chaque texte reste affiché config.LCD_ALTERNATE_PERIOD_S avant de céder
    la place à l'autre. Contrairement à _blink(), la ligne n'est jamais vide :
    elle porte toujours une information.

    Comme _blink(), le rythme est dérivé de `elapsed_s` — plusieurs lignes
    alternées d'un même écran basculent donc forcément ensemble.
    """
    period = config.LCD_ALTERNATE_PERIOD_S
    if period <= 0:
        return _center(text_a)
    first = int(elapsed_s / period) % 2 == 0
    return _center(text_a) if first else _center(text_b)


# ============================================================
# Sécurité débit — relance pompe (PRG5)
# ============================================================

def _pump_restart(
    ctx: MachineContext,
    count: int,
    pause_s: float,
    min_lpm: float,
) -> bool:
    """
    Procédure de relance pompe après débit insuffisant.
    BLOQUANTE : N cycles pompe OFF→pause→ON→pause→vérification.

    Le blocage est VOLONTAIRE : la machine doit rester 100 % automatique et
    l'opérateur ne doit pas pouvoir intervenir pendant le rétablissement.

    Args:
        count   : nombre de tentatives de relance
        pause_s : durée de chaque phase OFF puis ON
        min_lpm : seuil de débit considéré comme rétabli

    Retourne True si le débit revient à la normale, False si échec total.
    Affiche un écran LCD d'alerte pendant la procédure ; l'écran programme
    est restauré automatiquement par render_running() au retour dans la boucle.
    """
    log.warning(
        f"Sécurité débit — procédure relance ({count} tentatives, pause={pause_s:.0f}s)"
    )

    if ctx.bz is not None:
        ctx.bz.beep(repeat=3)

    if ctx.lcd is not None:
        ctx.lcd.clear()
        ctx.lcd.write_centered(1, "SECURITE DEBIT")
        ctx.lcd.write_centered(2, "Debit insuffisant")

    for attempt in range(1, count + 1):
        log.warning(f"Sécurité débit — relance pompe {attempt}/{count}")

        if ctx.lcd is not None:
            ctx.lcd.write_centered(3, f"Tentative {attempt}/{count}")
            ctx.lcd.write_centered(4, "Pompe arret...")

        ctx.relays.set_pompe_off()
        time.sleep(pause_s)

        if ctx.lcd is not None:
            ctx.lcd.write_centered(4, "Pompe relance...")

        ctx.relays.set_pompe_on()
        time.sleep(pause_s)

        lpm = ctx.flow.flow_lpm()
        if lpm >= min_lpm:
            log.info(f"Sécurité débit — relance réussie ({lpm:.1f} L/min)")
            return True

    log.error(f"Sécurité débit — {count} relances sans succès → arrêt forcé")
    return False


# ============================================================
# Sécurité cuve vide — PRG2 et PRG4 (pas de relance)
# ============================================================

def _cuve_vide_stop(ctx: MachineContext, prg_id: int, lpm: float) -> None:
    """
    Déclenchée quand le débit s'effondre sur PRG2/PRG4 : la cuve est vide.

    Coupe la pompe IMMÉDIATEMENT, avertit l'opérateur (3 beeps + écran LCD),
    puis laisse le message visible CUVE_VIDE_ALERT_TIME_S avant de rendre la main.
    Aucune tentative de relance : il n'y a plus rien à pomper.

    L'appelant (tick) doit retourner False juste après pour déclencher l'arrêt.
    """
    log.error(f"PRG{prg_id} — Cuve vide détectée ({lpm:.1f} L/min) → arrêt pompe")

    # Coupure pompe en priorité, avant tout affichage
    ctx.relays.set_pompe_off()

    if ctx.bz is not None:
        ctx.bz.beep(repeat=3)

    if ctx.lcd is not None:
        ctx.lcd.clear()
        ctx.lcd.write_centered(1, "PLUS DE DEBIT")
        ctx.lcd.write_centered(2, "Cuve vide")
        ctx.lcd.write_centered(3, f"Debit {lpm:.1f} L/min")
        ctx.lcd.write_centered(4, "Pompe arretee")
        time.sleep(config.CUVE_VIDE_ALERT_TIME_S)


def _check_cuve_vide(
    ctx: MachineContext,
    prg_id: int,
    now: float,
    grace_deadline: float,
    low_since: Optional[float],
    min_lpm: float,
    timeout_s: float,
) -> tuple[bool, Optional[float]]:
    """
    Surveillance cuve vide pour PRG2 / PRG4.

    Args:
        now            : instant courant (time.monotonic())
        grace_deadline : instant avant lequel la sécurité reste inactive
        low_since      : instant du passage sous le seuil (None si débit OK)
        min_lpm        : seuil de débit
        timeout_s      : durée continue sous le seuil avant déclenchement

    Returns:
        (continuer, nouveau_low_since)
        continuer=False → la cuve est vide, le programme doit s'arrêter.
    """
    # Délai de garde après le démarrage — évite un déclenchement pendant
    # la montée en pression, qui empêcherait la pompe de démarrer.
    if now < grace_deadline:
        return True, None

    lpm = ctx.flow.flow_lpm()

    if lpm >= min_lpm:
        return True, None

    if low_since is None:
        return True, now

    if now - low_since >= timeout_s:
        log.warning(
            f"PRG{prg_id} — Débit insuffisant depuis {timeout_s:.0f}s "
            f"({lpm:.1f} L/min < {min_lpm} L/min)"
        )
        _cuve_vide_stop(ctx, prg_id, lpm)
        return False, None

    return True, low_since


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
        _set_valves(ctx, self._OPEN_VALVES)   # charge condensateur incluse
        _anchor_and_move_vic(ctx, config.VIC_DEPART_STEPS)
        ctx.relays.set_air_on()
        self._air_on       = True
        self._air_deadline  = time.monotonic() + config.PRG1_AIR_ON_S
        self._log_deadline  = time.monotonic() + 10.0

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG1 — arrêt")
        ctx.relays.set_air_off()
        _move_vic(ctx, config.VIC_NEUTRE_STEPS)

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
        return (
            # Lignes 2 et 3 : alternance 3 s pour loger 4 informations sur 2 lignes.
            #   phase A : PREMIERE VIDANGE / 100% AUTOMATIQUE
            #   phase B : ATTENTION        / SURVEILLER CUVE 1
            _center("PROGRAMME 1"),
            _alternate("PREMIERE VIDANGE", "ATTENTION", elapsed_s),
            _alternate("100% AUTOMATIQUE", "SURVEILLER CUVE 1", elapsed_s),
            _center(f"DUREE : {_fmt_elapsed(elapsed_s)}"),
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

    Sécurité CUVE VIDE (pas de relance) : la cuve de travail est censée être
    pleine au lancement. Si le débit s'effondre, elle est vide → arrêt direct.
    Confirmation opérateur requise avant lancement (gérée par main.py).
    """

    id        = 2
    name      = "VIDANGE CUVE"
    led_index = 2

    _OPEN_VALVES = ("CUVE_TRAVAIL", "EGOUTS")

    def __init__(self) -> None:
        self._log_deadline: float             = 0.0
        self._flow_low_since: Optional[float] = None
        self._grace_deadline: float           = 0.0

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG2 — démarrage")
        _set_valves(ctx, self._OPEN_VALVES)   # charge condensateur incluse
        _anchor_and_move_vic(ctx, config.VIC_NEUTRE_STEPS)
        ctx.relays.set_pompe_on()
        now = time.monotonic()
        self._log_deadline   = now + 10.0
        self._flow_low_since = None
        # Délai de garde : la sécurité cuve vide ne s'active qu'après ce délai,
        # le temps que la pompe monte en pression.
        self._grace_deadline = now + config.PRG2_CUVE_VIDE_GRACE_S
        log.info(
            f"PRG2 — sécurité cuve vide active dans {config.PRG2_CUVE_VIDE_GRACE_S:.0f}s "
            f"(seuil {config.PRG2_CUVE_VIDE_MIN_LPM} L/min pendant "
            f"{config.PRG2_CUVE_VIDE_TIMEOUT_S:.0f}s)"
        )

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG2 — arrêt")
        ctx.relays.set_pompe_off()
        log.info(f"PRG2 — Volume total utilisé : {ctx.flow.total_liters():.2f} L")

    def tick(self, ctx: MachineContext) -> bool:
        now = time.monotonic()

        if now >= self._log_deadline:
            log.info(f"Debit instantane : {ctx.flow.flow_lpm():.1f} L/min")
            self._log_deadline = now + 10.0

        # Sécurité cuve vide — coupe la pompe et arrête, sans relance
        ok, self._flow_low_since = _check_cuve_vide(
            ctx,
            prg_id         = self.id,
            now            = now,
            grace_deadline = self._grace_deadline,
            low_since      = self._flow_low_since,
            min_lpm        = config.PRG2_CUVE_VIDE_MIN_LPM,
            timeout_s      = config.PRG2_CUVE_VIDE_TIMEOUT_S,
        )
        return ok

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        # En-tête fusionné (PRG2 + nom) pour garder les consignes en toutes lettres
        return (
            _center("PRG2 VIDANGE CUVE 1"),
            _blink("SURVEILLER CUVE 1", elapsed_s),
            _center("ALLUMER LA POMPE"),
            _center(f"DEBIT : {_fmt_flow(ctx.flow.flow_lpm())}"),
        )


# ============================================================
# PRG3 — Séchage
# ============================================================

class Prg3(ProgramBase):
    """
    Séchage de l'installation par injection d'air comprimé.

    Vannes  : toutes fermées au départ.
              EGOUTS : cycle non-bloquant relay (démarre fermé, puis ouv/fer alternée).
    VIC     : démarre en DEPART, puis **inversion automatique de sens** toutes les
              PRG3_VIC_INVERT_PERIOD_S — traversée DEPART ↔ RETOUR en overcourse.
              Objectif : inverser le sens d'injection d'air pour décoller les saletés.
    Pompe   : OFF.
    AIR     : cycle automatique ON_S / OFF_S (indépendant des autres cycles).
    Stop    : coupe l'air, ferme EGOUTS, replace la VIC en NEUTRE.

    Les trois cycles (AIR, EGOUTS, inversion VIC) sont **indépendants et
    non bloquants** : aucun n'interrompt les deux autres.

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
        self._air_deadline: float    = 0.0
        self._egouts_open: bool      = False
        self._egouts_deadline: float = 0.0
        # Cycle d'inversion VIC — état de la traversée en cours
        self._vic_moving: bool       = False
        self._vic_steps_left: int    = 0
        self._vic_to_retour: bool    = True   # sens de la prochaine traversée
        self._vic_next_start: float  = 0.0

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG3 — démarrage")
        ctx.relays.set_pompe_off()
        _set_valves(ctx, self._OPEN_VALVES)   # ferme EGOUTS si ouvert
        _anchor_and_move_vic(ctx, config.VIC_DEPART_STEPS)

        now = time.monotonic()

        # EGOUTS démarre fermé
        self._egouts_open     = False
        self._egouts_deadline = now + config.PRG3_EGOUTS_CLOSED_S

        # AIR démarre ON
        ctx.relays.set_air_on()
        self._air_on       = True
        self._air_deadline = now + config.PRG3_AIR_ON_S

        # Inversion VIC — départ depuis la butée DEPART, première traversée
        # vers RETOUR après la temporisation.
        self._vic_moving     = False
        self._vic_steps_left = 0
        self._vic_to_retour  = True
        self._vic_next_start = now + config.PRG3_VIC_INVERT_PERIOD_S
        log.info(
            f"PRG3 — inversion VIC toutes les {config.PRG3_VIC_INVERT_PERIOD_S:.0f}s "
            f"(overcourse x{config.PRG3_VIC_OVERCOURSE_FACTOR})"
        )

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG3 — arrêt")

        # 1. Air coupé en premier — avant toute manœuvre de vanne
        ctx.relays.set_air_off()
        self._air_on = False

        # 2. Traversée VIC éventuellement en cours : driver relâché proprement
        if self._vic_moving:
            ctx.vic.end_stepping()
            self._vic_moving = False
            log.info("PRG3 — traversée VIC interrompue par l'arrêt")

        # 3. Fermeture EGOUTS — commande inconditionnelle (sécurité), la course
        #    mécanique se déroule pendant le repositionnement VIC ci-dessous.
        t_close = time.monotonic()
        ctx.relays.close_valve("EGOUTS")
        ctx.valve_state["EGOUTS"] = False
        self._egouts_open = False
        log.info("PRG3 — fermeture EGOUTS commandée")

        # 4. VIC → NEUTRE : ancrage butée DEPART puis 50 pas (~15 s à 10 pas/s).
        #    Se déroule en parallèle de la course mécanique de la vanne.
        _anchor_and_move_vic(ctx, config.VIC_NEUTRE_STEPS)

        # 5. Garantie de fermeture : complète le temps de course si le
        #    repositionnement VIC a été plus rapide que VALVE_CLOSE_TRAVEL_S.
        remaining = config.VALVE_CLOSE_TRAVEL_S - (time.monotonic() - t_close)
        if remaining > 0:
            log.info(f"PRG3 — attente fin de course EGOUTS ({remaining:.1f}s)")
            time.sleep(remaining)
        log.info("PRG3 — EGOUTS fermée, VIC en NEUTRE")

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

        # Cycle inversion VIC — non-bloquant, indépendant des deux cycles ci-dessus
        self._tick_vic_invert(ctx, now)

        return True

    def _tick_vic_invert(self, ctx: MachineContext, now: float) -> None:
        """
        Fait avancer d'UN pas la traversée VIC en cours, ou déclenche la suivante.

        Non bloquant : un seul pas par appel (~0.1 s à VIC_SPEED_SPS = 10), ce qui
        laisse les cycles AIR et EGOUTS s'exécuter normalement pendant la traversée.

        Chaque traversée est faite en overcourse (PRG3_VIC_OVERCOURSE_FACTOR) pour
        garantir l'arrivée en butée mécanique ; le compteur est recalé à l'arrivée.
        """
        # --- Traversée en cours : un pas de plus ---
        if self._vic_moving:
            ctx.vic.step_once()
            self._vic_steps_left -= 1
            if self._vic_steps_left > 0:
                return

            # Butée atteinte — recalage du compteur et inversion du sens
            ctx.vic.end_stepping()
            target = config.VIC_RETOUR_STEPS if self._vic_to_retour else config.VIC_DEPART_STEPS
            ctx.vic.set_position(target)
            ctx.vic_steps = target
            self._vic_moving     = False
            self._vic_to_retour  = not self._vic_to_retour
            self._vic_next_start = now + config.PRG3_VIC_INVERT_PERIOD_S
            log.info(f"PRG3 — VIC en butée {_vic_label(target)}")
            return

        # --- À l'arrêt en butée : déclenchement de la traversée suivante ---
        if now < self._vic_next_start:
            return

        # round() et non int() : 100 * 1.15 vaut 114.99999... en flottant,
        # une troncature donnerait 114 pas au lieu des 115 attendus.
        overcourse = round(config.VIC_TOTAL_STEPS * config.PRG3_VIC_OVERCOURSE_FACTOR)
        direction  = "ouverture" if self._vic_to_retour else "fermeture"
        cible      = "RETOUR" if self._vic_to_retour else "DEPART"
        log.info(f"PRG3 — inversion VIC vers {cible} ({overcourse} pas overcourse)")
        ctx.vic.begin_stepping(direction)
        self._vic_steps_left = overcourse
        self._vic_moving     = True

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        return (
            _center("PROGRAMME 3"),
            _center("SECHAGE"),
            _center("100% AUTOMATIQUE"),
            _center(f"DUREE : {_fmt_elapsed(elapsed_s)}"),
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

    Sécurité CUVE VIDE (pas de relance) : la réserve d'eau propre est censée
    être pleine au lancement. Si le débit s'effondre, elle est vide → arrêt direct.
    Confirmation opérateur requise avant lancement (gérée par main.py).
    """

    id        = 4
    name      = "REMPLISSAGE"
    led_index = 4

    _OPEN_VALVES = ("EAU_PROPRE", "POT_A_BOUE")

    def __init__(self) -> None:
        self._log_deadline: float             = 0.0
        self._flow_low_since: Optional[float] = None
        self._grace_deadline: float           = 0.0

    def start(self, ctx: MachineContext) -> None:
        log.info("PRG4 — démarrage")
        _set_valves(ctx, self._OPEN_VALVES)   # charge condensateur incluse
        _anchor_and_move_vic(ctx, config.VIC_NEUTRE_STEPS)
        ctx.relays.set_pompe_on()
        now = time.monotonic()
        self._log_deadline   = now + 10.0
        self._flow_low_since = None
        # Délai de garde : la sécurité cuve vide ne s'active qu'après ce délai,
        # le temps que la pompe monte en pression.
        self._grace_deadline = now + config.PRG4_CUVE_VIDE_GRACE_S
        log.info(
            f"PRG4 — sécurité cuve vide active dans {config.PRG4_CUVE_VIDE_GRACE_S:.0f}s "
            f"(seuil {config.PRG4_CUVE_VIDE_MIN_LPM} L/min pendant "
            f"{config.PRG4_CUVE_VIDE_TIMEOUT_S:.0f}s)"
        )

    def stop(self, ctx: MachineContext) -> None:
        log.info("PRG4 — arrêt")
        ctx.relays.set_pompe_off()
        log.info(f"PRG4 — Volume total utilisé : {ctx.flow.total_liters():.2f} L")

    def tick(self, ctx: MachineContext) -> bool:
        now = time.monotonic()

        if now >= self._log_deadline:
            log.info(f"Debit instantane : {ctx.flow.flow_lpm():.1f} L/min")
            self._log_deadline = now + 10.0

        # Sécurité cuve vide — coupe la pompe et arrête, sans relance
        ok, self._flow_low_since = _check_cuve_vide(
            ctx,
            prg_id         = self.id,
            now            = now,
            grace_deadline = self._grace_deadline,
            low_since      = self._flow_low_since,
            min_lpm        = config.PRG4_CUVE_VIDE_MIN_LPM,
            timeout_s      = config.PRG4_CUVE_VIDE_TIMEOUT_S,
        )
        return ok

    def lcd_info(self, ctx: MachineContext, elapsed_s: float) -> tuple[str, str, str, str]:
        return (
            _center("PROGRAMME 4"),
            _center("REMPLISSAGE CUVE 1"),
            _blink("SURVEILLER CUVE 1", elapsed_s),
            _center(f"DEBIT : {_fmt_flow(ctx.flow.flow_lpm())}"),
        )


# ============================================================
# PRG5 — Désembouage
# ============================================================

class Prg5(ProgramBase):
    """
    Circuit fermé : eau cuve de travail → installation → pot à boue → retour.

    Vannes  : POT_A_BOUE, CUVE_TRAVAIL ouvertes. Reste fermé.
    VIC     : piloté par sélecteur VIC en temps réel.
    Pompe   : ON.
    AIR     : piloté par sélecteur AIR (0=OFF, 1=faible 2s/2s, 2=moyen 4s/2s, 3=continu).
    Stop    : coupe pompe + air. VIC ramenée en NEUTRE. Vannes laissées en place.

    Sécurité DÉBIT AVEC RELANCE : circuit fermé, une chute de débit peut être
    passagère → PRG5_FLOW_RESTART_COUNT tentatives de relance avant arrêt forcé.
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
        _set_valves(ctx, self._OPEN_VALVES)   # charge condensateur incluse
        # VIC — position initiale selon sélecteur
        vic_pos = ctx.io.read_vic_selector()
        target  = config.VIC_POSITIONS.get(vic_pos, config.VIC_DEPART_STEPS)
        log.info(f"PRG5 — sélecteur VIC brut={vic_pos} → cible {target} pas ({_vic_label(target)})")
        _anchor_and_move_vic(ctx, target)
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
        _move_vic(ctx, config.VIC_NEUTRE_STEPS)
        log.info(f"PRG5 — Volume total utilisé : {ctx.flow.total_liters():.2f} L")

    def tick(self, ctx: MachineContext) -> bool:
        now = time.monotonic()

        # VIC MANU — ajustement si le sélecteur change
        vic_pos = ctx.io.read_vic_selector()
        if vic_pos != self._vic_pos:
            target = config.VIC_POSITIONS[vic_pos]
            log.info(f"PRG5 tick — sélecteur VIC {self._vic_pos}→{vic_pos} : {ctx.vic_steps}→{target} pas ({_vic_label(target)})")
            _move_vic(ctx, target)
            self._vic_pos = vic_pos

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

        # Sécurité débit — avec relance pompe (circuit fermé)
        lpm = ctx.flow.flow_lpm()
        if lpm < config.PRG5_FLOW_MIN_LPM:
            if self._flow_low_since is None:
                self._flow_low_since = now
            elif now - self._flow_low_since >= config.PRG5_FLOW_TIMEOUT_S:
                log.warning(
                    f"PRG5 — Débit insuffisant depuis {config.PRG5_FLOW_TIMEOUT_S:.0f}s "
                    f"({lpm:.1f} L/min < {config.PRG5_FLOW_MIN_LPM} L/min)"
                )
                ok = _pump_restart(
                    ctx,
                    count   = config.PRG5_FLOW_RESTART_COUNT,
                    pause_s = config.PRG5_FLOW_RESTART_PAUSE_S,
                    min_lpm = config.PRG5_FLOW_MIN_LPM,
                )
                if not ok:
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
        # En-tête fusionné (PRG5 + nom) pour loger la consigne pompe en entier.
        # Ligne 4 : durée à gauche, débit à droite — largeur fixe, pas de scintillement.
        return (
            _center("PRG5 DESEMBOUAGE"),
            _blink("POMPE A L'ARRET POUR", elapsed_s),
            _blink("CHANGEMENT DE SENS", elapsed_s),
            _split_line(_fmt_elapsed(elapsed_s), _fmt_flow(ctx.flow.flow_lpm())),
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
