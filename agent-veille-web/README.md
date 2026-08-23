# Agent de Veille Web Autonome — Lot 1 / Jalons J1-J2

Noyau logique de l'agent (J1) + collecteur RSS/HTML réel, extraction et
déduplication (J2), tels que définis par la spécification fonctionnelle
(§4 M4-M6, M8, §6, §12.3).

**Portée de J1 :**
- ✅ Modèle de données : `Veille`, `Source`, `Cible`, `Occurrence`, `Feedback`,
  journal d'audit (`EvenementJournal`).
- ✅ Machine à états de l'orchestrateur d'ouverture (`Orchestrateur`),
  implémentant RG-01 à RG-07. Aucun accès réseau, aucune extension.
- ✅ Les quatre parcours du §5 de la spécification, rejoués en simulation
  avec des occurrences fictives, comme jeu de tests de référence.

**Portée de J2 :**
- ✅ Collecteur (M4) : flux RSS/Atom (`feedparser`) et pages de listing HTML
  (`BeautifulSoup`), avec politesse technique obligatoire (F4.5 : robots.txt,
  1 requête/10 s par domaine, `User-Agent` identifiable, back-off sur 429/503).
- ✅ Extracteur (M5) : normalisation titre/URL canonique/date de publication,
  repli sur la date de détection si absente (F5.4).
- ✅ Identification de Cible et déduplication (M6) : calcul de la clé
  logique par patron (F6.1), sans changement du moteur RG-01–RG-07 de J1.
- ✅ Pipeline M4→M5→M6→M8 (`pipeline.py`) testé sur trois catégories de
  sources réelles (RSS, listing HTML « résultat événementiel », listing
  HTML « sortie sérielle »), avec fixtures réalistes et vraie exécution de
  `feedparser`/`BeautifulSoup`. **Toujours aucune ouverture d'onglet.**
- ⚠️ Le run continu de 48 h sur trois **vrais** sites Internet (critère
  §12.3) n'a pas pu être exécuté *depuis cette session de développement* :
  l'accès réseau sortant y est restreint par une politique d'égress qui
  n'autorise qu'une liste d'hôtes (PyPI, npm, GitHub...). Voir
  `docs/DECISIONS-J2.md` §0 et `scripts/collecte_continue.py` pour lancer
  ce run depuis un environnement avec accès Internet normal.

**Hors périmètre (jalons suivants) :** interface de pilotage (J3), module
M2 d'interprétation/validation de la Directive (J4), service Windows (J5),
extension Chromium (J6), lancement du navigateur et reprise après absence
(J7). Le scoring pondéré complet (M7, F7.1) reste hors périmètre J1/J2 —
un score fixe en tient lieu (voir `docs/DECISIONS-J2.md` §2).

## Structure

```
src/veille_agent/
  models.py       — modèle de données (§6)
  moteur.py       — Orchestrateur : RG-01 à RG-07 (§4, M8) — J1
  collecteur.py    — Collecteur : RSS/Atom + listing HTML, politesse F4.5 — J2 (M4)
  extracteur.py    — normalisation des candidats bruts, F5.1/F5.4 — J2 (M5)
  cle_logique.py   — calcul de la clé logique par patron, F6.1 — J2 (M6)
  pipeline.py      — assemble M4→M5→M6→M8 en un cycle de collecte — J2
scripts/
  collecte_continue.py — lance le pipeline en continu sur 3 sites réels
                          (à exécuter hors de cette session, voir plus bas)
tests/
  test_parcours_5_1_*.py        — §5.1 Sortie sérielle (J1, simulation)
  test_parcours_5_2_*.py        — §5.2 Actualité thématique (J1, simulation)
  test_parcours_5_3_*.py        — §5.3 Résultat événementiel (J1, simulation)
  test_parcours_5_4_*.py        — §5.4 Résultat événementiel (J1, simulation)
  test_regles_gestion.py        — compléments RG-04/05/07 (J1)
  test_pipeline_collecte_j2.py  — Collecteur/Extracteur/déduplication (J2),
                                   sur fixtures RSS/HTML réalistes
  fixtures/                     — RSS et HTML représentatifs des 3 catégories
docs/
  DECISIONS-J1.md      — choix d'interprétation pris pour J1
  DECISIONS-J2.md       — choix d'interprétation pris pour J2 + blocage réseau
  spec/specification-v1.4.md — copie de référence de la spécification
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

**Critère de validation J1 (§12.3)** : *« Les quatre parcours du §5,
rejoués automatiquement avec des occurrences fictives, produisent exactement
les ouvertures attendues et aucune autre. »* — vérifié par
`tests/test_parcours_5_*.py`, où chaque assertion sur
`Orchestrateur.occurrences_ouvertes()` liste explicitement les seules
Occurrences censées avoir été ouvertes.

**Critère de validation J2 (§12.3)** : *« En laissant tourner sur trois
sites réels pendant 48 h, le journal montre les Cibles correctement
identifiées et dédupliquées — toujours sans ouvrir d'onglet. »* — la
logique est vérifiée par `tests/test_pipeline_collecte_j2.py` (RSS/HTML
réels traités par `feedparser`/`BeautifulSoup`, sur fixtures) ; le run réel
de 48 h doit être lancé séparément (voir ci-dessous).

## Lancer le run réel de 48 h (J2)

Depuis un environnement avec un accès Internet normal (pas cette session
de développement — voir `docs/DECISIONS-J2.md` §0) :

```bash
pip install -e .
python scripts/collecte_continue.py --duree-heures 48 --intervalle-min 15
```

Le script journalise chaque cycle dans `journal_collecte_j2.jsonl`
(un objet JSON par ligne : veille, type d'événement, détail, horodatage) et
peut être interrompu à tout moment (Ctrl+C) sans perdre l'historique déjà
écrit. Les trois sources par défaut (Hacker News en RSS, un tableau de
résultats Wikipédia, l'archive xkcd) sont des exemples — ajustez les
sélecteurs HTML dans le script si la structure d'une page a changé (F3.4).
