"""Modèle de données — Lot 1 / Jalon J1.

Ce module ne contient AUCUNE logique métier : uniquement les structures de
données décrites au §6 de la spécification (Directive/Interprétation exclues
du périmètre J1, cf. annexe §12.3 — elles arrivent en J4).

Aucun de ces objets ne connaît de domaine particulier (§1.3, consigne §12.5.2) :
ni "manga", ni "loto", ni "football" n'apparaissent jamais dans ce fichier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Énumérations (F1.2, F1.3, §6)
# ---------------------------------------------------------------------------

class Patron(str, Enum):
    """F1.3 — Typologie extensible des patrons de veille."""

    SORTIE_SERIELLE = "SORTIE_SÉRIELLE"
    RESULTAT_EVENEMENTIEL = "RÉSULTAT_ÉVÉNEMENTIEL"
    ACTUALITE_THEMATIQUE = "ACTUALITÉ_THÉMATIQUE"
    APPARITION_OFFRE = "APPARITION_D'OFFRE"
    SURVEILLANCE_VALEUR = "SURVEILLANCE_DE_VALEUR"
    CHANGEMENT_PAGE = "CHANGEMENT_DE_PAGE"


class ModeSources(str, Enum):
    """F1.2, M3 — Mode de sources d'une veille."""

    CIBLE = "CIBLÉ"
    LARGE = "LARGE"
    HYBRIDE = "HYBRIDE"


class OrigineSource(str, Enum):
    """F3.2 — Une source déclarée par l'utilisateur, ou découverte par l'agent."""

    DECLAREE = "DÉCLARÉE"
    DECOUVERTE = "DÉCOUVERTE"


class StatutVeille(str, Enum):
    BROUILLON = "BROUILLON"
    A_REVALIDER = "À_REVALIDER"
    ACTIVE = "ACTIVE"
    EN_PAUSE = "EN_PAUSE"
    ARCHIVEE = "ARCHIVÉE"


class EtatCible(str, Enum):
    """Diagramme d'états d'une Cible (§4, M8)."""

    DETECTEE = "DÉTECTÉE"
    EN_ATTENTE_FEEDBACK = "EN_ATTENTE_FEEDBACK"
    SATISFAITE = "SATISFAITE"
    EXPIREE = "EXPIRÉE"
    FILTREE = "FILTRÉE"


class EtatOccurrence(str, Enum):
    """§6 — États d'une Occurrence."""

    EN_RESERVE = "EN_RÉSERVE"
    OUVERTE = "OUVERTE"
    VALIDEE = "VALIDÉE"
    REJETEE = "REJETÉE"
    SANS_REPONSE = "SANS_RÉPONSE"
    IGNOREE_DOUBLON = "IGNORÉE_DOUBLON"
    FILTREE = "FILTRÉE"


class ValeurFeedback(str, Enum):
    OUI = "OUI"
    NON = "NON"


class Caractere(str, Enum):
    """F5.3 — Caractère provisoire ou définitif d'une information."""

    PROVISOIRE = "PROVISOIRE"
    DEFINITIF = "DÉFINITIF"


# ---------------------------------------------------------------------------
# Entités (§6)
# ---------------------------------------------------------------------------

@dataclass
class Source:
    """Une source interrogée pour une veille (M3).

    ``score_fiabilite`` est le score de fiabilité **propre à la veille**
    (F10.1 : jamais un score global). Il n'exclut jamais une source
    (F10.2, RG-04, D3) : ce module ne prévoit d'ailleurs aucun état
    "exclue" — seule une suggestion de rétrogradation existe (F10.3),
    et elle reste hors périmètre automatisé de J1.
    """

    id: str
    veille_id: str
    nom: str
    rang_preference: int = 0
    score_fiabilite: float = 50.0
    origine: OrigineSource = OrigineSource.DECLAREE


@dataclass
class Veille:
    """Une demande de veille persistante (M1).

    Le champ ``condition_declenchement`` matérialise F7.4 : au-delà de la
    simple nouveauté, une veille peut exiger une condition supplémentaire
    (ex. "résultat définitif uniquement"). Par défaut, toute Occurrence
    nouvelle est éligible — c'est la nouveauté elle-même qui fait office de
    condition.
    """

    id: str
    nom: str
    patron: Patron
    mode_sources: ModeSources
    seuil_pertinence: float = 0.0
    plafond_jour: Optional[int] = None  # F3.2, RG-07 — n/a en mode CIBLÉ
    fenetre_consolidation_min: float = 10.0  # RG-02
    delai_courtoisie_h: float = 2.0  # RG-05
    delai_sans_reponse_h: float = 6.0  # RG-05
    comportement_sans_reponse: str = "NON_TRAITE"  # ou "SATISFAIT" — RG-05
    condition_declenchement: Callable[["Occurrence"], bool] = field(
        default=lambda occurrence: True
    )
    statut: StatutVeille = StatutVeille.ACTIVE
    sources: dict[str, Source] = field(default_factory=dict)

    def plafond_effectif(self) -> Optional[int]:
        """RG-07 — Plafond quotidien d'ouvertures applicable, selon le mode."""
        if self.mode_sources == ModeSources.CIBLE:
            return None  # aucun plafond fonctionnel ; garde-fou géré à part
        return self.plafond_jour if self.plafond_jour is not None else 10


@dataclass
class Cible:
    """L'unité d'information attendue (M8)."""

    id: str
    veille_id: str
    cle_logique: str
    libelle: str
    creee_le: datetime
    etat: EtatCible = EtatCible.DETECTEE
    resolue_le: Optional[datetime] = None
    occurrence_ids: list[str] = field(default_factory=list)
    # Suivi interne de la fenêtre de consolidation (RG-02)
    fenetre_ouverte_le: Optional[datetime] = None
    fenetre_fermee: bool = False
    # RG-05 — délai de courtoisie avant une nouvelle ouverture
    pas_avant: Optional[datetime] = None


@dataclass
class Occurrence:
    """Le couple (Cible × Source) — §2."""

    id: str
    cible_id: str
    source_id: str
    titre: str
    score: float
    detectee_le: datetime
    etat: EtatOccurrence = EtatOccurrence.EN_RESERVE
    caractere: Caractere = Caractere.DEFINITIF
    ouverte_le: Optional[datetime] = None
    motif_rejet: Optional[str] = None
    attributs: dict = field(default_factory=dict)


@dataclass
class Feedback:
    """Réponse Oui/Non de l'utilisateur sur une Occurrence ouverte (M9)."""

    id: str
    occurrence_id: str
    valeur: ValeurFeedback
    horodatage: datetime
    motif: Optional[str] = None


@dataclass
class EvenementJournal:
    """Journal d'audit (F11.6) — écrit dès J1 (consigne §12.5.1)."""

    id: str
    veille_id: str
    type: str
    detail: str
    horodatage: datetime
