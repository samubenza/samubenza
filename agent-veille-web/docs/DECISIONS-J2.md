# Décisions d'interprétation et blocage réseau — Jalon J2

## 0. Blocage réseau de l'environnement de développement (important)

La session dans laquelle ce jalon a été développé (Claude Code) applique
une politique d'égress réseau qui **n'autorise qu'une liste précise
d'hôtes** (PyPI, npm, GitHub, l'API Anthropic...) — confirmée via
`curl` et via l'outil `WebFetch`, qui renvoient tous deux une erreur
d'autorisation (403 / `EGRESS_BLOCKED`) pour tout site tiers (testé sur
xkcd.com, en.wikipedia.org, hnrss.org). Les instructions de cet
environnement sont explicites : ne pas contourner une politique d'égress,
la signaler.

**Conséquence** : le Collecteur (M4), l'Extracteur (M5) et le calcul de
clé logique (M6) sont entièrement implémentés avec les vraies bibliothèques
(`feedparser`, `BeautifulSoup`, `requests`) et **validés par des tests
automatisés qui font tourner ce code réel sur des fixtures RSS/HTML
représentatives** des trois catégories demandées (voir
`tests/test_pipeline_collecte_j2.py` et `tests/fixtures/`). Une preuve
d'exécution *live* contre trois vraies URL a été obtenue depuis cette
session : le pipeline tente bien de vraies requêtes HTTP vers
`hnrss.org`, `en.wikipedia.org` et `xkcd.com`, échoue au niveau du proxy
(`403 Forbidden` du tunnel), et journalise proprement l'échec sans jamais
bloquer la veille (F3.4) — la chaîne complète fonctionne, seul le dernier
maillon (accès Internet sortant) est indisponible ici.

Le run continu de 48 h prévu par le critère de validation (§12.3) doit
donc être lancé **depuis un environnement avec un accès Internet normal**
(votre machine, par exemple), à l'aide de `scripts/collecte_continue.py`
fourni à cet effet — voir le README pour le mode d'emploi.

## 1. `F6.1` : la nature (provisoire/définitif) fait partie de la clé de
   `RÉSULTAT_ÉVÉNEMENTIEL` — et résout l'ambiguïté notée en J1

Le tableau F6.1 inclut explicitement la nature du résultat dans la clé
logique de ce patron : *« événement + date (+ nature du résultat :
provisoire / définitif) »*. Une Occurrence provisoire et une Occurrence
définitive du même événement produisent donc, une fois M6 réellement
implémenté, **deux Cibles distinctes**.

C'est en fait la clé qui résout proprement l'ambiguïté relevée dans
`docs/DECISIONS-J1.md` (point 1) entre le diagramme d'états (qui montre
`FILTRÉE` comme état terminal d'une Cible) et F7.2 (qui parle de
l'Occurrence). Avec la clé F6.1 : la Cible « provisoire » ne recevra par
construction **jamais** d'Occurrence définitive (elle a une clé
différente) — elle peut donc légitimement finir `FILTRÉE` de façon
terminale, exactement comme le montre le diagramme. La Cible
« définitive », elle, suit le cycle normal RG-01→RG-03. **Aucune
modification du moteur (moteur.py, jalon J1) n'a été nécessaire** : ce
comportement émerge naturellement du bon calcul de clé.

En J2, le pipeline (`pipeline.py`) ne détecte pas encore le caractère
provisoire sur un simple listing HTML (qui ne publie en général que des
résultats déjà consolidés) : la nature y est fixée à *"définitif"*. Un
flux publiant des scores en direct devra positionner `Caractere` en amont
— hors périmètre de J2, qui porte sur RSS + listing statique.

## 2. Score fixe en attendant M7

F7.1 (scoring pondéré : correspondance aux critères, fraîcheur, fiabilité
de source, pénalités...) est un module à part entière (M7), explicitement
hors périmètre des jalons J1/J2. `SourceCollecte.score_defaut` (80 par
défaut) sert de score de substitution le temps que M7 soit implémenté
(Lot 2). Le moteur RG-01–RG-07 (J1), lui, reste inchangé et continue de
appliquer le seuil de pertinence (F7.2) sur ce score, quelle que soit son
origine.

## 3. Extraction HTML : générique au niveau du Collecteur, spécifique au
   niveau de la Source

Le Collecteur (`collecteur.py`) ne sait lire aucune page HTML en
particulier — il reçoit une fonction `extraire_candidats` fournie par la
configuration de chaque Source (F5.1 : « selon le patron », concrètement
selon la structure de la page). C'est le choix qui respecte le mieux la
neutralité de domaine (§1.3) : le moteur générique ignore tout du
« résultat sportif » ou du « chapitre de blog » ; seule la configuration
d'une Source donnée sait où se trouvent le titre, la date et l'URL sur
**cette** page précise.

## 4. Numéro de série : extrait du titre, puis, à défaut, de l'URL

`cle_logique.extraire_numero` cherche d'abord un motif générique de
numérotation dans le titre (vocabulaire générique : « chapitre »,
« épisode », « numéro »...), puis retombe sur un segment numérique de
l'URL canonique (motif très répandu pour les contenus sériels :
`.../2960/`). Le nom de la série lui-même (F6.1 : « élément ») est une
donnée de configuration de la Source (`SourceCollecte.nom_serie`), pas une
extraction par item : le nom d'une série ne change pas d'un chapitre à
l'autre, il n'y a donc rien à en déduire à chaque cycle.

## 5. Persistance

Ce jalon garde l'Orchestrateur en mémoire (comme en J1) : un run de 48 h
via `scripts/collecte_continue.py` tourne dans un seul processus continu
et écrit le journal au fil de l'eau dans un fichier JSON Lines. La
persistance robuste aux redémarrages (SQLite, §12.1 de la spécification)
est repoussée aux jalons suivants (J3 introduit l'interface de pilotage,
qui a besoin d'un stockage durable) — non nécessaire pour valider J2 tel
que formulé au §12.3.
