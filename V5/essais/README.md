# Essais de la prochaine visite — VIC (préparés le 2026-11-09)

But : vérifier la mise à jour du 9/11 sur la machine, mesurer la course réelle de
la VIC, et savoir quoi observer si le blocage du 8/11 revient.

## Règles pour ces essais

- **Scripts `essai_*.py` : ouvrir dans Geany, lancer avec F5.**
- **Jamais Ctrl+C** (ça ferme le terminal Geany). Partout : `q` + Entrée pour quitter.
  Arrêt d'urgence réel = coupure électrique, pas le clavier.
- Chaque script finit par un **cadre `#####`** à prendre en capture d'écran, puis attend
  Entrée avant de fermer. Copie aussi dans `V5/essais/resultats/` (non versionné).
- **`main.py` ne se lance pas depuis Geany** : il tourne par le service. Seul
  `essai_2_course.py` demande d'arrêter le service (il bouge la VIC).
- Les essais à sec : **pompe sur OFF au variateur** pour PRG2, PRG4, PRG5. Les sécurités
  débit vont se déclencher : c'est normal, ce n'est pas un défaut.
- Si possible, un **repère** (feutre ou adhésif) sur l'accouplement ou l'axe du moteur :
  c'est le seul moyen de voir si la VIC bouge quand il n'y a pas d'eau.

Commandes terminal utiles (pas Geany) :

```bash
cd /home/bebl/Desktop/Clean-and-Protech && git pull
systemctl list-units --type=service | grep -i -E 'clean|serena|main'
sudo systemctl stop <nom-du-service>
sudo systemctl start <nom-du-service>
```

## Ordre et durée (≈ 1 h 15 à sec)

| N° | Essai | Durée | Service | Captures à m'envoyer |
|---|---|---|---|---|
| E0 | Mise à jour + état du logiciel | 5 min | tourne | `essai_1_infos.py` |
| E1 | Démarrage, homing | 3 min | tourne | `essai_3_logs.py` (page du homing) |
| E2 | Course réelle VIC | 15 min | **arrêté** | `essai_2_course.py` (cadre résultat) |
| E3 | PRG3 à sec (VIC fixe en DEPART) | 8 min | tourne | `essai_3_logs.py` (page PRG3) |
| E4 | PRG1 à sec | 3 min | tourne | — |
| E5 | PRG2 puis PRG4, pompe OFF | 6 min | tourne | `essai_3_logs.py` (pages PRG2/PRG4) |
| E6 | PRG5, pompe OFF | 3 min | tourne | `essai_3_logs.py` (page PRG5) |
| E7 | Écran LCD et boutons | pendant E3–E6 | tourne | photo de l'écran si anomalie |
| E8 | Température moteur / driver | 2 min | tourne | valeurs notées |
| E9 | Avec eau (si plombier) : reproduction du 8/11 | 45 min | tourne | `essai_3_logs.py` + vidéo si défaut |

Si le blocage revient à n'importe quel moment : **protocole D** (en bas), avant toute coupure.

**Nouveau depuis le 2026-11-10 — ancrage alterné.** À chaque lancement de programme, la VIC va
en butée **une fois côté RETOUR, une fois côté DEPART** (le 1er après le démarrage : RETOUR).
Un claquement bref côté RETOUR avant un programme qui demande DEPART est donc **normal**.
Le log dit lequel : `VIC anchor+move terminé : ancrage RETOUR, position 0 pas`.
Tant que la course n'est pas mesurée (E2), une position peut être décalée de quelques degrés
une fois sur deux : à signaler, mais attendu.

---

## E0 — Mise à jour et état du logiciel

1. Sur le PC : la mise à jour du 9/11 est commitée et poussée.
2. Sur le RPi, dans un terminal : `git pull`, puis `sudo systemctl restart <service>`.
3. Geany : `essai_1_infos.py`, F5.

**Attendu** : commit = celui du PC ; `Modifs RPi : aucune (propre)` ;
`Réarmement driver : True` ; `PRG3 inversion VIC : False` ; `Cache LCD : True`.
Sinon : ne pas continuer, m'envoyer la capture.

## E1 — Démarrage et homing

**Au tout premier démarrage de la journée** (machine froide, comme le 8/11 où la VIC n'a pas
bougé) : être à côté de la VIC. Noter si le moteur **claque sur place**, **ronfle** ou reste
**silencieux**, et l'état du voyant du DM860H. C'est l'observation qui manquait.

Au redémarrage du service : écran d'accueil 5 s, puis « Preparation ... » ≈ 1 min 30.

- **Écouter** : un claquement long au début (ancrage, jusqu'à ≈ 14 s), des allers-retours
  silencieux, un claquement bref côté RETOUR puis côté DEPART, puis montée en NEUTRE.
- **Attendu** : écran « CHOISIR PROGRAMME ». Ligne 4 : `VIC:NEUTRE` quand le sélecteur est
  au neutre ; tourner le sélecteur → `DEPART` / `RETOUR` suivent.
- Capture : `essai_3_logs.py`, dernier log, commencer par le début → page avec
  `VIC homing — terminé` et `Homing VIC — terminé en …s`.

## E2 — Course réelle de la VIC (service ARRÊTÉ)

1. `sudo systemctl stop <service>`.
2. Geany : `essai_2_course.py`, F5. Suivre l'écran :
   - ancrage DEPART (claquement normal) ;
   - montée rapide à 440 pas, puis **+2 pas à chaque Entrée** ;
   - au **premier contact** avec la pige RETOUR (claquement, ou repère moteur qui ne
     tourne plus) : `c` + Entrée ;
   - même chose dans l'autre sens, vers DEPART ;
   - proposer une 2e mesure : `o` (recommandé), puis Entrée.
3. Capture du cadre `RESULTAT COURSE VIC`.
4. `sudo systemctl start <service>` (le homing repart).

**Ce que la mesure décide :**
- Je mets `VIC_TOTAL_STEPS` = course mesurée dans `config.py` (sur le PC). NEUTRE reste la
  moitié de la course.
- **Ancrage alterné DEPART / RETOUR** : avec la course réelle dans `config.py`, NEUTRE est
  le même qu'on parte de DEPART ou de RETOUR. L'alternance devient possible si l'écart
  entre les mesures est ≤ 4 pas (≈ 0,7°).
- Refaire la mesure **à chaque visite** : une course qui augmente = usure des piges ou de
  l'oblong.

Testé sur PC (faux moteur, courses 486 / 500 / 520) : résultat = course + 1 pas.

## E3 — PRG3 à sec : VIC fixe en DEPART

1. Lancer PRG3 (pas de pompe dans ce programme). Écran de consignes 10 s.
2. Pendant « Demarrage... » (le premier programme après le démarrage ancre côté RETOUR,
   puis descend en DEPART ≈ 19 s ; le suivant ancrera côté DEPART) :
   - **Réarmement du driver** : ≈ 2,5 s pendant lesquelles le moteur est relâché.
     Un léger bruit ou un petit mouvement est possible, rien de plus.
   - Ancrage : bref claquement côté RETOUR ou côté DEPART selon le tour.
3. Laisser tourner **5 min**. **Attendu** : la VIC **ne bouge plus** (repère immobile).
   Le log doit montrer `ancrage RETOUR` puis `ancrage DEPART` en alternance d'un programme à l'autre.
   Air 6 s / 2 s. EGOUTS : fermée 30 s, ouverte 15 s, en boucle.
4. Arrêter PRG3 (bouton). **Attendu** : la VIC monte en NEUTRE (≈ 6 s, **sans** claquement).
5. Capture `essai_3_logs.py`, fin du log : lignes
   `VIC driver — réarmement : ENA inactif 2s puis actif 0.5s`,
   `PRG3 — VIC fixe en DEPART pendant tout le programme`, puis à l'arrêt `VIC → 250 pas`.

## E4 — PRG1 à sec

Lancer PRG1, laisser 1 min, arrêter. **Attendu** : réarmement + ancrage au démarrage,
VIC en DEPART immobile, NEUTRE à l'arrêt.

## E5 — PRG2 puis PRG4, pompe OFF au variateur

Pour chacun : confirmer « CUVE PLEINE ? » (2e appui), attendre.
**Attendu** : réarmement, ancrage (RETOUR ou DEPART selon le tour) puis NEUTRE (≈ 6 s + 6 s), relais
pompe activé (pompe arrêtée au variateur), puis ≈ 13 s plus tard **« PLUS DE DEBIT /
Cuve vide »** : normal à sec. La VIC reste en NEUTRE.
Capture `essai_3_logs.py` : les deux démarrages (`VIC anchor+move`, `réarmement`).

## E6 — PRG5, pompe OFF

Sélecteur VIC sur **DEPART** avant le lancement. Lancer PRG5.
**Attendu** : VIC en DEPART. Puis, **dans les 15 premières secondes** (après, la sécurité
débit bloque tout pendant 60 s, puis arrête le programme — normal à sec) : passer le
sélecteur sur **RETOUR** et l'y laisser 2 s → la VIC part en RETOUR.
Capture `essai_3_logs.py` : `PRG5 — sélecteur VIC brut=1` puis
`PRG5 tick — sélecteur VIC 1→2 stable …`.

## E7 — Écran et boutons (pendant E3 à E6)

- Les écrans s'affichent normalement, sans caractères parasites. S'il y en a, ils
  doivent disparaître seuls en moins de 5 s (réécriture forcée).
- Les lignes clignotantes clignotent (PRG2, PRG4, PRG5), la durée avance chaque seconde.
- Un appui sur le bouton du programme en cours l'arrête **sans délai perceptible**.

## E8 — Température moteur et driver

Après au moins 30 min de machine sous tension (le driver est toujours alimenté) :
température du boîtier moteur et du radiateur du DM860H (thermomètre, ou main : chaud
supportable / brûlant). Repères : moteur ≤ 80–85 °C, ambiance du driver ≤ 50 °C.

## E9 — Avec eau (si plombier) : reproduction du 8/11

1. PRG1, puis PRG2 (eau, VIC NEUTRE), comme le 8/11.
2. **PRG3 pendant 30 min**, arrêt par le bouton.
3. Toucher moteur et driver (E8).
4. **PRG4** : pendant « Demarrage... », regarder le repère (DEPART puis NEUTRE) ; une fois
   la pompe lancée, l'eau doit passer en **transfert direct** (pas par les radiateurs).
5. **PRG5** : sélecteur NEUTRE → DEPART → NEUTRE → RETOUR → NEUTRE, 2 s minimum sur chaque
   position ; vérifier le sens de l'eau à chaque fois.
6. Capture `essai_3_logs.py` (fin du log).

---

## Protocole D — si la VIC est de nouveau « bloquée »

Ne **pas** couper le courant tout de suite. Dans l'ordre :

1. **Voyant rouge du DM860H** : filmer 10 s. Compter les clignotements.
   1 = surintensité ou court-circuit de phases ; 2 = surtension ; fixe ou autre = noter.
   Noter aussi si le voyant vert est allumé.
2. **Moteur** : silencieux ? ronflement ? claquement sur place ? Le repère bouge-t-il ?
   Dans le log : le dernier ancrage était-il `RETOUR` ou `DEPART` ?
3. Capture `essai_3_logs.py`, fin du log (les dernières lignes VIC).
4. **Arrêter le programme** (bouton), puis **relancer un programme** (PRG4 par exemple) :
   le réarmement du driver se fait pendant « Demarrage... ». La VIC repart-elle ?
   - oui → le réarmement par ENA marche : le défaut venait du driver ;
   - non → refaire 1 et 2, puis seulement la **coupure générale**.
5. Après la coupure : la VIC refonctionne-t-elle ? (comme le 8/11)

Tout noter, même « rien vu » : c'est ce qui manquait le 8/11.
