# Contradictions à trancher

> Relevées le 2026-11-05 en lisant doc, code et mémoires. Rien n'a été modifié dans le code.
> Une fois tranchée, déplacer la ligne dans `decisions.md` et corriger la source fautive.

| # | Où | Contradiction | Proposition |
|---|---|---|---|
| ~~1~~ | ~~`CLAUDE.md` : purge 5 s / garde 7,5 s vs `config.py` 10 / 10~~ | **Tranché 2026-11-05** : 10 / 10 voulus par le client, `CLAUDE.md` aligné | — |
| 9 | Piges : 38 N·m (prompt, `CLAUDE.md`) vs **35 N·m** (fabricant, Julien 2026-11-05) | **35 N·m retenu**, `CLAUDE.md` aligné | — |
| ~~2~~ | ~~PRG3 « 60s » vs 50 s~~ | **Corrigé 2026-11-05** | — |
| ~~3~~ | ~~API `read_vic_selector()`~~ | **Corrigé 2026-11-05** | — |
| ~~4~~ | ~~Rodage VIC « validé »~~ | **Corrigé 2026-11-05** (à revalider) | — |
| 5 | `tests/test_vic.py` (docstring) | `h` = « DEPART→RETOUR×3→NEUTRE » : ancien homing | Corriger le texte |
| ~~6~~ | `programs.py` docstrings — **corrigé 2026-11-05** | Prg1/Prg5 « VIC laissée en place » alors que `stop()` ramène en NEUTRE ; `_anchor_and_move_vic` « jamais dans stop() » alors que PRG3 `stop()` l'utilise | Corriger les docstrings |
| 7 | Mémoire Claude Code `machine-100-pct-auto` | Parle de 90 s et de `V5/BACKLOG.md` (inexistant) ; `CLAUDE.md` dit 60 s (3 × 2 × 10 s) | Garder 60 s |
| 8 | Mémoire Claude Code `project_v5_created` | Adresses MCP « non vérifiées », K = 10.84 fixe ; `CLAUDE.md` : MCP validés, K vivant | Mémoire périmée — `CLAUDE.md` fait foi |
