"""
config.py — Paramètres configurables du script de rodage industriel.

Toutes les constantes ajustables sont ici. Les constantes hardware
(pins, pas/tour, vitesses) sont importées directement depuis V4/config.py.

Pour changer le nombre de cycles ou les pauses, modifier uniquement ce fichier.
"""

# ============================================================
# Nombre de cycles complets de rodage
# Un cycle = 1 aller-retour vanne classique ET 1 tour complet V4V
# ============================================================
TOTAL_CYCLES: int = 200

# ============================================================
# Pauses vanne classique (secondes)
# ============================================================
PAUSE_OPEN_S:  float = 1.0   # pause en position ouverte
PAUSE_CLOSE_S: float = 1.0   # pause en position fermée

# ============================================================
# Nom de la vanne classique à cycler (doit exister dans V4/config.py)
# Valeurs valides : RETOUR, POT_A_BOUE, CUVE_TRAVAIL, EGOUTS,
#                   DEPART, EAU_PROPRE, POMPE
# ============================================================
VANNE_CLASSIQUE: str = "POMPE"

# ============================================================
# Ordre des positions V4V (VIC) — doit correspondre aux clés de
# VIC_POSITIONS dans V4/config.py : {1:0, 2:30, 3:50, 4:70, 5:100}
# Le cycle parcourt cette liste dans l'ordre, puis retourne à la première.
# ============================================================
# Nombre de pas envoyés à l'init pour garantir la butée mécanique position 1.
# Course physique max = 100 pas → 110 pas assure la butée quelle que soit
# la position de départ (marge +10 %).
VIC_INIT_STEPS: int = 110

# Cycle V4V : aller-retour 1→2→3→4→5→4→3→2→1
# La position 1 (0 pas) est atteinte en fin de chaque cycle → départ propre du suivant.
VIC_CYCLE_POSITIONS: list[int] = [1, 2, 3, 4, 5, 4, 3, 2, 1]
