# Procédure — mesurer la course réelle de la VIC (prochaine visite)

> Préparée le 2026-11-05. La course réelle est ≠ 90° (500 pas théoriques), écart inconnu.
> Elle conditionne RETOUR (= course) et NEUTRE (= milieu de la course réelle, décision 2026-11-05).

## Conditions

- Pompe à l'arrêt (sélecteur variateur sur OFF par sécurité). Pas besoin d'eau.
- Service `main.py` arrêté (les GPIO doivent être libres). Environ 5 minutes.
- Être près de la VIC pour **entendre** le claquement en butée.

## Commandes sur le Raspberry

```bash
systemctl list-units | grep -i clean
sudo systemctl stop <nom-du-service>
cd /home/bebl/Desktop/Clean-and-Protech/V5
python tests/test_course_vic.py
```

## Déroulé

1. Entrée pour démarrer. La VIC va en butée DEPART sur 560 pas : **claquement normal**
   (jusqu'à ≈ 14 s si elle y est déjà).
2. Elle monte seule à 400 pas (≈ 72°), sans toucher la pige RETOUR.
3. À chaque Entrée : +2 pas (0,36°). Écouter.
4. **Au premier claquement** : taper `c` puis Entrée → le script affiche `COURSE REELLE ≈ N pas`.
5. Le script ramène la VIC en DEPART. **Refaire une 2e fois** pour confirmer (écart ≤ 2 à 4 pas attendu).
6. Relancer le service : `sudo systemctl start <nom-du-service>`.

Arrêt à tout moment : `q` + Entrée, ou Ctrl+C.

## Ensuite

- Me donner les 2 valeurs. Je mets `VIC_TOTAL_STEPS` à jour dans `config.py` (NEUTRE et RETOUR suivent).
- Changer la course invalide la position mémorisée (course différente) : le premier démarrage suivant
  fera un ancrage pleine course, c'est normal.
- Si la course dépasse 516 pas, revoir aussi la marge de l'ancrage pleine course.
