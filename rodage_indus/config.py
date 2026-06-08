"""
config.py — Constantes configurables du rodage industriel.

Modifier uniquement ce fichier pour ajuster le comportement du rodage.
Les constantes hardware (broches, pas/tour, vitesses) sont dans stepper.py.
"""

# ============================================================
# Cycles
# ============================================================

TOTAL_CYCLES: int = 200
# 1 cycle = ouverture POMPE + fermeture POMPE + 1 avance V4V

# ============================================================
# Pauses vanne classique (secondes)
# ============================================================

PAUSE_OPEN_S:  float = 0.5   # pause après ouverture complète
PAUSE_CLOSE_S: float = 0.5   # pause après fermeture complète

# ============================================================
# Vanne classique
# ============================================================

VANNE_CLASSIQUE: str = "POMPE"   # moteur utilisé pour la vanne classique

# ============================================================
# V4V (VIC) — initialisation et ordre de cycle
# ============================================================

# Pas envoyés à l'init pour garantir la butée position 1 (100 pas max + 10 % marge)
VIC_INIT_STEPS: int = 110

# Séquence V4V complète par cycle : aller-retour 1→2→3→4→5→4→3→2→1
# La V4V parcourt cette liste entière à chaque cycle, puis revient en pos.1
VIC_CYCLE_POSITIONS: list = [1, 2, 3, 4, 5, 4, 3, 2, 1]

# Pause entre chaque position V4V (secondes)
VIC_PAUSE_S: float = 0.1
