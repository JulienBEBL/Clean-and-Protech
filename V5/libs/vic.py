"""
vic.py — Contrôleur VIC (Vanne d'Injection et de Circuit) — V5.

Driver dédié à la VIC, motorisée par un driver JK-DM860H.
En V5, les signaux STEP/DIR/ENA sont câblés directement sur GPIO RPi 5
(plus de MCP3 intermédiaire comme en V4).

Positions de la VIC (réducteur 5:1, 400 pas/tour moteur → 0.18° de VIC par pas) :
    DEPART  =   0 pas  (butée fermeture, pige)   →  0°
    NEUTRE  = 250 pas  (position milieu)         → 45°
    RETOUR  = 500 pas  (butée ouverture, pige)   → 90°

Sens de déplacement (config.py) :
    fermeture → GPIO DIR = VIC_DIR_FERMETURE (0) → vers DEPART
    ouverture → GPIO DIR = VIC_DIR_OUVERTURE (1) → vers RETOUR

ENA actif bas (DM860H) :
    VIC_ENA_ACTIVE_LEVEL   = 0 → driver actif
    VIC_ENA_INACTIVE_LEVEL = 1 → driver désactivé (état sûr)

Driver toujours actif (config.VIC_HOLD_ENABLED, depuis 2026-11-05) :
    activé au premier mouvement, désactivé uniquement par disable() / close()
    (arrêt de main.py). Le moteur tient la VIC : l'eau ne peut plus la tourner.

Position mémorisée (config.VIC_STATE_ENABLED, voir libs/vic_state.py) :
    chaque mouvement écrit « en mouvement » avant, la position après ;
    note_pump_state() marque la position « sûre » quand la pompe est arrêtée
    depuis VIC_STATE_SAFE_DELAY_S. homing() s'en sert pour l'ancrage initial.

Usage :
    import libs.gpio_handle as gpio_handle
    from libs.vic import VICController

    gpio_handle.init()
    vic = VICController()
    vic.open()
    vic.homing()           # ancrage + cycles progressifs + positionnement NEUTRE
    vic.move_to(0)         # déplace vers DEPART
    vic.move_to(250)       # déplace vers NEUTRE
    vic.close()
"""

from __future__ import annotations

import time
from typing import Optional

import config
import libs.gpio_handle as gpio_handle
from libs.vic_state import VICStateStore
from logger import log

try:
    import lgpio  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("lgpio est requis. Installer python3-lgpio.") from e


# ============================================================
# Exceptions
# ============================================================

class VICError(Exception):
    """Erreur de base du contrôleur VIC."""

class VICNotInitializedError(VICError):
    """Levée si open() n'a pas été appelé."""


# ============================================================
# Contrôleur VIC
# ============================================================

class VICController:
    """
    Contrôleur moteur pas-à-pas pour la VIC — GPIO direct RPi 5.

    Toutes les constantes hardware viennent de config.py.
    Un seul VICController est instancié par application.
    """

    def __init__(
        self,
        gpio_step: int = config.VIC_STEP_GPIO,
        gpio_dir:  int = config.VIC_DIR_GPIO,
        gpio_ena:  int = config.VIC_ENA_GPIO,
    ) -> None:
        self.gpio_step = int(gpio_step)
        self.gpio_dir  = int(gpio_dir)
        self.gpio_ena  = int(gpio_ena)

        self._chip: Optional[int] = None
        self._steps: int = 0  # position inconnue — valide uniquement après homing
        self._step_cb = None  # callback optionnel appelé après chaque pas
        self._step_sign: int = 0  # sens de la série pas-à-pas en cours (+1 / -1)
        self._enabled: bool = False      # état courant de ENA (True = driver actif)
        self._dir: Optional[str] = None  # dernière direction écrite sur DIR
        # Ancrage alterné (config.VIC_ANCHOR_ALTERNATE) : valeur fixée par homing()
        # (côté opposé à son dernier ancrage) ; True tant qu'aucun homing n'a eu lieu.
        self._next_anchor_retour: bool = True

        # Mémorisation de la position (None = fonction désactivée)
        self._store: Optional[VICStateStore] = (
            VICStateStore(config.VIC_STATE_FILE, config.VIC_TOTAL_STEPS)
            if config.VIC_STATE_ENABLED else None
        )
        self._moving: bool = False                 # mouvement en cours (persisté)
        self._safe: bool = False                   # dernière valeur « sûr » écrite
        self._quiet_since: Optional[float] = None  # VIC immobile + pompe OFF depuis

    # ---- lifecycle ----

    def open(self) -> None:
        """
        Récupère le chip handle, claim les 3 pins VIC en sortie,
        force l'état sûr (driver désactivé).
        Idempotent.
        """
        if self._chip is not None:
            return
        try:
            chip = gpio_handle.get()
            lgpio.gpio_claim_output(chip, self.gpio_step, 0)
            lgpio.gpio_claim_output(chip, self.gpio_dir,  0)
            lgpio.gpio_claim_output(chip, self.gpio_ena,  config.VIC_ENA_INACTIVE_LEVEL)
            self._chip = chip
        except Exception as e:
            self._chip = None
            raise VICError(
                f"Impossible d'initialiser la VIC "
                f"(step={self.gpio_step}, dir={self.gpio_dir}, ena={self.gpio_ena}): {e}"
            ) from e

    def close(self) -> None:
        """Désactive le driver, libère les pins. Ne ferme pas le chip handle."""
        if self._chip is None:
            return
        try:
            self._disable()
        except Exception:
            pass
        try:
            lgpio.gpio_free(self._chip, self.gpio_step)
            lgpio.gpio_free(self._chip, self.gpio_dir)
            lgpio.gpio_free(self._chip, self.gpio_ena)
        except Exception:
            pass
        finally:
            self._chip = None

    def __enter__(self) -> "VICController":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._chip is None:
            raise VICNotInitializedError(
                "VICController non initialisé. Appeler open() d'abord."
            )
        return self._chip

    # ---- contrôle driver ----
    
    def _enable(self) -> None:
        """
        Active le driver DM860H (ENA bas) s'il ne l'est pas déjà.
        Attend le délai de stabilisation uniquement à l'activation.
        """
        chip = self._require_open()
        if self._enabled:
            return
        lgpio.gpio_write(chip, self.gpio_ena, config.VIC_ENA_ACTIVE_LEVEL)
        self._enabled = True
        time.sleep(config.MOTOR_ENA_SETTLE_MS / 1000.0)

    def _disable(self) -> None:
        """Désactive le driver DM860H (ENA haut). État sûr — VIC libre."""
        chip = self._require_open()
        lgpio.gpio_write(chip, self.gpio_ena, config.VIC_ENA_INACTIVE_LEVEL)
        self._enabled = False

    def _release_after_move(self) -> None:
        """
        Fin de mouvement : driver laissé actif si VIC_HOLD_ENABLED (le moteur
        tient la VIC), désactivé sinon (ancien comportement).
        """
        if not config.VIC_HOLD_ENABLED:
            self._disable()

    def disable(self) -> None:
        """
        API publique — désactive le driver (état sûr, VIC libre).
        Réservée à l'arrêt de l'application (main.py finally, scripts de test).
        """
        if self._chip is not None:
            self._disable()

    def reset_driver(self, off_s: float, on_s: float, sleep=None) -> None:
        """
        Réarmement du driver : ENA inactif pendant off_s, puis actif, puis attente on_s.

        À appeler pompe arrêtée et JUSTE AVANT un ancrage : pendant la coupure la
        VIC est libre et le rotor peut se replacer de quelques pas ; seul un
        ancrage rétablit ensuite une position sûre. La position est marquée
        « en mouvement » pendant l'opération (coupure de courant → pas sûre).

        Args:
            off_s : durée ENA inactif (s)
            on_s  : attente après réactivation, avant le premier pas (s)
            sleep : fonction d'attente (défaut time.sleep) — permet d'animer la LED
        """
        self._require_open()
        wait = sleep if sleep is not None else time.sleep
        self._persist_moving()
        log.info(f"VIC driver — réarmement : ENA inactif {off_s:g}s puis actif {on_s:g}s")
        self._disable()
        wait(max(0.0, float(off_s)))
        self._enable()
        wait(max(0.0, float(on_s)))
        self._persist_position()
        log.info("VIC driver — réarmement terminé, driver actif")

    @property
    def enabled(self) -> bool:
        """True si le driver est actif (ENA au niveau actif)."""
        return self._enabled

    def _set_dir(self, direction: str) -> None:
        """
        Configure la broche DIR.
        direction : 'ouverture' (vers RETOUR) ou 'fermeture' (vers DEPART)
        """
        chip = self._require_open()
        d = direction.strip().lower()
        if d == "ouverture":
            lgpio.gpio_write(chip, self.gpio_dir, config.VIC_DIR_OUVERTURE)
        elif d == "fermeture":
            lgpio.gpio_write(chip, self.gpio_dir, config.VIC_DIR_FERMETURE)
        else:
            raise VICError(f"Direction invalide : '{direction}'. Valeurs : 'ouverture' / 'fermeture'")
        if d != self._dir:
            # Driver déjà actif : plus de délai ENA pour séparer DIR du 1er pas
            time.sleep(config.MOTOR_DIR_SETTLE_MS / 1000.0)
            self._dir = d

    # ---- mémorisation de la position ----

    def _persist_moving(self) -> None:
        """À appeler AVANT tout mouvement : position marquée « en mouvement »."""
        self._moving = True
        self._safe = False
        self._quiet_since = None
        if self._store is not None:
            self._store.save(self._steps, moving=True, safe=False)

    def _persist_position(self) -> None:
        """À appeler APRÈS un mouvement : position finale, pas encore « sûre »."""
        self._moving = False
        self._safe = False
        self._quiet_since = None
        if self._store is not None:
            self._store.save(self._steps, moving=False, safe=False)

    def note_pump_state(self, pump_on: bool, now: Optional[float] = None) -> None:
        """
        À appeler à chaque tour de la boucle principale avec l'état de la pompe.

        La position devient « sûre » (utilisable après une coupure de courant
        brutale) quand la VIC est immobile ET la pompe arrêtée depuis au moins
        VIC_STATE_SAFE_DELAY_S — l'eau reste sous pression ≈ 10 s après l'arrêt.
        Pompe en marche ou VIC en mouvement → position « pas sûre » immédiatement.
        Ne lève jamais d'exception.
        """
        if self._store is None:
            return
        try:
            now = time.monotonic() if now is None else float(now)
            if pump_on or self._moving:
                self._quiet_since = None
                if self._safe:
                    self._safe = False
                    self._store.save(self._steps, moving=self._moving, safe=False)
                return
            if self._quiet_since is None:
                self._quiet_since = now
                return
            if not self._safe and now - self._quiet_since >= config.VIC_STATE_SAFE_DELAY_S:
                self._safe = True
                self._store.save(self._steps, moving=False, safe=True)
                log.info(f"VIC position mémorisée — {self._steps} pas marqués sûrs")
        except Exception as e:  # pragma: no cover — sécurité absolue
            log.warning(f"VIC position mémorisée — erreur ignorée ({e})")

    # ---- callback de pas ----

    def set_step_callback(self, cb) -> None:
        """
        Installe un callback appelé après chaque pas généré par _move_steps().

        Permet d'animer un organe d'affichage (LED, buzzer) pendant les
        déplacements bloquants, qui peuvent durer plus de 10 s.
        Passer None pour désactiver.

        ⚠️ Le callback est appelé à la cadence des pas (VIC_SPEED_SPS) et doit
           donc être très bref. Ses exceptions sont absorbées : un défaut
           d'affichage ne doit jamais interrompre un déplacement moteur.
        """
        self._step_cb = cb

    # ---- génération de pas ----
    def _move_steps(self, steps: int, direction: str, speed_sps: float = config.VIC_SPEED_SPS) -> None:
        """
        Génère N pas à vitesse constante dans la direction donnée.
        Active le driver avant le premier pas. Après le dernier : driver laissé
        actif si VIC_HOLD_ENABLED (défaut), désactivé sinon.
        """
        if steps <= 0:
            return
        chip = self._require_open()
        speed = max(config.MOTOR_MIN_SPEED_SPS, min(config.MOTOR_MAX_SPEED_SPS, float(speed_sps)))
        # Demi-période en secondes (impulsion haute + impulsion basse)
        half_s = max(config.MOTOR_MIN_PULSE_US, int(500_000 / speed)) / 1_000_000.0
        self._enable()
        self._set_dir(direction)
        for _ in range(steps):
            lgpio.gpio_write(chip, self.gpio_step, 1)
            time.sleep(half_s)
            lgpio.gpio_write(chip, self.gpio_step, 0)
            time.sleep(half_s)
            if self._step_cb is not None:
                try:
                    self._step_cb()
                except Exception:
                    pass
        self._release_after_move()

    # ---- API publique — déplacement ----

    def move_to(self, target_steps: int) -> None:
        """
        Déplace la VIC vers la position absolue cible (en pas).
        No-op si déjà à la position cible.

        Args:
            target_steps : 0 (DEPART), 250 (NEUTRE), 500 (RETOUR)
        """
        delta = target_steps - self._steps
        if delta == 0:
            return
        direction = "ouverture" if delta > 0 else "fermeture"
        self._persist_moving()
        self._move_steps(abs(delta), direction)
        self._steps = target_steps
        self._persist_position()
        log.info(f"VIC → {target_steps} pas")

    def move_relative(self, delta: int) -> None:
        """
        Déplace la VIC de delta pas relativement à la position courante.
        Positif = ouverture (vers RETOUR), négatif = fermeture (vers DEPART).
        Utile pour les tests et le diagnostic manuel.
        """
        if delta == 0:
            return
        direction = "ouverture" if delta > 0 else "fermeture"
        self._persist_moving()
        self._move_steps(abs(delta), direction)
        self._steps += delta
        self._persist_position()

    @property
    def position(self) -> int:
        """Position courante en pas (fiable uniquement après homing)."""
        return self._steps

    # ---- API publique — déplacement pas-à-pas NON BLOQUANT ----
    #
    # Permet d'étaler une traversée sur plusieurs itérations de la boucle
    # principale, au lieu de la bloquer pendant toute la durée du déplacement.
    # Le driver reste actif entre les pas (couple de maintien conservé) :
    # il ne faut donc PAS enchaîner begin/end à chaque pas.
    #
    # Usage :
    #     vic.begin_stepping("ouverture")
    #     ... à chaque tick : vic.step_once()
    #     vic.end_stepping()
    #     vic.set_position(config.VIC_RETOUR_STEPS)   # recalage après butée

    def begin_stepping(self, direction: str) -> None:
        """
        Démarre une série de pas non bloquante : fixe DIR et active le driver.

        Args:
            direction : 'ouverture' (vers RETOUR) ou 'fermeture' (vers DEPART)
        """
        self._require_open()
        self._persist_moving()
        self._enable()
        self._set_dir(direction)
        self._step_sign = 1 if direction.strip().lower() == "ouverture" else -1

    def step_once(self, speed_sps: float = config.VIC_SPEED_SPS) -> None:
        """
        Génère UN seul pas (durée ≈ 1/speed_sps seconde).

        begin_stepping() doit avoir été appelé au préalable.
        Le compteur de position suit chaque pas commandé, borné à la course
        [0, VIC_TOTAL_STEPS] : une série interrompue (arrêt PRG3 en pleine
        traversée) laisse donc une position exploitable par l'ancrage suivant.
        L'appelant recale tout de même via set_position() une fois en butée.
        """
        chip  = self._require_open()
        speed = max(config.MOTOR_MIN_SPEED_SPS, min(config.MOTOR_MAX_SPEED_SPS, float(speed_sps)))
        half_s = max(config.MOTOR_MIN_PULSE_US, int(500_000 / speed)) / 1_000_000.0
        lgpio.gpio_write(chip, self.gpio_step, 1)
        time.sleep(half_s)
        lgpio.gpio_write(chip, self.gpio_step, 0)
        time.sleep(half_s)
        self._steps = max(0, min(config.VIC_TOTAL_STEPS, self._steps + self._step_sign))

    def end_stepping(self) -> None:
        """
        Termine une série de pas non bloquante. Driver laissé actif si
        VIC_HOLD_ENABLED (le moteur tient la VIC), désactivé sinon.
        Idempotente — appelable même si aucune série n'est en cours.
        """
        was_moving = self._step_sign != 0
        self._step_sign = 0
        if self._chip is not None:
            self._release_after_move()
        if was_moving:
            self._persist_position()

    def set_position(self, steps: int) -> None:
        """
        Recale le compteur de position sans déplacer le moteur.
        À utiliser après un ancrage en butée réalisé en pas-à-pas.
        """
        self._steps = int(steps)
        if not self._moving:
            self._persist_position()

    # ---- homing ----

    @staticmethod
    def homing_amplitudes() -> list[int]:
        """
        Amplitudes (en pas) des cycles progressifs du homing, dans l'ordre.

        Cycle k : VIC_HOMING_FIRST_PCT + (k-1) × VIC_HOMING_STEP_PCT % de la course,
        plafonné à 100 %. Les VIC_HOMING_ANCHOR_CYCLES derniers cycles ne sont pas
        dans cette liste : ce sont les cycles butée à butée.
        Valeurs actuelles (15 / 15 %, 7 cycles dont 1 butée à butée) : [75, 150, 225, 300, 375, 450].
        """
        n_anchor = max(0, min(config.VIC_HOMING_ANCHOR_CYCLES, config.VIC_HOMING_CYCLES))
        n_prog   = config.VIC_HOMING_CYCLES - n_anchor
        amps = []
        for k in range(n_prog):
            pct = min(100, config.VIC_HOMING_FIRST_PCT + k * config.VIC_HOMING_STEP_PCT)
            amps.append(round(config.VIC_TOTAL_STEPS * pct / 100))
        return amps

    def homing(self) -> None:
        """
        Séquence de homing VIC au démarrage machine (position inconnue).

            0. Réarmement du driver (ENA coupé puis rétabli) si VIC_DRIVER_RESET_ENABLED.
            1. Ancrage initial côté S, S alterné d'un démarrage à l'autre
               (DEPART, RETOUR, DEPART… — mémorisé dans state/, décision 2026-11-10).
               Position mémorisée fiable → depuis cette position + marge ;
               sinon toute la course + dépassement.
            2. Cycles progressifs de rodage centrés sur NEUTRE (15 % à 90 % de la
               course actuellement) : montée vers NEUTRE + A/2, descente vers
               NEUTRE - A/2. Ils ne touchent pas les piges.
            3. VIC_HOMING_ANCHOR_CYCLES cycles butée à butée : ancrage côté S puis
               côté opposé, avec VIC_ANCHOR_OVERCOURSE_STEPS de dépassement.
               Sur deux démarrages, chaque pige reçoit autant d'ancrages.
            4. Déplacement vers NEUTRE.
            5. Réarmement du driver (VIC en NEUTRE, sans recalage ensuite :
               le rotor peut se replacer de quelques pas, corrigé au prochain ancrage).

        Le premier ancrage de programme (alternance VIC_ANCHOR_ALTERNATE) se fait
        du côté opposé au dernier ancrage du homing.
        Sans capteur, rien n'est vérifié : un ancrage est « commandé », pas
        « constaté ». À l'issue du homing, self._steps = VIC_NEUTRE_STEPS.
        """
        amps     = self.homing_amplitudes()
        n_anchor = config.VIC_HOMING_CYCLES - len(amps)
        n        = config.VIC_HOMING_CYCLES
        cote     = self._store.homing_side() if self._store is not None else "DEPART"
        oppose   = "RETOUR" if cote == "DEPART" else "DEPART"
        if self._store is not None:
            # Mémorisé dès le début : un homing interrompu fait tout de même alterner.
            self._store.save_homing_side(oppose)
        log.info(
            f"VIC homing — {n} cycles ({len(amps)} progressifs {amps} pas, "
            f"{n_anchor} butée à butée), dépassement {config.VIC_ANCHOR_OVERCOURSE_STEPS} pas, "
            f"ancrage initial côté {cote} (prochain démarrage : {oppose})"
        )
        ancrer = {"DEPART": self.anchor_depart, "RETOUR": self.anchor_retour}

        # Position mémorisée lue AVANT le réarmement : celui-ci réécrit le fichier
        # (« en mouvement » puis « pas sûr ») et la rendrait inutilisable.
        known = self._store.load() if self._store is not None else None

        # 0. Réarmement du driver avant tout mouvement
        if config.VIC_DRIVER_RESET_ENABLED:
            self.reset_driver(config.VIC_DRIVER_RESET_OFF_S, config.VIC_DRIVER_RESET_ON_S)

        # 1. Ancrage initial côté `cote`. Position mémorisée fiable → depuis cette
        #    position + marge (vers la butée visée) ; sinon toute la course.
        if known is None:
            ancrer[cote](full_travel=True)
        else:
            marge = config.VIC_STATE_MARGIN_STEPS
            if cote == "DEPART":
                self._steps = min(config.VIC_TOTAL_STEPS, known + marge)
            else:
                self._steps = max(0, known - marge)
            log.info(f"VIC homing — ancrage initial depuis la position mémorisée "
                     f"{known} pas, marge {marge} pas")
            ancrer[cote](full_travel=False)
        log.info(f"VIC homing — ancrage initial {cote} commandé")

        # 2. Cycles progressifs de rodage centrés sur NEUTRE
        for k, amp in enumerate(amps, start=1):
            low  = max(config.VIC_DEPART_STEPS, config.VIC_NEUTRE_STEPS - amp // 2)
            high = min(config.VIC_RETOUR_STEPS, low + amp)
            self.move_to(high)
            self.move_to(low)
            log.info(f"VIC homing — cycle {k}/{n} rodage amplitude {amp} pas ({low} ↔ {high})")

        # 3. Cycles butée à butée — côté initial puis côté opposé
        for k in range(len(amps) + 1, n + 1):
            ancrer[cote]()
            ancrer[oppose]()
            log.info(f"VIC homing — cycle {k}/{n} butée {cote} puis {oppose}")

        # Premier ancrage de programme : côté opposé au dernier ancrage du homing
        dernier = oppose if n_anchor > 0 else cote
        self._next_anchor_retour = dernier == "DEPART"

        # 4. Position finale NEUTRE
        self.move_to(config.VIC_NEUTRE_STEPS)

        # 5. Réarmement du driver après le homing
        if config.VIC_DRIVER_RESET_ENABLED:
            self.reset_driver(config.VIC_DRIVER_RESET_OFF_S, config.VIC_DRIVER_RESET_ON_S)
        log.info(f"VIC homing — terminé, position commandée NEUTRE ({config.VIC_NEUTRE_STEPS} pas)")

    def _anchor_distance(self, to_depart: bool, full_travel: bool) -> int:
        """
        Nombre de pas d'un ancrage : distance jusqu'à la butée + dépassement.
        Distance = toute la course si full_travel ou VIC_ANCHOR_FULL_TRAVEL,
        sinon la distance depuis la position connue (bornée à la course).
        """
        if full_travel or config.VIC_ANCHOR_FULL_TRAVEL:
            dist = config.VIC_TOTAL_STEPS
        else:
            pos  = max(0, min(config.VIC_TOTAL_STEPS, self._steps))
            dist = pos if to_depart else config.VIC_TOTAL_STEPS - pos
        return dist + config.VIC_ANCHOR_OVERCOURSE_STEPS

    def anchor_programme(self) -> str:
        """
        Ancrage d'un lancement de programme (mini-homing de start()).

        VIC_ANCHOR_ALTERNATE = True  → butée RETOUR et butée DEPART en alternance ;
        VIC_ANCHOR_ALTERNATE = False → toujours butée DEPART.
        Le compteur est recalé sur la butée touchée (0 ou VIC_RETOUR_STEPS).
        Retourne la butée utilisée : "DEPART" ou "RETOUR".
        """
        if config.VIC_ANCHOR_ALTERNATE and self._next_anchor_retour:
            self.anchor_retour()
            cote = "RETOUR"
        else:
            self.anchor_depart()
            cote = "DEPART"
        if config.VIC_ANCHOR_ALTERNATE:
            self._next_anchor_retour = cote == "DEPART"
        return cote

    def anchor_depart(self, full_travel: bool = False) -> None:
        """
        Mini-homing : ancrage mécanique en butée DEPART + recalage compteur à 0.
        Parcourt la distance jusqu'à DEPART + VIC_ANCHOR_OVERCOURSE_STEPS, pour
        garantir l'arrivée physique en butée malgré d'éventuels pas perdus.
        Remet self._steps = 0 après l'ancrage.
        Appelée au début de chaque start() de programme pour garantir
        la position physique réelle avant tout déplacement vers la cible.

        Args:
            full_travel : True = toute la course (position inconnue, homing).
        """
        steps = self._anchor_distance(to_depart=True, full_travel=full_travel)
        log.info(f"VIC mini-homing — ancrage DEPART ({steps} pas dont "
                 f"{config.VIC_ANCHOR_OVERCOURSE_STEPS} de dépassement)")
        self._persist_moving()
        self._move_steps(steps, "fermeture")
        self._steps = config.VIC_DEPART_STEPS
        self._persist_position()
        log.info("VIC mini-homing — ancrage DEPART commandé, compteur recalé à 0")

    def anchor_retour(self, full_travel: bool = False) -> None:
        """
        Mini-homing : ancrage mécanique en butée RETOUR + recalage compteur.
        Parcourt la distance jusqu'à RETOUR + VIC_ANCHOR_OVERCOURSE_STEPS.
        Remet self._steps = VIC_RETOUR_STEPS après l'ancrage.
        Utilisée par le homing et les séquences de rodage.

        Args:
            full_travel : True = toute la course (position inconnue).
        """
        steps = self._anchor_distance(to_depart=False, full_travel=full_travel)
        log.info(f"VIC mini-homing — ancrage RETOUR ({steps} pas dont "
                 f"{config.VIC_ANCHOR_OVERCOURSE_STEPS} de dépassement)")
        self._persist_moving()
        self._move_steps(steps, "ouverture")
        self._steps = config.VIC_RETOUR_STEPS
        self._persist_position()
        log.info(f"VIC mini-homing — ancrage RETOUR commandé, compteur recalé à {config.VIC_RETOUR_STEPS}")