"""Tests unitaires complémentaires pour les règles RG-01 à RG-07 (M8).

Les quatre parcours du §5 (voir les autres fichiers de ce dossier) sont le
jeu de tests de référence du projet, mais ils ne parcourent pas à eux seuls
chaque branche des règles de gestion. Ce fichier couvre les cas restants :
RG-05 (absence de feedback), RG-07 dans son intégralité (garde-fou CIBLÉ,
plafond HYBRIDE), et la non-exclusion structurelle d'une source (D3/F10.2).
"""
from datetime import datetime, timedelta

from veille_agent import (
    EtatCible,
    EtatOccurrence,
    ModeSources,
    Orchestrateur,
    OrigineSource,
    Patron,
    Source,
    StatutVeille,
    ValeurFeedback,
    Veille,
)


def _t(minute_offset: int) -> datetime:
    return datetime(2026, 1, 5, 8, 0) + timedelta(minutes=minute_offset)


# ---------------------------------------------------------------------------
# RG-05 — absence de feedback
# ---------------------------------------------------------------------------

def test_rg05_sans_reponse_par_defaut_reste_en_attente_avec_delai_de_courtoisie():
    orch = Orchestrateur()
    veille = Veille(
        id="v1", nom="Veille test", patron=Patron.CHANGEMENT_PAGE,
        mode_sources=ModeSources.CIBLE, delai_courtoisie_h=2.0,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v1", Source(id="s1", veille_id="v1", nom="s1"))
    orch.ajouter_source("v1", Source(id="s2", veille_id="v1", nom="s2"))

    occ1 = orch.detecter_occurrence(
        "v1", "page-x", "Page X", source_id="s1", titre="v1", score=80, detectee_le=_t(0)
    )
    orch.avancer_temps(_t(10))
    assert occ1.etat == EtatOccurrence.OUVERTE

    # L'onglet est fermé sans réponse après le délai (RG-05, comportement
    # par défaut "Considérer comme non traité").
    orch.expirer_sans_reponse(occ1.id, _t(6 * 60))
    cible = orch.cibles[occ1.cible_id]
    assert occ1.etat == EtatOccurrence.SANS_REPONSE
    assert cible.etat == EtatCible.EN_ATTENTE_FEEDBACK  # jamais SATISFAITE ni EXPIRÉE

    # Une nouvelle source publie juste après : le délai de courtoisie de 2h
    # n'est pas écoulé, donc aucune ouverture immédiate.
    occ2 = orch.detecter_occurrence(
        "v1", "page-x", "Page X", source_id="s2", titre="v2", score=80,
        detectee_le=_t(6 * 60 + 10),
    )
    assert occ2.etat == EtatOccurrence.EN_RESERVE

    # Une fois le délai de courtoisie écoulé, l'ouverture reprend (F4.6 /
    # RG-05) — ici simulée par un nouveau cycle de collecte (avancer_temps).
    orch.avancer_temps(_t(6 * 60 + 121))  # + 2h01
    assert occ2.etat == EtatOccurrence.OUVERTE


def test_rg05_mode_satisfait_ferme_la_cible():
    orch = Orchestrateur()
    veille = Veille(
        id="v2", nom="Veille test", patron=Patron.CHANGEMENT_PAGE,
        mode_sources=ModeSources.CIBLE, comportement_sans_reponse="SATISFAIT",
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v2", Source(id="s1", veille_id="v2", nom="s1"))

    occ = orch.detecter_occurrence(
        "v2", "page-y", "Page Y", source_id="s1", titre="v1", score=80, detectee_le=_t(0)
    )
    orch.avancer_temps(_t(10))
    orch.expirer_sans_reponse(occ.id, _t(6 * 60))

    cible = orch.cibles[occ.cible_id]
    assert cible.etat == EtatCible.SATISFAITE


# ---------------------------------------------------------------------------
# RG-07 — plafonds d'ouverture
# ---------------------------------------------------------------------------

def test_rg07_garde_fou_30_ouvertures_jour_en_mode_cible():
    orch = Orchestrateur()
    veille = Veille(
        id="v3", nom="Veille très active", patron=Patron.CHANGEMENT_PAGE,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v3", Source(id="s1", veille_id="v3", nom="s1"))

    # 30 Cibles distinctes, chacune ouverte et immédiatement satisfaite —
    # aucun plafond fonctionnel en mode CIBLÉ (D2), seul le garde-fou de
    # sécurité à 30/jour s'applique.
    for i in range(30):
        occ = orch.detecter_occurrence(
            "v3", f"page-{i}", f"Page {i}", source_id="s1", titre=f"v{i}",
            score=80, detectee_le=_t(i),
        )
        orch.avancer_temps(_t(i + 10))
        assert occ.etat == EtatOccurrence.OUVERTE
        orch.donner_feedback(occ.id, ValeurFeedback.OUI, _t(i + 11))

    assert veille.statut == StatutVeille.ACTIVE  # pas encore d'anomalie

    # La 31e Cible du jour : le garde-fou se déclenche, la veille est mise
    # en pause automatiquement et l'ouverture est bloquée.
    occ_31 = orch.detecter_occurrence(
        "v3", "page-30", "Page 30", source_id="s1", titre="v30",
        score=80, detectee_le=_t(31),
    )
    orch.avancer_temps(_t(41))

    assert occ_31.etat == EtatOccurrence.EN_RESERVE
    assert veille.statut == StatutVeille.EN_PAUSE
    assert any(evt.type == "GARDE_FOU_ANOMALIE" for evt in orch.journal)


def test_rg07_hybride_plafond_uniquement_sur_l_elargissement():
    orch = Orchestrateur()
    veille = Veille(
        id="v4", nom="Veille hybride", patron=Patron.ACTUALITE_THEMATIQUE,
        mode_sources=ModeSources.HYBRIDE, plafond_jour=2,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source(
        "v4", Source(id="declaree", veille_id="v4", nom="declaree", origine=OrigineSource.DECLAREE)
    )
    orch.ajouter_source(
        "v4", Source(id="decouverte", veille_id="v4", nom="decouverte", origine=OrigineSource.DECOUVERTE)
    )

    # Trois ouvertures depuis la source déclarée : jamais plafonnées, même
    # au-delà de 2 (le plafond ne s'applique qu'à la part élargie, RG-07).
    for i in range(3):
        occ = orch.detecter_occurrence(
            "v4", f"sujet-declare-{i}", f"Sujet {i}", source_id="declaree",
            titre=f"s{i}", score=80, detectee_le=_t(i),
        )
        orch.avancer_temps(_t(i + 10))
        assert occ.etat == EtatOccurrence.OUVERTE

    # Deux ouvertures depuis la source découverte : atteignent le plafond
    # de 2 fixé pour la part élargie.
    for i in range(2):
        occ = orch.detecter_occurrence(
            "v4", f"sujet-decouvert-{i}", f"Sujet découvert {i}", source_id="decouverte",
            titre=f"d{i}", score=80, detectee_le=_t(20 + i),
        )
        orch.avancer_temps(_t(20 + i + 10))
        assert occ.etat == EtatOccurrence.OUVERTE

    # Un troisième sujet découvert le même jour est bloqué par le plafond.
    occ_bloque = orch.detecter_occurrence(
        "v4", "sujet-decouvert-2", "Sujet découvert 2", source_id="decouverte",
        titre="d2", score=80, detectee_le=_t(40),
    )
    orch.avancer_temps(_t(50))
    assert occ_bloque.etat == EtatOccurrence.EN_RESERVE


# ---------------------------------------------------------------------------
# RG-04 / D3 — le refus ne disqualifie jamais une source
# ---------------------------------------------------------------------------

def test_rg04_trois_refus_consecutifs_n_excluent_jamais_la_source():
    orch = Orchestrateur()
    veille = Veille(
        id="v5", nom="Veille test", patron=Patron.CHANGEMENT_PAGE,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v5", Source(id="s1", veille_id="v5", nom="s1"))
    orch.ajouter_source("v5", Source(id="s2", veille_id="v5", nom="s2", rang_preference=1))

    for i in range(3):
        occ = orch.detecter_occurrence(
            "v5", f"page-{i}", f"Page {i}", source_id="s1", titre=f"v{i}",
            score=80, detectee_le=_t(i * 100),
        )
        orch.avancer_temps(_t(i * 100 + 10))
        assert occ.etat == EtatOccurrence.OUVERTE  # jamais exclue malgré les refus précédents
        orch.donner_feedback(occ.id, ValeurFeedback.NON, _t(i * 100 + 11))

    # Après 3 refus sur 3 Cibles différentes consécutives, la source existe
    # toujours et reste un candidat normal (seule une suggestion humaine de
    # rétrogradation est prévue par F10.3 — jamais une exclusion automatique).
    assert "s1" in veille.sources
    assert veille.sources["s1"].score_fiabilite == 35.0  # 50 - 5*3, jamais "banni"


# ---------------------------------------------------------------------------
# F11.6 — journal d'audit
# ---------------------------------------------------------------------------

def test_journal_audit_trace_toute_ouverture():
    orch = Orchestrateur()
    veille = Veille(
        id="v6", nom="Veille test", patron=Patron.CHANGEMENT_PAGE,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v6", Source(id="s1", veille_id="v6", nom="s1"))

    occ = orch.detecter_occurrence(
        "v6", "page-z", "Page Z", source_id="s1", titre="v1", score=80, detectee_le=_t(0)
    )
    orch.avancer_temps(_t(10))
    assert occ.etat == EtatOccurrence.OUVERTE

    entrees_ouverture = [evt for evt in orch.journal if evt.type == "OUVERTURE"]
    assert len(entrees_ouverture) == 1
    entree = entrees_ouverture[0]
    assert entree.veille_id == "v6"
    assert "page-z" in entree.detail
    assert "s1" in entree.detail
    assert "80" in entree.detail
