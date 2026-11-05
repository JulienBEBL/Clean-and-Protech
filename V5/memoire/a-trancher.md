# Contradictions à trancher

> Relevées le 2026-11-05 en lisant doc, code et mémoires. Rien n'a été modifié dans le code.
> Une fois tranchée, déplacer la ligne dans `decisions.md` et corriger la source fautive.

| # | Où | Contradiction | Proposition |
|---|---|---|---|
| ~~1~~ | ~~`CLAUDE.md` : purge 5 s / garde 7,5 s vs `config.py` 10 / 10~~ | **Tranché 2026-11-05** : 10 / 10 voulus par le client, `CLAUDE.md` aligné | — |
| 9 | Piges : 38 N·m (prompt, `CLAUDE.md`) vs **35 N·m** (fabricant, Julien 2026-11-05) | **35 N·m retenu**, `CLAUDE.md` aligné | — |
| 2 | `CLAUDE.md`, tableau des programmes | PRG3 « INVERSION auto 60s » ; `PRG3_VIC_INVERT_PERIOD_S = 50` | Corriger en « 50 s en butée » |
| 3 | `CLAUDE.md`, API `IOBoard` | `read_vic_selector()` « 1=DEP, 2=NEU, 3=RET » ; câblage réel 2 positions : 0=NEUTRE, 1=DEPART, 2=RETOUR | Corriger la doc |
| 4 | `CLAUDE.md`, validations terrain | « Rodage VIC ✅ Validé » — validé **avant** le réducteur 5:1 | Repasser en « à revalider » |
| 5 | `tests/test_vic.py` (docstring) | `h` = « DEPART→RETOUR×3→NEUTRE » : ancien homing | Corriger le texte |
| 6 | `programs.py` docstrings | Prg1/Prg5 « VIC laissée en place » alors que `stop()` ramène en NEUTRE ; `_anchor_and_move_vic` « jamais dans stop() » alors que PRG3 `stop()` l'utilise | Corriger les docstrings |
| 7 | Mémoire Claude Code `machine-100-pct-auto` | Parle de 90 s et de `V5/BACKLOG.md` (inexistant) ; `CLAUDE.md` dit 60 s (3 × 2 × 10 s) | Garder 60 s |
| 8 | Mémoire Claude Code `project_v5_created` | Adresses MCP « non vérifiées », K = 10.84 fixe ; `CLAUDE.md` : MCP validés, K vivant | Mémoire périmée — `CLAUDE.md` fait foi |
