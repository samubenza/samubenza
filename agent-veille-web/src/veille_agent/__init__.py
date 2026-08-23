"""Agent de Veille Web Autonome — noyau logique (Lot 1, jalon J1).

Aucun accès réseau, aucune extension navigateur : uniquement le modèle de
données et la machine à états Cible/Occurrence (RG-01 à RG-07).
"""
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
]
