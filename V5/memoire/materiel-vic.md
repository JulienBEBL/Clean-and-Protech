# Matériel VIC

> Source : prompt de mission (2026-11-05) et `CLAUDE.md`. Les infos détaillées moteur / réducteur /
> mécanique / piges que Julien doit envoyer seront ajoutées ici, datées.

## Chaîne cinématique (depuis 2026-10-21)

| Élément | Détail |
|---|---|
| Driver | JK-DM860H, DIP 400 pas/tour moteur, courant 6.0 A (pic 7.2 A) |
| Signaux | STEP GPIO 27, DIR GPIO 17, ENA GPIO 22 (actif bas). `lgpio`, gpiochip4, RPi 5 |
| Moteur | STEPPERONLINE 34IP65-120 : NEMA 34, 12 N·m de maintien, 6 A. Courbe constructeur ≈ 9 N·m à 100 tr/min (60 V, 2000 µpas) |
| Réducteur | STEPPERONLINE RYG34-G5 : planétaire **à renvoi d'angle**, 5:1, η 96 %, jeu ≤ 10 arcmin, 90 N·m admissibles (180 N·m momentané) |
| Butées | 2 piges dans la VIC, **38 N·m chacune**. Aucun capteur de position |

Inconnus à ce jour : tension d'alimentation du DM860H, réglage idle-current (SW4) du driver,
couple résistant de la VIC elle-même, comportement mécanique des piges (rigide, élastique ?).

## Conversions (tout le code est en pas)

- 400 pas/tour moteur × 5 = **2000 pas / tour de VIC → 1 pas = 0,18°**.
- DEPART 0 · NEUTRE 250 (45°) · RETOUR 500 (90°).
- Jeu réducteur 10 arcmin ≈ 0,17° < 1 pas : ignoré.

## Vitesse

- `VIC_SPEED_SPS = 40` → 0,1 tr/s moteur = **6 tr/min moteur**, 1,2 tr/min VIC, 7,2°/s.
- Course complète 500 pas = 12,5 s (12,9 s avec 15 pas de dépassement). Exigence terrain ≤ 15 s
  → vitesse mini ≈ 34 pas/s pour 515 pas.
- Pas générés par `time.sleep()` (demi-période 12,5 ms) + callback LED après chaque pas bloquant :
  vitesse réelle **jamais mesurée** sur le RPi (elle ne peut être que ≤ 40 pas/s).

## Couple (calcul, non mesuré)

- À 6 tr/min le moteur est proche de son couple de maintien (≈ 12 N·m).
- En sortie : 12 × 5 × 0,96 ≈ **57,6 N·m** → sous les 90 N·m du réducteur, **au-dessus des 38 N·m d'une pige**.
- Couple moteur maxi pour rester ≤ 38 N·m sur la pige : 38 / 4,8 ≈ **7,9 N·m**, soit ≈ 66 % du couple de
  maintien. Estimation du courant correspondant : ≈ 66 % de 6 A ≈ 4 A *(approximation couple ∝ courant,
  à vérifier sur la courbe et la table de courant du DM860H)*.
- Ce que fait un pas-à-pas qui pousse contre une pige : au-delà du couple de décrochage il perd le
  synchronisme et **claque** (le rotor recule de jusqu'à 4 pas entiers à chaque décrochage). Le bruit de
  claquement en butée est donc attendu ; les dépassements courts (15 pas) limitent sa durée, pas sa force.
