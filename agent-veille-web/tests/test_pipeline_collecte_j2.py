"""Lot 1 / Jalon J2 — Collecteur RSS + parsing HTML + déduplication réelle.

Ces tests exécutent le pipeline complet M4 (Collecteur, ``feedparser`` /
``BeautifulSoup`` réels) → M5 (Extracteur) → M6 (clé logique) → M8
(Orchestrateur, RG-01 à RG-07 de J1) sur trois « sites » représentatifs des
trois catégories demandées :

1. un flux RSS statique (actualité technique) — ``flux_actualite_tech.xml``
2. un site de listing HTML (résultats sportifs) — ``listing_resultats_sportifs.html``
3. un site sériel (blog à chapitres) — ``listing_blog_serie.html``

Le réseau réel est simulé par une ``requests.Session`` factice qui sert le
contenu des fixtures ci-dessus : ``feedparser`` et ``BeautifulSoup``
tournent donc pour de vrai sur du HTML/RSS représentatif, sans dépendre
d'un accès réseau (repli nécessaire : voir docs/DECISIONS-J2.md — l'accès
sortant vers des sites tiers est bloqué par la politique d'égress de cet
environnement).

Critère de validation (§12.3, J2) : le journal d'audit (F11.6) montre les
Cibles correctement identifiées et dédupliquées sur plusieurs cycles —
jamais d'ouverture d'onglet, juste le log du cycle de collecte.
"""
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

from veille_agent import (
    CandidatBrut,
    EtatCible,
    ModeSources,
    Orchestrateur,
    Patron,
    Politesse,
    Source,
    SourceCollecte,
    Veille,
    executer_cycle,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Doubles de test pour le réseau (aucun accès réseau réel, cf. DECISIONS-J2)
# ---------------------------------------------------------------------------

class _ReponseFake:
    def __init__(self, contenu: bytes, status_code: int = 200):
        self.content = contenu
        self.text = contenu.decode("utf-8")
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _SessionFake:
    """Sert le contenu d'un fichier fixture quelle que soit l'URL demandée —
    ``feedparser``/``BeautifulSoup`` reçoivent un contenu HTTP réaliste."""

    def __init__(self, chemin_fixture: Path, status_code: int = 200):
        self._contenu = chemin_fixture.read_bytes()
        self._status_code = status_code
        self.appels = 0

    def get(self, url, headers=None, timeout=None):
        self.appels += 1
        return _ReponseFake(self._contenu, self._status_code)


def _politesse_test() -> Politesse:
    """Pas de délai (tests rapides) et robots.txt considéré autorisé —
    sans cela, ``Politesse.autorise`` tenterait un vrai accès réseau."""
    politesse = Politesse(delai_min_s=0)
    politesse.autorise = lambda url, user_agent=None: True
    return politesse


def _t(heure: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 23, 0, 0) + timedelta(hours=heure, minutes=minute)


# ---------------------------------------------------------------------------
# Extraction HTML propre à chaque source de test (config M3/F5.1, jamais
# intégrée au Collecteur générique — cf. collecteur.py)
# ---------------------------------------------------------------------------

def _extraire_resultats_sportifs(soupe: BeautifulSoup) -> list[CandidatBrut]:
    candidats = []
    for ligne in soupe.select("tr.resultat"):
        rencontre = ligne.select_one("td.rencontre").get_text(strip=True)
        score = ligne.select_one("td.score").get_text(strip=True)
        date_iso = ligne.select_one("td.date").get_text(strip=True)
        lien = ligne.select_one("a")["href"]
        candidats.append(
            CandidatBrut(
                titre=f"{rencontre} : {score}",
                url=lien,
                date_publication_brute=date_iso,
            )
        )
    return candidats


def _extraire_archive_serie(soupe: BeautifulSoup) -> list[CandidatBrut]:
    candidats = []
    for lien in soupe.select("#archive a"):
        candidats.append(
            CandidatBrut(
                titre=lien.get_text(strip=True),
                url=lien["href"],
                date_publication_brute=lien.get("title"),
            )
        )
    return candidats


# ---------------------------------------------------------------------------
# 1. Flux RSS statique — actualité technique
# ---------------------------------------------------------------------------

def test_flux_rss_actualite_identifie_trois_cibles_et_deduplique_au_cycle_suivant():
    orch = Orchestrateur()
    veille = Veille(
        id="v-tech", nom="Actualité technique", patron=Patron.ACTUALITE_THEMATIQUE,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v-tech", Source(id="actu-tech", veille_id="v-tech", nom="Flux actu-tech"))

    session = _SessionFake(FIXTURES / "flux_actualite_tech.xml")
    sources = [
        SourceCollecte(
            veille_id="v-tech", source_id="actu-tech", type_collecte="RSS",
            url="https://actu-tech.example/rss.xml", session=session,
        )
    ]

    # --- Premier cycle : trois articles, trois nouvelles Cibles -----------
    bilan1 = executer_cycle(orch, sources, _t(8, 0), politesse=_politesse_test())
    assert session.appels == 1  # une requête HTTP (factice) par cycle
    assert bilan1["v-tech"]["candidats_vus"] == 3
    assert bilan1["v-tech"]["cibles_nouvelles"] == 3
    assert len([c for c in orch.cibles.values() if c.veille_id == "v-tech"]) == 3

    # F5.4 — l'article sans date publiée retombe sur l'heure de détection,
    # avec l'incertitude signalée.
    occ_sans_date = next(
        o for o in orch.occurrences.values() if "Faille de sécurité" in o.titre
    )
    assert occ_sans_date.attributs["date_incertaine"] is True
    assert occ_sans_date.attributs["date_publication"] == _t(8, 0).isoformat()

    # --- Deuxième cycle, même flux inchangé : aucune nouvelle Cible -------
    bilan2 = executer_cycle(orch, sources, _t(8, 15), politesse=_politesse_test())
    assert bilan2["v-tech"]["candidats_vus"] == 3       # les 3 items sont revus...
    assert bilan2["v-tech"]["cibles_nouvelles"] == 0     # ...mais aucune nouvelle Cible (M6)
    assert len([c for c in orch.cibles.values() if c.veille_id == "v-tech"]) == 3

    # Le journal d'audit trace bien les deux cycles (F11.6).
    cycles = [e for e in orch.journal if e.type == "CYCLE_COLLECTE" and e.veille_id == "v-tech"]
    assert len(cycles) == 2
    assert "cibles_nouvelles=3" in cycles[0].detail
    assert "cibles_nouvelles=0" in cycles[1].detail


# ---------------------------------------------------------------------------
# 2. Site de listing HTML — résultats sportifs
# ---------------------------------------------------------------------------

def test_listing_html_resultats_sportifs_identifie_et_deduplique():
    orch = Orchestrateur()
    veille = Veille(
        id="v-sport", nom="Résultats sportifs", patron=Patron.RESULTAT_EVENEMENTIEL,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v-sport", Source(id="resultats-sport", veille_id="v-sport", nom="Page résultats"))

    session = _SessionFake(FIXTURES / "listing_resultats_sportifs.html")
    sources = [
        SourceCollecte(
            veille_id="v-sport", source_id="resultats-sport", type_collecte="LISTING_HTML",
            url="https://resultats-sport.example/journee-22-23-08-2026",
            extraire_candidats=_extraire_resultats_sportifs, session=session,
        )
    ]

    bilan1 = executer_cycle(orch, sources, _t(9, 0), politesse=_politesse_test())
    assert bilan1["v-sport"]["candidats_vus"] == 2
    assert bilan1["v-sport"]["cibles_nouvelles"] == 2

    cibles = [c for c in orch.cibles.values() if c.veille_id == "v-sport"]
    assert len(cibles) == 2
    # Deux matchs distincts le même jour → deux Cibles distinctes, jamais
    # regroupées (cas limite §7 : "deux éléments... le même jour").
    assert cibles[0].cle_logique != cibles[1].cle_logique
    # RG-02 : la fenêtre de consolidation (10 min) vient tout juste de
    # s'ouvrir dans ce même cycle — rien ne s'ouvre encore à cet instant.
    assert cibles[0].etat == EtatCible.DETECTEE

    # Deuxième cycle, 30 min plus tard, page inchangée : la fenêtre de
    # consolidation du premier cycle a eu le temps de se fermer (RG-02),
    # ET aucun nouveau match n'apparaît (déduplication, M6).
    bilan2 = executer_cycle(orch, sources, _t(9, 30), politesse=_politesse_test())
    assert bilan2["v-sport"]["cibles_nouvelles"] == 0
    assert len([c for c in orch.cibles.values() if c.veille_id == "v-sport"]) == 2
    assert cibles[0].etat == EtatCible.EN_ATTENTE_FEEDBACK  # ouverture normale (RG-01)


# ---------------------------------------------------------------------------
# 3. Site sériel — blog à chapitres
# ---------------------------------------------------------------------------

def test_site_seriel_identifie_le_numero_via_l_url_et_deduplique():
    orch = Orchestrateur()
    veille = Veille(
        id="v-serie", nom="Chroniques du Nord", patron=Patron.SORTIE_SERIELLE,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v-serie", Source(id="chroniques", veille_id="v-serie", nom="Archive du blog"))

    session = _SessionFake(FIXTURES / "listing_blog_serie.html")
    sources = [
        SourceCollecte(
            veille_id="v-serie", source_id="chroniques", type_collecte="LISTING_HTML",
            url="https://chroniques-du-nord.example/archive/",
            extraire_candidats=_extraire_archive_serie,
            nom_serie="Chroniques du Nord", session=session,
        )
    ]

    bilan1 = executer_cycle(orch, sources, _t(10, 0), politesse=_politesse_test())
    assert bilan1["v-serie"]["candidats_vus"] == 3
    assert bilan1["v-serie"]["cibles_nouvelles"] == 3

    cibles = {c.cle_logique: c for c in orch.cibles.values() if c.veille_id == "v-serie"}
    # Le numéro est extrait depuis l'URL (.../2960/, .../2959/...), la clé
    # logique combine le nom de la série (constant, F6.1) et ce numéro.
    assert "chroniques-du-nord-2960" in cibles
    assert "chroniques-du-nord-2959" in cibles
    assert "chroniques-du-nord-2958" in cibles

    # Deuxième cycle, archive inchangée : déduplication totale (M6).
    bilan2 = executer_cycle(orch, sources, _t(10, 15), politesse=_politesse_test())
    assert bilan2["v-serie"]["cibles_nouvelles"] == 0
    assert len([c for c in orch.cibles.values() if c.veille_id == "v-serie"]) == 3


# ---------------------------------------------------------------------------
# F3.4 — une source défaillante ne bloque jamais la veille
# ---------------------------------------------------------------------------

def test_source_interdite_par_robots_txt_est_journalisee_sans_bloquer_les_autres():
    orch = Orchestrateur()
    veille = Veille(
        id="v-mix", nom="Veille mixte", patron=Patron.ACTUALITE_THEMATIQUE,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v-mix", Source(id="interdite", veille_id="v-mix", nom="Source interdite"))
    orch.ajouter_source("v-mix", Source(id="ok", veille_id="v-mix", nom="Source ok"))

    politesse = Politesse(delai_min_s=0)
    politesse.autorise = lambda url, user_agent=None: "interdite" not in url

    session_ok = _SessionFake(FIXTURES / "flux_actualite_tech.xml")
    sources = [
        SourceCollecte(
            veille_id="v-mix", source_id="interdite", type_collecte="RSS",
            url="https://interdite.example/rss.xml",
        ),
        SourceCollecte(
            veille_id="v-mix", source_id="ok", type_collecte="RSS",
            url="https://actu-tech.example/rss.xml", session=session_ok,
        ),
    ]

    bilan = executer_cycle(orch, sources, _t(11, 0), politesse=politesse)

    # bilan["v-mix"] est partagé par les deux sources de cette veille : il
    # porte bien la trace de l'échec de la source interdite...
    assert len(bilan["v-mix"]["erreurs"]) == 1
    # ...mais la source OK, elle, a quand même été traitée normalement.
    assert bilan["v-mix"]["candidats_vus"] == 3
    entrees_robots = [e for e in orch.journal if e.type == "COLLECTE_ROBOTS_INTERDIT"]
    assert len(entrees_robots) == 1
    assert "interdite" in entrees_robots[0].detail
    assert veille.statut.value == "ACTIVE"  # la veille n'est jamais bloquée (F3.4)


class _SessionEnPanne:
    """Simule une source injoignable (DNS, timeout...) — F3.4."""

    def get(self, url, headers=None, timeout=None):
        raise ConnectionError("DNS injoignable (simulation)")


def test_echec_technique_d_une_source_est_journalise_sans_bloquer_les_autres():
    orch = Orchestrateur()
    veille = Veille(
        id="v-panne", nom="Veille avec panne", patron=Patron.ACTUALITE_THEMATIQUE,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v-panne", Source(id="en-panne", veille_id="v-panne", nom="Source en panne"))
    orch.ajouter_source("v-panne", Source(id="saine", veille_id="v-panne", nom="Source saine"))

    session_saine = _SessionFake(FIXTURES / "flux_actualite_tech.xml")
    sources = [
        SourceCollecte(
            veille_id="v-panne", source_id="en-panne", type_collecte="RSS",
            url="https://en-panne.example/rss.xml", session=_SessionEnPanne(),
        ),
        SourceCollecte(
            veille_id="v-panne", source_id="saine", type_collecte="RSS",
            url="https://actu-tech.example/rss.xml", session=session_saine,
        ),
    ]

    bilan = executer_cycle(orch, sources, _t(12, 0), politesse=_politesse_test())

    assert bilan["v-panne"]["candidats_vus"] == 3  # la source saine a bien été traitée
    entrees_echec = [e for e in orch.journal if e.type == "COLLECTE_ECHEC"]
    assert len(entrees_echec) == 1
    assert "en-panne" in entrees_echec[0].detail
    assert veille.statut.value == "ACTIVE"  # F3.4 — jamais bloquée
