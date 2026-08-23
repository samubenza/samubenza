# Décisions d'interprétation — Jalon J1

La spécification (v1.4) est précise sur le comportement observable, mais
laisse quelques détails d'implémentation ouverts. Voici les choix retenus
pour ce jalon, à confirmer ou amender par le commanditaire.

## 1. `FILTRÉE` s'applique à l'Occurrence, pas à la Cible

Le diagramme d'états (§4, M8) montre `DÉTECTÉE --> FILTRÉE` au niveau de la
Cible, avec `FILTRÉE` comme état terminal. Mais F7.2 dit explicitement :
*« Sinon **elle** [l'Occurrence] est enregistrée en statut `FILTRÉE` »*, et
le parcours §5.3 montre une Cible qui reçoit d'abord un résultat provisoire
filtré, puis un résultat définitif qui s'ouvre normalement — ce qui est
impossible si la Cible elle-même devenait `FILTRÉE` de façon terminale.

**Décision retenue** : le filtrage (F7.2) s'applique à l'**Occurrence**
uniquement. La Cible reste `DÉTECTÉE` tant qu'aucune Occurrence éligible n'a
été retenue ; le diagramme du §4 doit se lire comme une vue simplifiée. Une
future itération pourra introduire un état `FILTRÉE` réellement terminal
pour une Cible dont on sait qu'elle ne produira jamais de résultat
conforme (ex. après péremption, cf. F12.5.1 — hors périmètre J1).

## 2. Score composite (F7.1) simulé en entrée, pas calculé par ce module

M7 (moteur de pertinence, F7.1) combine plusieurs facteurs pour calculer le
score d'une Occurrence, dont le score de fiabilité de la source. Ce calcul
pondéré n'est pas dans le périmètre de J1 (qui porte sur RG-01 à RG-07, pas
sur M7). Le score est donc un paramètre d'entrée de
`Orchestrateur.detecter_occurrence(...)`, comme le préconise l'énoncé du
jalon (« occurrences fictives »). Les tests du parcours §5.1 (Cible 1192)
composent volontairement ce score à partir du score de fiabilité appris,
pour illustrer fidèlement F10.2 sans anticiper sur l'implémentation de M7.

## 3. Garde-fou des 30 ouvertures/jour restreint au mode `CIBLÉ`

Le tableau RG-07 ne mentionne le garde-fou de 30 ouvertures/jour que sur la
ligne `CIBLÉ`. Les modes `LARGE` et `HYBRIDE` ont déjà un plafond
fonctionnel strict (10/jour par défaut) : leur appliquer en plus le
garde-fou anti-anomalie n'a pas de sens et n'est pas prévu par le texte. Il
n'est donc actif qu'en mode `CIBLÉ`.

## 4. Reprise d'ouverture après délai de courtoisie (RG-05)

La spécification décrit le délai de courtoisie comme une contrainte
*avant toute nouvelle ouverture pour la même Cible*, mais ne précise pas le
mécanisme qui relance la tentative une fois le délai écoulé, en l'absence de
toute nouvelle détection. Dans un service réel, c'est un cycle de collecte
(M4) qui s'en chargerait. En J1 (sans collecteur), `Orchestrateur.
avancer_temps(...)` — qui simule l'écoulement du temps entre deux détections
— retente aussi l'ouverture des Cibles `EN_ATTENTE_FEEDBACK` dont le délai de
courtoisie est écoulé et qui ont des Occurrences en réserve.

## 5. Portée de M1/M3/M4/M5/M6/M9/M10/M11 dans J1

Seuls les champs de `Veille`/`Source` strictement nécessaires à
l'exécution de RG-01–RG-07 sont repris ici (pas de `Directive`,
`Interprétation`, étiquettes, modes de restitution, etc. — ces éléments
appartiennent aux jalons J3/J4). L'apprentissage du score de source
(F10.1/F10.2) est implémenté a minima (ajustement +5/-5 borné [0, 100]) pour
permettre aux parcours du §5 de produire l'ordre attendu ; le profil de
pertinence thématique (F10.4, Lot 2) n'est pas implémenté.
