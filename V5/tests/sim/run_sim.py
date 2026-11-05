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
        check(f"départ {start} : driver jamais coupé", phys.ena_toggles == 0 and vic.enabled,
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
    def __getattr__(self, name):
        return lambda *a, **k: None


def _ctx(vic: VICController, io=None):
    return programs.MachineContext(
        vic=vic, relays=_FakeRelays(), io=io or _FakeIO(),
        flow=SimpleNamespace(flow_lpm=lambda: 999.0, total_liters=lambda: 0.0),
        valve_state={"POT_A_BOUE": False, "EGOUTS": False, "CUVE_TRAVAIL": False, "EAU_PROPRE": False},
        vic_steps=vic.position,
    )


def sc_prg3() -> None:
    print("\n6. PRG3 — 9 traversées, recalage 1 sur 3")
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
    print("\n7. PRG3 — arrêt en pleine traversée")
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
    check("start : DEPART", phys.pos == 0)
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
    check("passage bref par NEUTRE ignoré : un seul mouvement vers RETOUR", moves == [500], str(moves))
    run(0, 3.0)      # NEUTRE voulu
    check("NEUTRE voulu (stable) → appliqué", moves == [500, 250] and phys.pos == 250, str(moves))
    run(2, 0.5); run(0, 3.0)  # aller-retour bref vers RETOUR
    check("retour bref sur RETOUR ignoré", moves == [500, 250], str(moves))
    io.sel = 7
    run(7, 2.0)
    check("lecture inconnue ignorée", moves == [500, 250])
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
    sc_prg3()
    sc_prg3_stop_mid()
    sc_prg5_selector()
    sc_real_travel()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} vérifications OK")
    sys.exit(1 if failed else 0)
