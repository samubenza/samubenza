"""M4 — Collecteur : lecture de flux RSS/Atom et de pages de listing HTML.

Respecte F4.5 (politesse technique obligatoire) : robots.txt, limitation de
débit par domaine (défaut 1 requête / 10 s), `User-Agent` identifiable,
back-off exponentiel sur 429/503.

Ce module ne fait strictement que produire des ``CandidatBrut`` — aucune
interprétation métier, aucune ouverture d'onglet. La normalisation (M5) et
l'identification de Cible (M6) sont des modules séparés ; l'orchestration
des trois (pipeline.py) est le seul endroit qui les assemble.
"""
from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "AgentVeilleWebAVW/0.2 (usage personnel non commercial ; "
    "+https://github.com/samubenza/samubenza)"
)
DELAI_MIN_PAR_DOMAINE_S = 10.0  # F4.5 — 1 requête / 10 s par défaut
DELAI_MIN_ENTRE_CYCLES_S = 5 * 60  # F4.1.1 — plancher de 5 minutes


@dataclass
class CandidatBrut:
    """Résultat brut d'une collecte, avant normalisation (M5)."""

    titre: str
    url: str
    date_publication_brute: Optional[str] = None
    resume: Optional[str] = None
    contenu_brut: dict = field(default_factory=dict)


class ErreurRobotsInterdit(PermissionError):
    """F13.4 — robots.txt interdit la collecte de cette URL."""


class Politesse:
    """F4.5 — limitation de débit par domaine + respect de robots.txt.

    Un seul objet ``Politesse`` doit être réutilisé sur toute la durée de
    vie du collecteur (il porte l'état "dernier accès par domaine").
    """

    def __init__(self, delai_min_s: float = DELAI_MIN_PAR_DOMAINE_S, dormir: Callable[[float], None] = time.sleep):
        self.delai_min_s = delai_min_s
        self._dormir = dormir
        self._dernier_acces: dict[str, float] = {}
        self._robots: dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    @staticmethod
    def _domaine(url: str) -> str:
        return urlparse(url).netloc

    def autorise(self, url: str, user_agent: str = USER_AGENT) -> bool:
        domaine = self._domaine(url)
        if domaine not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{urlparse(url).scheme}://{domaine}/robots.txt")
            try:
                rp.read()
            except Exception:
                # robots.txt inaccessible : on suppose l'autorisation
                # implicite, comme le font la plupart des agrégateurs RSS.
                self._robots[domaine] = None
            else:
                self._robots[domaine] = rp
        rp = self._robots[domaine]
        return rp is None or rp.can_fetch(user_agent, url)

    def attendre_si_necessaire(self, url: str) -> None:
        domaine = self._domaine(url)
        dernier = self._dernier_acces.get(domaine)
        maintenant = time.monotonic()
        if dernier is not None:
            ecoule = maintenant - dernier
            if ecoule < self.delai_min_s:
                self._dormir(self.delai_min_s - ecoule)
        self._dernier_acces[domaine] = time.monotonic()


def _requete_avec_backoff(
    session: requests.Session,
    url: str,
    politesse: Politesse,
    tentatives_max: int = 4,
    dormir: Callable[[float], None] = time.sleep,
) -> requests.Response:
    """F4.5 — back-off exponentiel sur 429/503."""
    derniere_reponse: Optional[requests.Response] = None
    for essai in range(tentatives_max):
        politesse.attendre_si_necessaire(url)
        derniere_reponse = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if derniere_reponse.status_code in (429, 503) and essai < tentatives_max - 1:
            dormir(2**essai)
            continue
        derniere_reponse.raise_for_status()
        return derniere_reponse
    derniere_reponse.raise_for_status()
    return derniere_reponse


def collecter_flux_rss(
    url: str,
    politesse: Optional[Politesse] = None,
    session: Optional[requests.Session] = None,
) -> list[CandidatBrut]:
    """F4.4 — méthode de collecte préférée : flux RSS/Atom."""
    politesse = politesse or Politesse()
    if not politesse.autorise(url):
        raise ErreurRobotsInterdit(f"robots.txt interdit la collecte de {url}")
    session = session or requests.Session()
    reponse = _requete_avec_backoff(session, url, politesse)
    flux = feedparser.parse(reponse.content)
    candidats = []
    for entree in flux.entries:
        candidats.append(
            CandidatBrut(
                titre=(entree.get("title") or "").strip(),
                url=(entree.get("link") or "").strip(),
                date_publication_brute=entree.get("published") or entree.get("updated"),
                resume=entree.get("summary"),
                contenu_brut={"id": entree.get("id"), "auteur": entree.get("author")},
            )
        )
    return candidats


def collecter_listing_html(
    url: str,
    extraire_candidats: Callable[[BeautifulSoup], list[CandidatBrut]],
    politesse: Optional[Politesse] = None,
    session: Optional[requests.Session] = None,
) -> list[CandidatBrut]:
    """F4.4 — dernier recours après RSS/sitemap : page de listing HTML.

    ``extraire_candidats`` sait lire la structure HTML d'**une** source
    donnée (chaque site a sa propre mise en page) : c'est une donnée de
    configuration de la Source (F5.1), pas une connaissance intégrée au
    Collecteur générique — qui, lui, reste neutre de tout domaine (§1.3).
    """
    politesse = politesse or Politesse()
    if not politesse.autorise(url):
        raise ErreurRobotsInterdit(f"robots.txt interdit la collecte de {url}")
    session = session or requests.Session()
    reponse = _requete_avec_backoff(session, url, politesse)
    soupe = BeautifulSoup(reponse.text, "html.parser")
    return extraire_candidats(soupe)
