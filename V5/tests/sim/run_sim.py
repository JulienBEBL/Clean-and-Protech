"""
run_sim.py — Simulation PC de la VIC V5 (faux lgpio + modèle physique des piges).

À lancer sur le PC, JAMAIS sur le Raspberry :
    python tests/sim/run_sim.py

Horloge simulée : time.sleep() avance une horloge virtuelle, la simulation
complète tourne en quelques secondes. Chaque scénario affiche OK / ÉCHEC ;
le code de sortie vaut 1 si un scénario échoue.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---- horloge virtuelle (avant tout import projet) ----
_clock = [1000.0]
time.sleep = lambda s: _clock.__setitem__(0, _clock[0] + max(0.0, float(s)))
time.monotonic = lambda: _clock[0]

import config  # noqa: E402
from tests.sim.fake_lgpio import install, set_physique, VICPhysique  # noqa: E402

install()
_TMP = Path(tempfile.mkdtemp(prefix="vic_sim_"))
config.VIC_STATE_FILE = str(_TMP / "vic_state.json")

import libs.gpio_handle as gpio_handle  # noqa: E402
from libs.vic import VICController       # noqa: E402
import programs                          # noqa: E402

gpio_handle.init()

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"  [{'OK' if cond else 'ECHEC'}] {name}" + (f" — {detail}" if detail else ""))


def new_vic(phys: VICPhysique) -> VICController:
    set_physique(phys)
    v = VICController()
    v.open()
    return v


def state_file() -> dict | None:
    p = Path(config.VIC_STATE_FILE)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def clear_state() -> None:
    for p in Path(config.VIC_STATE_FILE).parent.glob("vic_state.json*"):
        p.unlink()


def idle(vic: VICController, seconds: float, pump_on: bool = False) -> None:
    """Simule la boucle principale à 10 Hz sans mouvement."""
    end = _clock[0] + seconds
    while _clock[0] < end:
        vic.note_pump_state(pump_on)
        time.sleep(0.1)


# ======================================================================
def sc_homing_unknown() -> None:
    print("\n1. Homing, position inconnue, pas de fichier")
    for start in (0, 250, 500):
        clear_state()
        phys = VICPhysique(500, start)
        vic = new_vic(phys)
        t0 = _clock[0]
        vic.homing()
        dt = _clock[0] - t0
        check(f"départ {start} : fin NEUTRE physique et compteur",
              phys.pos == 250 and vic.position == 250, f"phys={phys.pos} cpt={vic.position}")
        check(f"départ {start} : réarmé avant/après, jamais coupé en mouvement, actif à la fin",
              phys.ena_toggles == 1 and phys.steps_while_disabled == 0 and vic.enabled,
              f"coupures={phys.ena_toggles}")
        print(f"      durée {dt:.0f} s, pas forcés {phys.steps_forced} "
              f"(DEPART {phys.forced_at_0}, RETOUR {phys.forced_at_travel})")
        vic.close()


def sc_homing_known() -> None:
    print("\n2. Homing avec position mémorisée sûre")
    clear_state()
    phys = VICPhysique(500, 137)
    vic = new_vic(phys)
    vic.homing()
    vic.move_to(400)
    idle(vic, 16)  # pompe OFF ≥ 15 s → sûr
    st = state_file()
    check("fichier marqué sûr après 15 s pompe OFF", st and st["safe"] and st["position"] == 400, str(st))
    vic.close()
    # coupure de courant : nouveau démarrage, VIC physiquement à 400
    phys2 = VICPhysique(500, 400)
    vic2 = new_vic(phys2)
    vic2.homing()
    check("redémarrage : NEUTRE exact", phys2.pos == 250 and vic2.position == 250, f"phys={phys2.pos}")
    first_anchor_forced = phys2.forced_at_0
    print(f"      pas forcés en DEPART {phys2.forced_at_0} "
          f"(sans fichier, depuis 400 : 116 + 16 du cycle butée à butée = 132)")
    check("forçage DEPART réduit", first_anchor_forced <= 40 + 16 + 16, f"{first_anchor_forced}")
    vic2.close()


def sc_unsafe_cases() -> None:
    print("\n3. Cas où le fichier ne doit PAS servir → pleine course")
    # 3a pompe ON au moment de la coupure
    clear_state()
    phys = VICPhysique(500, 300)
    vic = new_vic(phys); vic.homing(); vic.move_to(500)
    idle(vic, 16)                     # sûr
    idle(vic, 1, pump_on=True)        # pompe démarre → pas sûr
    st = state_file()
    check("pompe ON → fichier pas sûr", st and st["safe"] is False, str(st))
    idle(vic, 8)                      # pompe OFF depuis 8 s seulement
    check("pompe OFF depuis 8 s → toujours pas sûr", state_file()["safe"] is False)
    vic.close()
    # 3b mouvement interrompu (PRG3 en pleine traversée)
    clear_state()
    phys = VICPhysique(500, 300)
    vic = new_vic(phys); vic.homing(); idle(vic, 16)
    vic.begin_stepping("ouverture")
    for _ in range(100):
        vic.step_once()
    check("traversée interrompue → fichier « en mouvement »", state_file()["moving"] is True)
    vic.close()
    phys2 = VICPhysique(500, phys.pos)
    vic2 = new_vic(phys2); vic2.homing()
    check("après coupure en mouvement : NEUTRE exact", phys2.pos == 250 and vic2.position == 250)
    vic2.close()
    # 3c fichier corrompu
    Path(config.VIC_STATE_FILE).write_text("{pas du json", encoding="utf-8")
    phys3 = VICPhysique(500, 480)
    vic3 = new_vic(phys3); vic3.homing()
    check("fichier corrompu → NEUTRE exact", phys3.pos == 250 and vic3.position == 250)
    vic3.close()
    # 3d course changée dans config
    clear_state()
    vic4 = new_vic(VICPhysique(500, 250)); vic4.homing(); idle(vic4, 16); vic4.close()
    st = state_file(); st["total_steps"] = 510
    Path(config.VIC_STATE_FILE).write_text(json.dumps(st), encoding="utf-8")
    from libs.vic_state import VICStateStore
    check("course différente → ignoré", VICStateStore(config.VIC_STATE_FILE, 500).load() is None)


def sc_write_failure() -> None:
    print("\n4. Échec d'écriture SD → jamais d'ancienne position « sûre »")
    clear_state()
    vic = new_vic(VICPhysique(500, 250)); vic.homing(); idle(vic, 16)
    check("état sûr écrit", state_file()["safe"] is True)
    import os
    real_replace = os.replace
    os.replace = lambda *a: (_ for _ in ()).throw(OSError("SD en lecture seule (simulé)"))
    try:
        vic.move_to(0)                # écriture « en mouvement » échoue
    finally:
        os.replace = real_replace
    check("fichier supprimé après échec", state_file() is None)
    check("le mouvement a quand même eu lieu", vic.position == 0)
    vic.close()


def sc_water_hold() -> None:
    print("\n5. Driver toujours actif : l'eau ne peut plus tourner la VIC")
    clear_state()
    phys = VICPhysique(500, 250)
    vic = new_vic(phys); vic.homing()
    phys.push_water(+120)
    check("driver actif → VIC immobile", phys.pos == 250)
    config.VIC_HOLD_ENABLED = False
    vic.move_to(260); vic.move_to(250)
    phys.push_water(+120)
    check("(ancien comportement) driver libre → VIC poussée", phys.pos == 370, f"phys={phys.pos}")
    config.VIC_HOLD_ENABLED = True
    vic.close()


class _FakeIO:
    def __init__(self) -> None:
        self.sel = 0
    def read_vic_selector(self) -> int:
        return self.sel
    def read_air_mode(self) -> int:
        return 0


class _FakeRelays:
    pompe_is_on = False
    pompe_off_since = None
    def __getattr__(self, name):
        return lambda *a, **k: None


def _ctx(vic: VICController, io=None):
    return programs.MachineContext(
        vic=vic, relays=_FakeRelays(), io=io or _FakeIO(),
        flow=SimpleNamespace(flow_lpm=lambda: 999.0, total_liters=lambda: 0.0),
        valve_state={"POT_A_BOUE": False, "EGOUTS": False, "CUVE_TRAVAIL": False, "EAU_PROPRE": False},
        vic_steps=vic.position,
    )


def sc_prg3_fixed() -> None:
    print("\n6a. PRG3 — VIC fixe en DEPART (décision 2026-11-09), fin NEUTRE")
    clear_state()
    config.PRG3_VIC_INVERT_ENABLED = False
    phys = VICPhysique(500, 250)
    vic = new_vic(phys); vic.homing()
    ctx = _ctx(vic)
    prg = programs.Prg3()
    programs._set_valves = lambda c, v: None
    prg.start(ctx)
    check("start : DEPART (recul de butée) physique et compteur", phys.pos == config.VIC_CIBLE_DEPART and vic.position == config.VIC_CIBLE_DEPART, f"phys={phys.pos}")
    phys.reset_counters()
    for _ in range(10 * 60 * 10):          # 10 min de boucle à 10 Hz
        prg.tick(ctx); time.sleep(0.1)
    check("10 min : aucun pas émis, VIC immobile en DEPART",
          phys.steps_ok == 0 and phys.steps_forced == 0 and phys.pos == config.VIC_CIBLE_DEPART,
          f"ok={phys.steps_ok} forcés={phys.steps_forced}")
    prg.stop(ctx)
    check("stop : NEUTRE sans nouvel appui sur la pige",
          phys.pos == 250 and vic.position == 250 and phys.forced_at_0 == 0,
          f"phys={phys.pos} forcés DEPART={phys.forced_at_0}")
    vic.close()


def sc_driver_reset() -> None:
    print("\n6b. Réarmement driver avant l'ancrage de chaque start()")
    clear_state()
    phys = VICPhysique(500, 250)
    vic = new_vic(phys); vic.homing()
    relays = _FakeRelays()
    ctx = _ctx(vic); ctx.relays = relays
    programs._set_valves = lambda c, v: None
    phys.reset_counters()
    programs.Prg4().start(ctx)
    check("1 coupure ENA par start(), puis NEUTRE exact",
          phys.ena_toggles == 1 and phys.steps_while_disabled == 0 and phys.pos == 250 and vic.enabled,
          f"coupures={phys.ena_toggles} pas ENA coupé={phys.steps_while_disabled} phys={phys.pos}")
    # driver « en défaut » simulé : VIC libre déplacée (eau) pendant la coupure, VERS la butée
    # d'ancrage qui suit → l'ancrage recale (une dérive vers l'autre butée n'est rattrapée
    # qu'à hauteur du dépassement, voir 6e)
    phys.reset_counters()
    orig_disable = vic._disable
    sens = +30 if vic._next_anchor_retour else -30
    def disable_and_push():
        orig_disable(); phys.push_water(sens)
    vic._disable = disable_and_push
    programs.Prg2().start(ctx)
    vic._disable = orig_disable
    check("VIC bougée pendant la coupure → recalée par l'ancrage", phys.pos == 250 and vic.position == 250,
          f"phys={phys.pos}")
    # pompe arrêtée depuis 5 s → attente des 10 s manquantes avant la coupure
    relays.pompe_off_since = _clock[0] - 5.0
    cut_at = []
    orig_disable = vic._disable
    vic._disable = lambda: (cut_at.append(_clock[0]), orig_disable())[1]
    programs.Prg4().start(ctx)
    vic._disable = orig_disable
    delay = (cut_at[0] - relays.pompe_off_since) if cut_at else -1
    check("coupure ENA seulement ≥ 15 s après l'arrêt pompe", delay >= config.VIC_DRIVER_RESET_PUMP_OFF_S - 1e-6,
          f"coupure {delay:.1f}s après l'arrêt pompe")
    # reset_driver seul : driver de nouveau actif à la sortie (avant tout pas)
    vic.reset_driver(0.1, 0.1)
    check("reset_driver : ENA rétabli avant l'ancrage", phys.ena_active and vic.enabled)
    # pompe en marche → réarmement ignoré
    relays.pompe_off_since = None
    relays.pompe_is_on = True
    phys.reset_counters()
    programs._anchor_and_move_vic(ctx, config.VIC_NEUTRE_STEPS)
    check("pompe en marche → pas de coupure ENA", phys.ena_toggles == 0)
    relays.pompe_is_on = False
    # désactivé par config
    config.VIC_DRIVER_RESET_ENABLED = False
    phys.reset_counters()
    programs.Prg2().start(ctx)
    check("VIC_DRIVER_RESET_ENABLED = False → pas de coupure", phys.ena_toggles == 0)
    config.VIC_DRIVER_RESET_ENABLED = True
    vic.close()


def sc_relays_pump_off_since() -> None:
    print("\n6d. Relays.pompe_off_since (vrai module relays, faux lgpio)")
    from libs.relays import Relays
    r = Relays(); r.open()
    check("après open() : None (pompe jamais démarrée)", r.pompe_off_since is None)
    r.set_pompe_off()
    check("arrêt sans marche préalable : toujours None", r.pompe_off_since is None)
    r.set_pompe_on(); time.sleep(3.0); t_off = _clock[0]
    r.set_pompe_off()
    check("arrêt après marche : instant enregistré", r.pompe_off_since == t_off, f"{r.pompe_off_since}")
    time.sleep(2.0); r.set_pompe_off()
    check("2e arrêt sans marche : instant inchangé", r.pompe_off_since == t_off)
    r.close()


def sc_anchor_recovery() -> None:
    print("\n6e. Ancrage : rattrape des pas perdus (≤ dépassement)")
    clear_state()
    phys = VICPhysique(500, 250)
    vic = new_vic(phys); vic.homing()
    ctx = _ctx(vic)
    programs._set_valves = lambda c, v: None
    for _ in range(2):      # un start() de chaque côté (alternance)
        vers_retour = vic._next_anchor_retour
        cote = "RETOUR" if vers_retour else "DEPART"
        # écart de 12 pas à l'OPPOSÉ de la butée d'ancrage : rattrapé (≤ 16 de dépassement)
        phys.pos = 250 + (-12 if vers_retour else 12)
        programs.Prg2().start(ctx)
        check(f"ancrage {cote} : 12 pas d'écart côté opposé → NEUTRE exact", phys.pos == 250, f"phys={phys.pos}")
    for _ in range(2):
        vers_retour = vic._next_anchor_retour
        cote = "RETOUR" if vers_retour else "DEPART"
        # 20 pas VERS la butée d'ancrage : absorbés contre la pige
        phys.pos = 250 + (20 if vers_retour else -20)
        programs.Prg4().start(ctx)
        check(f"ancrage {cote} : 20 pas vers la butée → NEUTRE exact", phys.pos == 250, f"phys={phys.pos}")
    vic.close()


def sc_homing_wrong_memory() -> None:
    print("\n6f. Homing avec position mémorisée FAUSSE (fichier « sûr » = 250, VIC en 500)")
    clear_state()
    vic = new_vic(VICPhysique(500, 250)); vic.homing(); idle(vic, 16); vic.close()
    phys = VICPhysique(500, 500)
    vic2 = new_vic(phys)
    vic2.homing()
    check("référence rétablie par le cycle butée à butée : NEUTRE exact",
          phys.pos == 250 and vic2.position == 250, f"phys={phys.pos}")
    print(f"      coût : pas forcés {phys.steps_forced} (DEPART {phys.forced_at_0}, RETOUR {phys.forced_at_travel})")
    vic2.close()


def _enchainement(travel: int) -> tuple[list, VICPhysique, VICController]:
    """Homing puis PRG1..PRG5 comme une journée client ; retourne (programme, butée, cible, physique)."""
    clear_state()
    phys = VICPhysique(travel, 250)
    vic = new_vic(phys); vic.homing()
    if not config.VIC_ANCHOR_ALTERNATE:
        vic._next_anchor_retour = True   # l'interrupteur doit l'emporter sur cet état
    io = _FakeIO(); io.sel = 0
    ctx = _ctx(vic, io)
    programs._set_valves = lambda c, v: None
    phys.reset_counters()
    journal = []
    sequence = [(1, programs.Prg1(), None), (2, programs.Prg2(), None), (3, programs.Prg3(), None),
                (4, programs.Prg4(), None), (5, programs.Prg5(), 1), (5, programs.Prg5(), 2),
                (5, programs.Prg5(), 0), (1, programs.Prg1(), None)]
    for n, prg, sel in sequence:
        if sel is not None:
            io.sel = sel
        cote_avant = vic._next_anchor_retour
        prg.start(ctx)
        cible = vic.position
        journal.append((n, "RETOUR" if (cote_avant and config.VIC_ANCHOR_ALTERNATE) else "DEPART",
                        cible, phys.pos))
        if isinstance(prg, programs.Prg5):
            prg._grace_deadline = 1e12
        for _ in range(30):
            prg.tick(ctx); time.sleep(0.1)
        prg.stop(ctx)
    return journal, phys, vic


def sc_anchor_alternate() -> None:
    print("\n6g. Ancrage alterné DEPART / RETOUR (VIC_ANCHOR_ALTERNATE = True)")
    config.VIC_ANCHOR_ALTERNATE = True
    journal, phys, vic = _enchainement(500)
    cotes = [c for _, c, _, _ in journal]
    check("butées alternées, 1er ancrage opposé au dernier du homing (homing côté DEPART → finit RETOUR)",
          cotes == ["DEPART", "RETOUR"] * 4, str(cotes))
    check("course réelle = configurée : chaque cible exacte",
          all(cible == p for _, _, cible, p in journal), str([(n, c, p) for n, _, c, p in journal]))
    check("appuis répartis sur les deux piges",
          phys.forced_at_0 > 0 and phys.forced_at_travel > 0
          and abs(phys.forced_at_0 - phys.forced_at_travel) <= 16 * 2,
          f"DEPART {phys.forced_at_0} pas, RETOUR {phys.forced_at_travel} pas")
    check("fin de journée : NEUTRE exact", phys.pos == 250 and vic.position == 250, f"phys={phys.pos}")
    check("recul de butée : aucun programme ne laisse la VIC sur une pige",
          config.VIC_BUTEE_RECUL_STEPS > 0
          and all(p not in (0, 500) for _, _, _, p in journal), str([p for _, _, _, p in journal]))
    vic.close()

    config.VIC_ANCHOR_ALTERNATE = False
    journal, phys, vic = _enchainement(500)
    check("VIC_ANCHOR_ALTERNATE = False → toujours DEPART, appuis RETOUR = 0",
          all(c == "DEPART" for _, c, _, _ in journal) and phys.forced_at_travel == 0,
          f"RETOUR {phys.forced_at_travel}")
    vic.close()
    config.VIC_ANCHOR_ALTERNATE = True

    print("      Course réelle ≠ 500 (non mesurée) — position physique atteinte par cible :")
    for travel in (480, 520):
        journal, phys, vic = _enchainement(travel)
        check(f"course {travel} : écart borné à |course - 500| = {abs(travel - 500)} pas",
              max(abs(p - c) for _, _, c, p in journal) <= abs(travel - 500),
              " ".join(f"PRG{n}/{cote[0]}:{c}->{p}" for n, cote, c, p in journal))
        vic.close()


def sc_homing_alterne() -> None:
    print("\n6h. Homing alterné d'un démarrage à l'autre")
    clear_state()
    cotes, forces, prem = [], [], []
    for boot, start in enumerate((250, 250, 250, 0, 500), start=1):
        phys = VICPhysique(500, start)
        vic = new_vic(phys)
        cotes.append(vic._store.homing_side())
        vic.homing()
        forces.append((phys.forced_at_0, phys.forced_at_travel))
        prem.append("RETOUR" if vic._next_anchor_retour else "DEPART")
        check(f"démarrage {boot} (VIC en {start}) : NEUTRE exact", phys.pos == 250 and vic.position == 250,
              f"phys={phys.pos}")
        idle(vic, 16)   # pompe arrêtée → position sûre pour le démarrage suivant
        vic.close()
    check("côté initial alterné DEPART / RETOUR", cotes == ["DEPART", "RETOUR", "DEPART", "RETOUR", "DEPART"], str(cotes))
    check("1er ancrage de programme = opposé au dernier ancrage du homing",
          prem == ["DEPART", "RETOUR", "DEPART", "RETOUR", "DEPART"], str(prem))
    tot0 = sum(f[0] for f in forces[1:3]); tot1 = sum(f[1] for f in forces[1:3])
    check("démarrage 2 : position mémorisée utilisée (≤ marge 40 + 2 × 16 pas forcés)",
          forces[1][1] <= config.VIC_STATE_MARGIN_STEPS + 2 * config.VIC_ANCHOR_OVERCOURSE_STEPS,
          f"RETOUR {forces[1][1]} pas")
    check("démarrages 2 et 3 (position mémorisée) : autant d'appuis sur chaque pige", tot0 == tot1,
          f"DEPART {tot0} pas, RETOUR {tot1} pas")
    print(f"      appuis (DEPART, RETOUR) par démarrage : {forces}")
    # fonction désactivée : VIC_STATE_ENABLED = False → toujours DEPART
    config.VIC_STATE_ENABLED = False
    v = new_vic(VICPhysique(500, 250))
    check("position mémorisée désactivée → homing côté DEPART", v._store is None)
    v.homing(); v.close()
    config.VIC_STATE_ENABLED = True


def sc_lcd_cache() -> None:
    print("\n6c. Cache des lignes LCD")
    import types
    if "smbus2" not in sys.modules:                # pas de smbus2 sur le PC : module factice
        fake = types.ModuleType("smbus2"); fake.SMBus = object
        sys.modules["smbus2"] = fake
    from libs.lcd2004 import LCD2004
    writes = [0]
    bus = SimpleNamespace(
        _require_open=lambda: SimpleNamespace(write_byte=lambda a, b: None),
        _run=lambda name, addr, fn: (writes.__setitem__(0, writes[0] + 1), fn())[1],
    )
    lcd = LCD2004(bus)
    lcd.clear()
    writes[0] = 0
    lcd.write_centered(1, "PROGRAMME 4")
    first = writes[0]
    lcd.write_centered(1, "PROGRAMME 4")
    check("ligne identique → aucune écriture I2C", writes[0] == first, f"{first} puis {writes[0]}")
    lcd.write_centered(1, "PROGRAMME 5")
    check("ligne modifiée → réécrite", writes[0] > first)
    before = writes[0]
    time.sleep(config.LCD_FULL_REFRESH_S + 0.1)
    lcd.write_centered(1, "PROGRAMME 5")
    check("réécriture forcée après LCD_FULL_REFRESH_S", writes[0] > before)
    lcd.clear(); before = writes[0]
    lcd.write_centered(2, "")
    check("ligne vide après clear() → aucune écriture", writes[0] == before)


def sc_prg3() -> None:
    print("\n6. PRG3 (inversion activée) — 9 traversées, recalage 1 sur 3")
    config.PRG3_VIC_INVERT_ENABLED = True
    clear_state()
    phys = VICPhysique(500, 250)
    vic = new_vic(phys); vic.homing()
    ctx = _ctx(vic)
    prg = programs.Prg3()
    prg._set_valves = None
    programs._set_valves = lambda c, v: None
    prg.start(ctx)
    phys.reset_counters()
    arrivals = []
    while prg._vic_traversals < 9 or prg._vic_moving:
        moving_before = prg._vic_moving
        prg.tick(ctx)
        if moving_before and not prg._vic_moving:
            arrivals.append((prg._vic_traversals, phys.pos, vic.position, phys.steps_forced))
        time.sleep(0.1)
    ok = all(p == c for _, p, c, _ in arrivals)
    check("9 traversées : physique = compteur à chaque arrivée", ok and len(arrivals) == 9,
          str([(n, p) for n, p, _, _ in arrivals]))
    check("pas forcés = 3 recalages × 8", phys.steps_forced == 24, f"{phys.steps_forced}")
    check("driver jamais coupé", phys.ena_toggles == 0)
    prg.stop(ctx)
    check("stop : NEUTRE", phys.pos == 250 and vic.position == 250)
    vic.close()


def sc_prg3_stop_mid() -> None:
    print("\n7. PRG3 (inversion activée) — arrêt en pleine traversée")
    config.PRG3_VIC_INVERT_ENABLED = True
    clear_state()
    phys = VICPhysique(500, 250)
    vic = new_vic(phys); vic.homing()
    ctx = _ctx(vic)
    prg = programs.Prg3()
    prg.start(ctx)
    while not prg._vic_moving:
        prg.tick(ctx); time.sleep(0.1)
    for _ in range(30):
        prg.tick(ctx); time.sleep(0.1)
    prg.stop(ctx)
    check("arrêt mi-traversée → NEUTRE exact", phys.pos == 250 and vic.position == 250, f"phys={phys.pos}")
    config.PRG3_VIC_INVERT_ENABLED = False
    vic.close()


def sc_prg5_selector() -> None:
    print("\n8. PRG5 — sélecteur DEP → (NEU bref) → RET")
    clear_state()
    phys = VICPhysique(500, 250)
    vic = new_vic(phys); vic.homing()
    io = _FakeIO(); io.sel = 1
    ctx = _ctx(vic, io)
    prg = programs.Prg5()
    prg.start(ctx)
    check("start : DEPART (recul de butée)", phys.pos == config.VIC_CIBLE_DEPART, f"phys={phys.pos}")
    prg._grace_deadline = 1e12  # sécurité débit hors scénario
    moves = []
    orig = programs._move_vic
    programs._move_vic = lambda c, t: (moves.append(t), orig(c, t))
    def run(sel: int, seconds: float) -> None:
        io.sel = sel
        end = _clock[0] + seconds
        while _clock[0] < end:
            prg.tick(ctx); time.sleep(0.1)
    run(0, 0.4)      # passage par NEUTRE 0,4 s
    run(2, 3.0)      # RETOUR
    check("passage bref par NEUTRE ignoré : un seul mouvement vers RETOUR", moves == [config.VIC_CIBLE_RETOUR], str(moves))
    run(0, 3.0)      # NEUTRE voulu
    check("NEUTRE voulu (stable) → appliqué", moves == [config.VIC_CIBLE_RETOUR, 250] and phys.pos == 250, str(moves))
    run(2, 0.5); run(0, 3.0)  # aller-retour bref vers RETOUR
    check("retour bref sur RETOUR ignoré", moves == [config.VIC_CIBLE_RETOUR, 250], str(moves))
    io.sel = 7
    run(7, 2.0)
    check("lecture inconnue ignorée", moves == [config.VIC_CIBLE_RETOUR, 250])
    programs._move_vic = orig
    vic.close()


def sc_real_travel() -> None:
    print("\n9. Course réelle ≠ 500 (info, non bloquant)")
    for travel in (480, 520):
        clear_state()
        phys = VICPhysique(travel, 250)
        vic = new_vic(phys); vic.homing()
        vic.move_to(500)
        print(f"      course réelle {travel} : NEUTRE physique après homing ? RETOUR demandé → "
              f"physique {phys.pos}, pas forcés au total {phys.steps_forced}")
        vic.close()


if __name__ == "__main__":
    print(f"Simulation VIC — fichier d'état temporaire : {config.VIC_STATE_FILE}")
    sc_homing_unknown()
    sc_homing_known()
    sc_unsafe_cases()
    sc_write_failure()
    sc_water_hold()
    sc_prg3_fixed()
    sc_driver_reset()
    sc_relays_pump_off_since()
    sc_anchor_recovery()
    sc_homing_wrong_memory()
    sc_anchor_alternate()
    sc_homing_alterne()
    sc_lcd_cache()
    sc_prg3()
    sc_prg3_stop_mid()
    sc_prg5_selector()
    sc_real_travel()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} vérifications OK")
    sys.exit(1 if failed else 0)
