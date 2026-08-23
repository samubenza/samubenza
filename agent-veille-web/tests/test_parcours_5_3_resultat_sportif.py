"""Parcours §5.3 — Résultat événementiel : résultats sportifs (définitif uniquement).

Vérifie F5.3/F7.4 : un score en cours (provisoire) ne doit jamais ouvrir
d'onglet ; seul le résultat définitif déclenche l'ouverture.
"""
from datetime import datetime, timedelta

from veille_agent import (
    Caractere,
    EtatCible,
    EtatOccurrence,
    ModeSources,
    Orchestrateur,
    Patron,
    Source,
    ValeurFeedback,
    Veille,
)


def _t(heure: int, minute: int) -> datetime:
    return datetime(2026, 8, 25, 0, 0) + timedelta(hours=heure, minutes=minute)


def _condition_definitif_uniquement(occurrence) -> bool:
    """F7.4 — condition de déclenchement exprimée dans la Directive :
    « pas les scores en direct, seulement le définitif »."""
    return occurrence.caractere == Caractere.DEFINITIF


def test_score_provisoire_est_filtre_seul_le_definitif_ouvre():
    orch = Orchestrateur()
    veille = Veille(
        id="v-club",
        nom="Résultats de mon club",
        patron=Patron.RESULTAT_EVENEMENTIEL,
        mode_sources=ModeSources.CIBLE,
        condition_declenchement=_condition_definitif_uniquement,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source("v-club", Source(id="site1", veille_id="v-club", nom="site1", rang_preference=1))
    orch.ajouter_source("v-club", Source(id="site2", veille_id="v-club", nom="site2", rang_preference=2))

    # --- Étape 3 : match à 21h → surveillance dès 22h30 ; un site publie
    # un score en cours : FILTRÉE, aucune ouverture -------------------------
    occ_provisoire = orch.detecter_occurrence(
        "v-club", "match-2026-08-24", "OL–PSG du 24/08",
        source_id="site1", titre="Score en direct : 1-0", score=80,
        detectee_le=_t(22, 35), caractere=Caractere.PROVISOIRE,
    )
    assert occ_provisoire.etat == EtatOccurrence.FILTREE
    assert occ_provisoire.ouverte_le is None

    cible = orch.cibles[occ_provisoire.cible_id]
    assert cible.etat == EtatCible.DETECTEE  # toujours en attente, pas terminée

    # --- Étape 4 : score final publié → ouverture + notification ----------
    occ_definitif = orch.detecter_occurrence(
        "v-club", "match-2026-08-24", "OL–PSG du 24/08",
        source_id="site1", titre="Résultat final : 2-1, résumé", score=95,
        detectee_le=_t(22, 50), caractere=Caractere.DEFINITIF,
    )
    orch.avancer_temps(_t(23, 0))  # fin de fenêtre de consolidation
    assert occ_definitif.etat == EtatOccurrence.OUVERTE
    assert cible.etat == EtatCible.EN_ATTENTE_FEEDBACK

    # --- Étape 5 : "Oui" → la Cible est close ; le second site ne déclenche
    # rien -------------------------------------------------------------------
    orch.donner_feedback(occ_definitif.id, ValeurFeedback.OUI, _t(23, 5))
    assert cible.etat == EtatCible.SATISFAITE

    occ_site2_tardif = orch.detecter_occurrence(
        "v-club", "match-2026-08-24", "OL–PSG du 24/08",
        source_id="site2", titre="Résultat final : 2-1", score=90,
        detectee_le=_t(23, 10), caractere=Caractere.DEFINITIF,
    )
    assert occ_site2_tardif.etat == EtatOccurrence.IGNOREE_DOUBLON

    assert [o.id for o in orch.occurrences_ouvertes("v-club")] == [occ_definitif.id]
