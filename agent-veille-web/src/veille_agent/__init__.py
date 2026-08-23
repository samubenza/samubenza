"""Agent de Veille Web Autonome — noyau logique + collecteur (Lot 1, J1-J2).

J1 : modèle de données et machine à états Cible/Occurrence (RG-01 à RG-07),
sans accès réseau. J2 ajoute la collecte réelle (RSS/HTML), l'extraction et
la déduplication (M4/M5/M6), sans jamais ouvrir d'onglet ni piloter de
navigateur (hors périmètre jusqu'au jalon J6/J7).
"""
from .cle_logique import (
    cle_actualite_thematique,
    cle_resultat_evenementiel,
    cle_sortie_serielle,
    extraire_numero,
    slug,
)
from .collecteur import CandidatBrut, ErreurRobotsInterdit, Politesse, collecter_flux_rss, collecter_listing_html
from .extracteur import OccurrenceExtraite, normaliser
from .models import (
    Caractere,
    Cible,
    EtatCible,
    EtatOccurrence,
    EvenementJournal,
    Feedback,
    ModeSources,
    Occurrence,
    OrigineSource,
    Patron,
    Source,
    StatutVeille,
    ValeurFeedback,
    Veille,
)
from .moteur import GARDE_FOU_OUVERTURES_CIBLE, Orchestrateur
from .pipeline import SourceCollecte, executer_cycle

__all__ = [
    "Caractere",
    "Cible",
    "EtatCible",
    "EtatOccurrence",
    "EvenementJournal",
    "Feedback",
    "ModeSources",
    "Occurrence",
    "OrigineSource",
    "Patron",
    "Source",
    "StatutVeille",
    "ValeurFeedback",
    "Veille",
    "Orchestrateur",
    "GARDE_FOU_OUVERTURES_CIBLE",
    # M6 — clé logique
    "cle_actualite_thematique",
    "cle_resultat_evenementiel",
    "cle_sortie_serielle",
    "extraire_numero",
    "slug",
    # M4 — collecteur
    "CandidatBrut",
    "ErreurRobotsInterdit",
    "Politesse",
    "collecter_flux_rss",
    "collecter_listing_html",
    # M5 — extracteur
    "OccurrenceExtraite",
    "normaliser",
    # Pipeline J2
    "SourceCollecte",
    "executer_cycle",
]
