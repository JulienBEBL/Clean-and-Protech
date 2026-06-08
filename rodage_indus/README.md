# Rodage Industriel — Clean & Protech V4

Script de rodage autonome pour la machine SERENA.
Deux moteurs tournent en parallèle pendant N cycles configurables.

## Lancement

```bash
cd /home/bebl/Desktop/Clean-and-Protech/rodage_indus
python3 rodage.py
```

Le log s'écrit dans `logs/rodage_YYYYMMDD_HHMMSS.log`.  
Arrêt propre : **Ctrl+C** (la machine revient en position sûre avant de s'éteindre).

---

## Comportement

| Moteur           | Cycle                                                       |
|------------------|-------------------------------------------------------------|
| Vanne classique  | Ouverture → pause → Fermeture → pause → recommence         |
| VIC (V4V)        | Pos 1 → 2 → 3 → 4 → 5 → 1 → recommence                    |

Les deux boucles tournent **simultanément** (threads indépendants).  
Un **cycle global** est comptabilisé quand les deux boucles ont chacune terminé un aller-retour / tour complet.

---

## Paramètres configurables (`config.py`)

| Paramètre            | Défaut        | Description                                  |
|----------------------|---------------|----------------------------------------------|
| `TOTAL_CYCLES`       | `1000`        | Nombre de cycles complets avant arrêt normal |
| `PAUSE_OPEN_S`       | `2.0`         | Pause (s) en position ouverte — vanne        |
| `PAUSE_CLOSE_S`      | `2.0`         | Pause (s) en position fermée — vanne         |
| `VANNE_CLASSIQUE`    | `"RETOUR"`    | Nom métier de la vanne à cycler              |
| `VIC_CYCLE_POSITIONS`| `[1,2,3,4,5]` | Ordre des positions VIC (1..5)               |

### Exemple : test rapide 10 cycles, pauses courtes

```python
# config.py
TOTAL_CYCLES  = 10
PAUSE_OPEN_S  = 0.5
PAUSE_CLOSE_S = 0.5
```

---

## Structure

```
rodage_indus/
├── rodage.py   — point d'entrée, boucle parallèle + gestion arrêt
├── config.py   — tous les paramètres ajustables
├── stepper.py  — fonctions de pilotage moteur (wrapping V4/libs/moteur.py)
└── logs/       — logs horodatés créés automatiquement
```

Les bibliothèques V4 (`libs/`, `config.py` V4) sont importées directement
depuis `../V4` — aucune copie nécessaire.

---

## Position de sécurité à l'arrêt

Quel que soit le motif d'arrêt (fin normale ou Ctrl+C) :

- Vanne classique → **position ouverte**
- VIC → **position 1** (0 pas, butée DEPART)
- Tous les drivers → **désactivés** (ENA HIGH)
