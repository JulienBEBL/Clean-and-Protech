"""
config.py — Constantes configurables du rodage industriel.

Modifier uniquement ce fichier pour ajuster le comportement du rodage.
Les constantes hardware (broches, vannes, pas/tour, vitesses) sont dans stepper.py.
"""

# ============================================================
# Cycles
# ============================================================

TOTAL_CYCLES: int = 200
# 1 cycle = les 4 vannes (POMPE, RETOUR, CUVE_TRAVAIL, EAU_PROPRE)
#           ont chacune fait : fermeture complète + ouverture complète

# ============================================================
# Pauses entre chaque mouvement (secondes)
# ============================================================

PAUSE_OPEN_S:  float = 0.5   # pause après ouverture complète de chaque vanne
PAUSE_CLOSE_S: float = 0.5   # pause après fermeture complète de chaque vanne
