"""M5 — Extracteur : normalisation des candidats bruts (F5.1, F5.4).

Traduit un ``CandidatBrut`` (M4, encore proche de la source) en
``OccurrenceExtraite`` (champs normalisés : titre, URL canonique, date de
publication). La détection provisoire/définitif (F5.3) et le calcul de la
clé logique (M6) restent hors de ce module : ils dépendent du patron de la
veille, donc de la configuration de la Source, pas de l'extraction brute.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

from .collecteur import CandidatBrut


@dataclass
class OccurrenceExtraite:
    """§6 — champs normalisés d'une Occurrence, avant identification de Cible."""

    titre: str
    url_canonique: str
    date_publication: datetime
    date_incertaine: bool  # F5.4
    resume: Optional[str] = None


_FORMATS_DATE_REPLI = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def _parser_date(date_brute: Optional[str]) -> Optional[datetime]:
    if not date_brute:
        return None
    try:
        return parsedate_to_datetime(date_brute)  # RFC 2822 (RSS)
    except (TypeError, ValueError, IndexError):
        pass
    for fmt in _FORMATS_DATE_REPLI:  # ISO 8601 (Atom) et variantes courantes
        try:
            return datetime.strptime(date_brute, fmt)
        except ValueError:
            continue
    return None


def normaliser(candidat: CandidatBrut, maintenant: datetime) -> OccurrenceExtraite:
    """F5.1 — normalise un candidat brut.

    F5.4 — si la date de publication est absente ou illisible, retient la
    date de première détection (``maintenant``) en signalant l'incertitude.
    """
    date_pub = _parser_date(candidat.date_publication_brute)
    return OccurrenceExtraite(
        titre=candidat.titre,
        url_canonique=candidat.url,
        date_publication=date_pub or maintenant,
        date_incertaine=date_pub is None,
        resume=candidat.resume,
    )
