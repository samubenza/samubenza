"""M6 — Calcul de la clé logique d'une Cible, par patron (F6.1, §6).

Ce module ne connaît aucun domaine : les fonctions ci-dessous savent
reconnaître un vocabulaire *générique* de numérotation (« chapitre »,
« épisode », « numéro »...) commun à toute Sortie sérielle, mais ne
contiennent aucun nom de série, d'équipe ou de sujet particulier (§1.3).

Note de conception (voir docs/DECISIONS-J2.md) : pour `RÉSULTAT_ÉVÉNEMENTIEL`,
F6.1 inclut la nature du résultat (provisoire/définitif) *dans la clé*.
Une Occurrence provisoire et une Occurrence définitive du même événement
produisent donc deux Cibles distinctes — ce qui explique naturellement,
sans aucune modification du moteur (moteur.py), le comportement observé au
parcours §5.3 : la Cible « provisoire » ne peut par construction jamais
être satisfaite, tandis que la Cible « définitive » suit le cycle normal.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime


def slug(texte: str) -> str:
    """Normalisation générique d'un texte en identifiant stable (F5.2)."""
    texte = unicodedata.normalize("NFKD", texte)
    texte = texte.encode("ascii", "ignore").decode("ascii")
    texte = texte.lower()
    texte = re.sub(r"[^a-z0-9]+", "-", texte)
    return texte.strip("-")


# Vocabulaire générique de numérotation d'une suite (F1.3 : chapitre,
# épisode, numéro de revue, version, saison...) — jamais un nom propre.
_MOTS_NUMEROTATION = (
    r"(?:chapitre|chapter|episode|épisode|issue|num[ée]ro|num|vol(?:ume)?|"
    r"part(?:ie)?|saison|season|tome)"
)
_RE_NUMERO_MOT_CLE = re.compile(
    rf"{_MOTS_NUMEROTATION}\.?\s*#?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE
)
_RE_NUMERO_DIESE = re.compile(r"#\s*(\d+(?:[.,]\d+)?)")
_RE_NUMERO_URL = re.compile(r"/(\d+)(?:/|$|[?#].*$|\.\w+$)")


def extraire_numero(titre: str, url: str = "") -> str | None:
    """F1.3/F6.1 — extrait le numéro d'un élément de suite.

    Cherche d'abord un motif générique de numérotation dans le titre
    (« chapitre 12 », « episode #5 »...), puis, à défaut, un segment
    numérique dans l'URL (motif générique très répandu pour les contenus
    sériels : .../2960/, .../ep-12...). Fonction volontairement neutre :
    aucun nom de série n'y figure.
    """
    m = _RE_NUMERO_MOT_CLE.search(titre)
    if m:
        return m.group(1).replace(",", ".")
    m = _RE_NUMERO_DIESE.search(titre)
    if m:
        return m.group(1).replace(",", ".")
    m = _RE_NUMERO_URL.search(url)
    if m:
        return m.group(1)
    return None


def cle_sortie_serielle(
    nom_serie: str, numero: str, version_linguistique: str | None = None
) -> str:
    """F6.1 — élément + numéro (+ version linguistique si distinguée)."""
    cle = f"{slug(nom_serie)}-{numero}"
    if version_linguistique:
        cle += f"-{slug(version_linguistique)}"
    return cle


def cle_resultat_evenementiel(evenement: str, date_evenement: date | datetime, nature: str) -> str:
    """F6.1 — événement + date (+ nature du résultat : provisoire/définitif)."""
    date_str = date_evenement.date().isoformat() if isinstance(date_evenement, datetime) else date_evenement.isoformat()
    return f"{slug(evenement)}-{date_str}-{slug(nature)}"


def cle_actualite_thematique(titre: str) -> str:
    """F6.1 — empreinte sémantique de l'événement couvert.

    Approximation textuelle pour J2 : le scoring/regroupement sémantique
    complet (M7) est prévu au Lot 2. Ici, une empreinte normalisée du titre
    suffit à dédupliquer un même article republié à l'identique.
    """
    return f"actu-{slug(titre)[:80]}"
