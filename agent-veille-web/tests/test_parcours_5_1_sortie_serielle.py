"""Parcours §5.1 — Sortie sérielle : dernier chapitre d'une série (VF).

Rejoue intégralement le tableau du §5.1 avec des occurrences fictives et
vérifie que les ouvertures produites sont exactement celles attendues,
et aucune autre (critère de validation du jalon J1, §12.3).
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


def _t(jour_offset: int, heure: int, minute: int) -> datetime:
    return datetime(2026, 8, 23, 0, 0) + timedelta(days=jour_offset, hours=heure, minutes=minute)


def _veille_serielle() -> tuple[Orchestrateur, str]:
    orch = Orchestrateur()
    veille = Veille(
        id="v-op",
        nom="One Piece — dernier chapitre (VF)",
        patron=Patron.SORTIE_SERIELLE,
        mode_sources=ModeSources.CIBLE,
    )
    orch.ajouter_veille(veille)
    for source_id, rang in [("A", 1), ("B", 2), ("C", 3), ("D", 4)]:
        orch.ajouter_source(
            "v-op", Source(id=source_id, veille_id="v-op", nom=source_id, rang_preference=rang)
        )
    return orch, "v-op"


def test_parcours_5_1_deux_ouvertures_puis_cible_suivante_ordre_appris():
    orch, veille_id = _veille_serielle()

    # --- Étape 4 : dimanche 10h02 site B publie, 10h07 site C publie -----
    occ_b = orch.detecter_occurrence(
        veille_id, "op-1191-vf", "One Piece — ch. 1191 (VF)",
        source_id="B", titre="One Piece Chapitre 1191 VF", score=92,
        detectee_le=_t(0, 10, 2),
    )
    occ_c = orch.detecter_occurrence(
        veille_id, "op-1191-vf", "One Piece — ch. 1191 (VF)",
        source_id="C", titre="OP Chapter 1191 VF", score=85,
        detectee_le=_t(0, 10, 7),
    )
    cible_1191 = orch.cibles[occ_b.cible_id]
    assert cible_1191 is orch.cibles[occ_c.cible_id]  # F5.2 — même Cible

    # Avant la fin de la fenêtre de consolidation (10 min, RG-02) : rien
    # n'est encore ouvert.
    assert occ_b.etat == EtatOccurrence.EN_RESERVE
    assert occ_c.etat == EtatOccurrence.EN_RESERVE

    # La fenêtre se ferme à 10h12 : une seule ouverture, sur le meilleur
    # score (site B, 92 > 85).
    orch.avancer_temps(_t(0, 10, 12))
    assert occ_b.etat == EtatOccurrence.OUVERTE
    assert occ_c.etat == EtatOccurrence.EN_RESERVE
    assert cible_1191.etat == EtatCible.EN_ATTENTE_FEEDBACK

    # --- Étape 5-6 : "Non" sur B → ouverture immédiate de C ---------------
    orch.donner_feedback(
        occ_b.id, ValeurFeedback.NON, _t(0, 10, 15), motif="Contenu incomplet ou tronqué"
    )
    assert occ_b.etat == EtatOccurrence.REJETEE
    assert occ_c.etat == EtatOccurrence.OUVERTE
    assert cible_1191.etat == EtatCible.EN_ATTENTE_FEEDBACK  # RG-04 : la Cible reste en attente

    # --- Étape 7-8 : "Oui" sur C → Cible satisfaite ------------------------
    orch.donner_feedback(occ_c.id, ValeurFeedback.OUI, _t(0, 10, 20))
    assert occ_c.etat == EtatOccurrence.VALIDEE
    assert cible_1191.etat == EtatCible.SATISFAITE

    # Les sites A et D publient ensuite : aucun onglet ne s'ouvre (RG-03).
    occ_a_tardif = orch.detecter_occurrence(
        veille_id, "op-1191-vf", "One Piece — ch. 1191 (VF)",
        source_id="A", titre="One Piece 1191", score=70, detectee_le=_t(0, 10, 25),
    )
    occ_d_tardif = orch.detecter_occurrence(
        veille_id, "op-1191-vf", "One Piece — ch. 1191 (VF)",
        source_id="D", titre="One Piece Chapitre 1191", score=60, detectee_le=_t(0, 10, 30),
    )
    assert occ_a_tardif.etat == EtatOccurrence.IGNOREE_DOUBLON
    assert occ_d_tardif.etat == EtatOccurrence.IGNOREE_DOUBLON

    # Aucun plafond appliqué (mode CIBLÉ) : les deux ouvertures de la
    # semaine sont bien passées, sans blocage.
    ouvertures_semaine_1 = orch.occurrences_ouvertes(veille_id)
    assert [o.id for o in ouvertures_semaine_1] == [occ_b.id, occ_c.id]

    # --- Étape 9 : semaine suivante, Cible 1192 ----------------------------
    # Score appris : B a été refusé (50 → 45), C a été validé (50 → 55).
    assert orch.veilles[veille_id].sources["B"].score_fiabilite == 45
    assert orch.veilles[veille_id].sources["C"].score_fiabilite == 55

    # Même qualité éditoriale pour les deux sources cette semaine ; c'est
    # donc uniquement le score de source appris qui doit décider l'ordre.
    fiabilite_b = orch.veilles[veille_id].sources["B"].score_fiabilite
    fiabilite_c = orch.veilles[veille_id].sources["C"].score_fiabilite
    qualite = 80
    occ_b_1192 = orch.detecter_occurrence(
        veille_id, "op-1192-vf", "One Piece — ch. 1192 (VF)",
        source_id="B", titre="One Piece Chapitre 1192 VF",
        score=qualite + (fiabilite_b - 50), detectee_le=_t(7, 10, 0),
    )
    occ_c_1192 = orch.detecter_occurrence(
        veille_id, "op-1192-vf", "One Piece — ch. 1192 (VF)",
        source_id="C", titre="OP Chapter 1192 VF",
        score=qualite + (fiabilite_c - 50), detectee_le=_t(7, 10, 5),
    )
    orch.avancer_temps(_t(7, 10, 10))

    # Le cycle est reparti intégralement à zéro (RG-06) : la nouvelle
    # Cible ignore l'issue de la précédente, hormis les scores appris.
    # → le site C est essayé en premier (meilleur score appris).
    assert occ_c_1192.etat == EtatOccurrence.OUVERTE
    # → le site B reste un candidat normal, non exclu (D3/RG-04) : il est
    # toujours dans le pool de réserve, prêt à servir en cas de refus.
    assert occ_b_1192.etat == EtatOccurrence.EN_RESERVE
    assert "B" in orch.veilles[veille_id].sources  # jamais supprimée/exclue

    ouvertures_totales = orch.occurrences_ouvertes(veille_id)
    assert [o.id for o in ouvertures_totales] == [occ_b.id, occ_c.id, occ_c_1192.id]
