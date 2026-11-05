# Matériel VIC

> Source : prompt de mission (2026-11-05) et `CLAUDE.md`. Les infos détaillées moteur / réducteur /
> mécanique / piges que Julien doit envoyer seront ajoutées ici, datées.

## Chaîne cinématique (depuis 2026-10-21)

| Élément | Détail |
|---|---|
| Driver | JK-DM860H. DIP relevés 2026-11-05 : **RMS 6,00 A / pic 7,20 A**, **SW4 OFF**, SW5..SW8 ON = 400 pulses/tour. **Alim 48 VDC** |
| Signaux | STEP GPIO 27, DIR GPIO 17, ENA GPIO 22 (actif bas). `lgpio`, gpiochip4, RPi 5 |
| Moteur | STEPPERONLINE 34IP65-120 : NEMA 34, 12 N·m de maintien, 6 A. Courbe constructeur ≈ 9 N·m à 100 tr/min (60 V, 2000 µpas) |
| Réducteur | STEPPERONLINE RYG34-G5 : planétaire **à renvoi d'angle**, 5:1, η 96 %, jeu ≤ 10 arcmin, 90 N·m admissibles (180 N·m momentané) |
| VIC | Boisseau **bronze** tournant dans un corps **aluminium non anodisé**. Un joint sur la VIC, **hors zone d'eau**, côté réducteur : il empêche l'eau du corps de sortir par le passage de l'axe |
| Butées | 2 piges **acier emmanchées dans la VIC**, Ø ≈ 10 à 12 mm (non confirmé), à **≈ 30 mm de l'axe**. Elles butent aux extrémités d'un **oblong circulaire usiné dans le corps alu** → course **90° théorique** (réelle jamais mesurée). **≈ 35 N·m chacune** (fabricant ; remplace les 38 N·m cités avant). Aucun capteur de position. État des piges / de l'oblong invisible sans démontage |
| Hydraulique | **≈ 500 L/min** arrivent sur la VIC : il faut un couple très élevé pour la faire tourner → **courant driver au maximum obligatoire** (Julien, 2026-11-05) |
| Driver coupé | **Si le driver est désactivé, l'eau peut faire tourner la VIC** (Julien, 2026-11-05) |
| Accès | **Impossible de tourner la VIC ou le moteur à la main**, de quelque côté que ce soit (intégration méca) |

**Précision exigée : ±1°, idéalement ±0,5°** (= 2,8 pas). Ancienne règle de Julien (avant le réducteur) :
envoyer la VIC avec 10 % de course en plus pour être sûr de taper la butée.

SW4 OFF : en principe réduction du courant à l'arrêt sur cette famille de driver (à confirmer sur l'étiquette).
Sans effet aujourd'hui : le code désactive le driver (ENA) entre deux mouvements.

Inconnus à ce jour : couple nécessaire pour faire tourner la VIC (décollage et en mouvement, à sec et en eau),
géométrie et fixation des piges, effort de l'eau sur la VIC quand le driver est désactivé.

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
- En sortie : 12 × 5 × 0,96 ≈ **57,6 N·m** → sous les 90 N·m du réducteur, **1,65 × les 35 N·m d'une pige**.
- Effort sur la pige à 30 mm : 57,6 / 0,030 ≈ **1 900 N**, pour ≈ 1 170 N admissibles (35 / 0,030).
- Couple moteur maxi pour rester ≤ 35 N·m sur la pige : 35 / 4,8 ≈ **7,3 N·m**, soit ≈ 61 % du couple de
  maintien. Courant correspondant ≈ 61 % de 6 A ≈ **3,6 A RMS** *(approximation couple ∝ courant,
  à vérifier sur la table de courant du DM860H)*. Mais ce courant plafonne aussi le couple disponible pour
  faire tourner la VIC : il faut connaître son couple de décollage.
- Rayon : pour un couple donné, F = C / r → plus la pige est loin de l'axe, **moins** elle prend d'effort.
  Le rapport de surcharge (1,65) est le même en couple ou en effort ; le rayon n'y change rien.
- Cisaillement d'une pige Ø 10 sous 1 900 N ≈ 24 MPa : très loin de la limite d'un acier. Les 35 N·m du
  fabricant viennent donc probablement d'autre chose (emmanchement dans le bronze, matage de l'alu non
  anodisé aux extrémités de l'oblong) — **origine de la valeur à confirmer**.
- À 7,2°/s l'énergie cinétique à l'impact est négligeable : la surcharge est **statique** (couple de
  décrochage appliqué tant que le moteur pousse), pas un choc.
- Ce que fait un pas-à-pas qui pousse contre une pige : au-delà du couple de décrochage il perd le
  synchronisme et **claque** (le rotor recule de jusqu'à 4 pas entiers à chaque décrochage). Le bruit de
  claquement en butée est donc attendu ; les dépassements courts (15 pas) limitent sa durée, pas sa force.
