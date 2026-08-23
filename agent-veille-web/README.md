# Agent de Veille Web Autonome — Lot 1 / Jalon J1

Noyau logique de l'agent : modèle de données et machine à états
Cible/Occurrence (règles RG-01 à RG-07), tel que défini par la spécification
fonctionnelle (§4 M8, §6, §12.3).

**Portée de ce jalon (J1) :**
- ✅ Modèle de données : `Veille`, `Source`, `Cible`, `Occurrence`, `Feedback`,
  journal d'audit (`EvenementJournal`).
- ✅ Machine à états de l'orchestrateur d'ouverture (`Orchestrateur`),
  implémentant RG-01 à RG-07.
- ✅ Aucun accès réseau, aucune extension navigateur : les occurrences sont
  fournies par les appelants (tests), comme le prévoit le collecteur/
  extracteur (M4/M5/M6) qui n'arrive qu'au jalon J2.
- ✅ Les quatre parcours du §5 de la spécification, rejoués en simulation
  avec des occurrences fictives, comme jeu de tests de référence.

**Hors périmètre (jalons suivants) :** interface de pilotage (J3), module
M2 d'interprétation/validation de la Directive (J4), service Windows (J5),
extension Chromium (J6), lancement du navigateur et reprise après absence
(J7).

## Structure

```
src/veille_agent/
  models.py   — modèle de données (§6)
  moteur.py   — Orchestrateur : RG-01 à RG-07 (§4, M8)
tests/
  test_parcours_5_1_*.py   — §5.1 Sortie sérielle (manga)
  test_parcours_5_2_*.py   — §5.2 Actualité thématique (voyage)
  test_parcours_5_3_*.py   — §5.3 Résultat événementiel (sport)
  test_parcours_5_4_*.py   — §5.4 Résultat événementiel (loterie)
  test_regles_gestion.py   — compléments RG-04/05/07 non couverts par les
                              quatre parcours pris isolément
docs/
  DECISIONS-J1.md      — choix d'interprétation pris pour lever les
                          ambiguïtés de la spécification à ce stade
  spec/specification-v1.4.md — copie de référence de la spécification
                          fonctionnelle (source de vérité : le document
                          fourni par le commanditaire)
```

Conformément à la consigne §1.3/§12.5.2 de la spécification, aucune ligne de
ce code ne mentionne un domaine particulier (« manga », « loto », « football »,
etc.) : le même moteur générique traite les quatre parcours du §5, qui ne
servent qu'à nommer les scénarios de test.

## Lancer les tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install pytest
pytest -v
```

**Critère de validation du jalon (§12.3)** : *« Les quatre parcours du §5,
rejoués automatiquement avec des occurrences fictives, produisent exactement
les ouvertures attendues et aucune autre. »* — vérifié par
`tests/test_parcours_5_*.py`, où chaque assertion sur
`Orchestrateur.occurrences_ouvertes()` liste explicitement les seules
Occurrences censées avoir été ouvertes.
