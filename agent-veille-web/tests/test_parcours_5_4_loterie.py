"""Parcours §5.4 — Résultat événementiel : tirage de loterie.

Source officielle unique : déduplication triviale, une seule ouverture,
aucun risque de doublon.
"""
from datetime import datetime, timedelta

from veille_agent import (
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
    return datetime(2026, 8, 21, 0, 0) + timedelta(hours=heure, minutes=minute)


def test_source_unique_une_ouverture_puis_cible_close():
    orch = Orchestrateur()
    veille = Veille(
        id="v-loto",
        nom="Tirage du Loto du vendredi",
        patron=Patron.RESULTAT_EVENEMENTIEL,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    orch.ajouter_source(
        "v-loto", Source(id="fdj", veille_id="v-loto", nom="Site officiel FDJ", rang_preference=1)
    )

    # --- Étape 3 : résultat publié → une ouverture, une notification ------
    occ = orch.detecter_occurrence(
        "v-loto", "loto-2026-08-21", "Tirage Loto du 21/08",
        source_id="fdj", titre="Résultats Loto 21/08/2026", score=100,
        detectee_le=_t(20, 35),
    )
    orch.avancer_temps(_t(20, 45))

    cible = orch.cibles[occ.cible_id]
    assert occ.etat == EtatOccurrence.OUVERTE
    assert cible.etat == EtatCible.EN_ATTENTE_FEEDBACK

    # --- Cible close au "Oui" ------------------------------------------------
    orch.donner_feedback(occ.id, ValeurFeedback.OUI, _t(20, 40))
    assert cible.etat == EtatCible.SATISFAITE

    # Une seule source ⇒ déduplication triviale, aucun risque de doublon :
    # une seule Occurrence, une seule ouverture au total.
    assert cible.occurrence_ids == [occ.id]
    assert [o.id for o in orch.occurrences_ouvertes("v-loto")] == [occ.id]
    assert len(orch.occurrences) == 1
