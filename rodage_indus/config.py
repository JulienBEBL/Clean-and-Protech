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

PAUSE_OPEN_S:  float = 2.0   # pause après ouverture complète
PAUSE_CLOSE_S: float = 2.0   # pause après fermeture complète

# ============================================================
# Vanne classique
# ============================================================

VANNE_CLASSIQUE: str = "POMPE"   # moteur utilisé pour la vanne classique

# ============================================================
# V4V (VIC) — initialisation et ordre de cycle
# ============================================================

# Pas envoyés à l'init pour garantir la butée position 1 (100 pas max + 10 % marge)
VIC_INIT_STEPS: int = 110

# Ordre des positions V4V dans un cycle (1..5)
# Chaque cycle avance d'une position ; retour à 1 après la position 5
VIC_CYCLE_ORDER: list = [1, 2, 3, 4, 5]
