"""
run_mutants.py — Contrôle de la simulation par mutation (PC UNIQUEMENT).

    python tests/sim/run_mutants.py

Copie V5 dans un dossier temporaire (hors dépôt), casse volontairement le code
(une erreur à la fois) et vérifie que tests/sim/run_sim.py ÉCHOUE. Une simulation
qui reste 100 % OK sur un code cassé ne prouve rien.
Ajouter un mutant à chaque nouvelle fonction VIC. Ne modifie jamais le dépôt.
Durée : environ 1 minute.
"""
import os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
MUTANTS = [
    ("PRG3 : inversion toujours active",
     "programs.py", "if config.PRG3_VIC_INVERT_ENABLED:\n            self._tick_vic_invert(ctx, now)",
     "if True:\n            self._tick_vic_invert(ctx, now)"),
    ("PRG3 stop : oubli du retour NEUTRE",
     "programs.py", "            _move_vic(ctx, config.VIC_NEUTRE_STEPS)\n",
     "            pass\n"),
    ("Réarmement driver jamais appelé",
     "programs.py", "    _reset_vic_driver(ctx)\n    cote = ctx.vic.anchor_programme()",
     "    cote = ctx.vic.anchor_programme()"),
    ("Réarmement : ENA jamais rétabli",
     "libs/vic.py", "        self._enable()\n        wait(max(0.0, float(on_s)))",
     "        wait(max(0.0, float(on_s)))"),
    ("Réarmement : pompe en marche non vérifiée",
     "programs.py", "    if ctx.relays.pompe_is_on:\n", "    if False:\n"),
    ("Réarmement : délai pompe ignoré",
     "programs.py", "        if missing > 0:\n", "        if False:\n"),
    ("Relays : pompe_off_since jamais mis à jour",
     "libs/relays.py", "                self._pompe_off_since = time.monotonic()\n", "                pass\n"),
    ("LCD : cache jamais utilisé",
     "libs/lcd2004.py", "            if self._shown[line0] == s:\n                return",
     "            if False:\n                return"),
    ("LCD : jamais de réécriture forcée",
     "libs/lcd2004.py", "and now - self._last_full_refresh >= config.LCD_FULL_REFRESH_S:",
     "and False:"),
    ("LCD : clear() ne remet pas le cache",
     "libs/lcd2004.py", "        self._shown = [\" \" * self.cols] * self.rows", "        pass"),
    ("Ancrage : dépassement oublié",
     "libs/vic.py", "        return dist + config.VIC_ANCHOR_OVERCOURSE_STEPS", "        return dist"),
    ("Homing : pas de cycle butée à butée",
     "libs/vic.py", "            self.anchor_retour()\n            self.anchor_depart()", "            pass"),
    ("Ancrage alterné : jamais en RETOUR",
     "libs/vic.py", "if config.VIC_ANCHOR_ALTERNATE and self._next_anchor_retour:", "if False:"),
    ("Ancrage alterné : pas de bascule",
     "libs/vic.py", "            self._next_anchor_retour = cote == \"DEPART\"", "            pass"),
    ("Ancrage alterné : interrupteur ignoré",
     "libs/vic.py", "if config.VIC_ANCHOR_ALTERNATE and self._next_anchor_retour:",
     "if self._next_anchor_retour:"),
    ("Recul de butée ignoré",
     "config.py", "VIC_CIBLE_DEPART: int = VIC_DEPART_STEPS + VIC_BUTEE_RECUL_STEPS",
     "VIC_CIBLE_DEPART: int = VIC_DEPART_STEPS"),
]

def run(root: Path) -> tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-B", "tests/sim/run_sim.py"], cwd=root,
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=600)
    m = re.search(r"(\d+)/(\d+) vérifications OK", p.stdout)
    return p.returncode, (m.group(0) if m else "pas de résumé (plantage ?)")

work = Path(tempfile.mkdtemp(prefix="v5_mut_"))
base = work / "V5"
shutil.copytree(SRC, base, ignore=shutil.ignore_patterns("logs", "state", "__pycache__", ".git"))
(base / "logs").mkdir()
rc, res = run(base)
print(f"Référence (code non modifié) : code retour {rc}, {res}")
rc_ref = rc
detected = 0
for name, f, old, new in MUTANTS:
    d = work / "m"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(base, d)
    path = d / f
    txt = path.read_text(encoding="utf-8")
    if old not in txt:
        print(f"  [MUTANT NON APPLIQUÉ] {name}")
        continue
    path.write_text(txt.replace(old, new, 1), encoding="utf-8")
    rc, res = run(d)
    ok = rc != 0
    detected += ok
    print(f"  [{'DÉTECTÉ' if ok else 'NON DÉTECTÉ'}] {name} — {res}")
print(f"\n{detected}/{len(MUTANTS)} erreurs volontaires détectées par la simulation")
print("(un mutant NON APPLIQUÉ = son texte n'existe plus dans le code : le mettre à jour)")
shutil.rmtree(work, ignore_errors=True)
sys.exit(0 if rc_ref == 0 and detected == len(MUTANTS) else 1)
