# Mémoire projet — V5 (index)

> **Toute session Claude lit ce fichier au démarrage**, puis les fichiers utiles au sujet.
> `V5/CLAUDE.md` reste la doc technique de référence (architecture, API, constantes).
> Ici : ce qui ne se déduit pas du code — terrain, matériel, décisions, risques, façon de travailler.

## Fichiers

| Fichier | Contenu |
|---|---|
| [regles-travail.md](regles-travail.md) | Droits git, flux PC → RPi, règles à ne pas enfreindre, essais à sec |
| [materiel-vic.md](materiel-vic.md) | Moteur, driver, réducteur, piges, calculs de couple et de vitesse |
| [journal-terrain.md](journal-terrain.md) | Entrées **datées** : symptômes, mesures, réglages essayés et résultats |
| [decisions.md](decisions.md) | Décisions **datées** et leur raison |
| [risques-ouverts.md](risques-ouverts.md) | Risques et points ouverts encore vivants |
| [a-trancher.md](a-trancher.md) | Contradictions relevées entre doc, code et mémoire — en attente de Julien |
| [procedure-mesure-course.md](procedure-mesure-course.md) | Mesure de la course réelle VIC — à faire à la prochaine visite |
| `sources/` | Documents d'origine conservés tels quels (prompt de mission, mémo risques du 21/10) |

## Règles de tenue

- Un fait appris = une ligne dans le bon fichier, **datée** si c'est du terrain ou une décision.
- Ce qui devient faux est **corrigé ou barré avec la date**, pas laissé en contradiction.
- Pas de doublon avec `CLAUDE.md` : on y renvoie.
- Commité et poussé avec le code (`docs(VIC): …` / `feat(VIC): …`).
- Format des dates : AAAA-MM-JJ.
