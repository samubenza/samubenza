"""Pipeline J2 : relie Collecteur (M4), Extracteur (M5), calcul de clé
logique (M6) et l'Orchestrateur (M8, RG-01 à RG-07 — jalon J1).

``executer_cycle`` réalise un cycle de collecte complet sur un ensemble de
Sources réelles et journalise le résultat (F11.6). Rien ici n'ouvre
d'onglet ni ne pilote de navigateur : l'Orchestrateur ne fait qu'un
changement d'état logique + une entrée de journal (voir moteur.py). Le
lancement effectif du navigateur (RG-10) est hors périmètre jusqu'au
jalon J7.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal, Optional

from bs4 import BeautifulSoup

from .cle_logique import cle_actualite_thematique, cle_resultat_evenementiel, cle_sortie_serielle, extraire_numero
from .collecteur import CandidatBrut, ErreurRobotsInterdit, Politesse, collecter_flux_rss, collecter_listing_html
from .extracteur import normaliser
from .models import Caractere, Patron
from .moteur import Orchestrateur


@dataclass
class SourceCollecte:
    """Configuration de collecte pour une Source réelle (M3/M4).

    ``extraire_candidats`` (uniquement pour ``LISTING_HTML``) sait lire la
    structure propre à CETTE source — c'est une donnée de configuration,
    jamais une connaissance intégrée au Collecteur générique (§1.3).
    """

    veille_id: str
    source_id: str
    type_collecte: Literal["RSS", "LISTING_HTML"]
    url: str
    extraire_candidats: Optional[Callable[[BeautifulSoup], list[CandidatBrut]]] = None
    # F1.3/F6.1 — nom de la série, uniquement pertinent pour SORTIE_SÉRIELLE ;
    # c'est une identité constante de la source, pas déduite de chaque item.
    nom_serie: Optional[str] = None
    # Score fixe attribué faute de moteur de pertinence pondéré (M7, F7.1),
    # explicitement hors périmètre du jalon J2.
    score_defaut: float = 80.0
    # Session HTTP à utiliser (injectable pour les tests — sans quoi une
    # ``requests.Session()`` réelle est créée par le Collecteur, M4).
    session: Optional[object] = None


def _identifier_cible(
    patron: Patron, source: SourceCollecte, titre: str, url: str, date_publication: datetime
) -> tuple[str, str]:
    """M6 (F6.1) — calcule (clé_logique, libellé) selon le patron de la veille."""
    if patron == Patron.SORTIE_SERIELLE:
        numero = extraire_numero(titre, url)
        nom = source.nom_serie or source.source_id
        if numero is None:
            # F13.5 — jamais aveugle silencieusement : à défaut de numéro
            # identifiable, l'URL canonique sert de repli pour ne pas
            # perdre l'élément, au prix d'un regroupement moins fin.
            return f"{nom}-{url}", titre
        return cle_sortie_serielle(nom, numero), f"{nom} — n°{numero}"

    if patron == Patron.RESULTAT_EVENEMENTIEL:
        # F5.3 : ce pipeline ne détecte pas encore le caractère provisoire
        # sur un simple listing HTML (qui ne publie en général que des
        # résultats déjà consolidés) — nature fixée à "définitif" pour ce
        # canal de collecte. Un flux publiant des scores en direct devra
        # positionner ``caractere`` en amont (hors périmètre J2).
        return cle_resultat_evenementiel(titre, date_publication, "définitif"), titre

    # ACTUALITÉ_THÉMATIQUE et repli par défaut (F1.4)
    return cle_actualite_thematique(titre), titre


def executer_cycle(
    orchestrateur: Orchestrateur,
    sources: list[SourceCollecte],
    maintenant: datetime,
    politesse: Optional[Politesse] = None,
) -> dict[str, dict]:
    """Exécute un cycle M4→M5→M6→M8 sur les sources fournies.

    Retourne un bilan par veille (candidats vus, Cibles nouvelles) et
    ajoute une entrée ``CYCLE_COLLECTE`` au journal d'audit pour chacune
    (F11.6). Une source en échec (réseau, robots.txt) n'interrompt jamais
    les autres (F3.4 : la veille n'est jamais bloquée par une source
    défaillante).
    """
    politesse = politesse or Politesse()
    bilans: dict[str, dict] = {}

    def _bilan(veille_id: str) -> dict:
        if veille_id not in bilans:
            cibles_avant = sum(1 for c in orchestrateur.cibles.values() if c.veille_id == veille_id)
            bilans[veille_id] = {"candidats_vus": 0, "cibles_avant": cibles_avant, "erreurs": []}
        return bilans[veille_id]

    for source in sources:
        veille = orchestrateur.veilles[source.veille_id]
        bilan = _bilan(source.veille_id)

        try:
            if source.type_collecte == "RSS":
                bruts = collecter_flux_rss(source.url, politesse=politesse, session=source.session)
            else:
                bruts = collecter_listing_html(
                    source.url, source.extraire_candidats, politesse=politesse, session=source.session
                )
        except ErreurRobotsInterdit as exc:
            orchestrateur.journaliser(
                source.veille_id, "COLLECTE_ROBOTS_INTERDIT",
                f"source={source.source_id} {exc}", maintenant,
            )
            bilan["erreurs"].append(str(exc))
            continue
        except Exception as exc:  # F3.4 — échec technique, veille non bloquée
            orchestrateur.journaliser(
                source.veille_id, "COLLECTE_ECHEC",
                f"source={source.source_id} erreur={exc!r}", maintenant,
            )
            bilan["erreurs"].append(repr(exc))
            continue

        for brut in bruts:
            extraite = normaliser(brut, maintenant)
            bilan["candidats_vus"] += 1
            cle, libelle = _identifier_cible(
                veille.patron, source, extraite.titre, extraite.url_canonique, extraite.date_publication
            )
            orchestrateur.detecter_occurrence(
                source.veille_id, cle, libelle,
                source_id=source.source_id, titre=extraite.titre,
                score=source.score_defaut, detectee_le=maintenant,
                caractere=Caractere.DEFINITIF,
                attributs={
                    "url": extraite.url_canonique,
                    "date_publication": extraite.date_publication.isoformat(),
                    "date_incertaine": extraite.date_incertaine,
                },
            )

    orchestrateur.avancer_temps(maintenant)

    for veille_id, bilan in bilans.items():
        cibles_apres = sum(1 for c in orchestrateur.cibles.values() if c.veille_id == veille_id)
        bilan["cibles_apres"] = cibles_apres
        bilan["cibles_nouvelles"] = cibles_apres - bilan["cibles_avant"]
        orchestrateur.journaliser(
            veille_id, "CYCLE_COLLECTE",
            f"candidats_vus={bilan['candidats_vus']} "
            f"cibles_nouvelles={bilan['cibles_nouvelles']} "
            f"cibles_totales={cibles_apres} erreurs={len(bilan['erreurs'])} "
            "(M4→M5→M6→M8, F11.6)",
            maintenant,
        )

    return bilans
