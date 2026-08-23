"""Parcours §5.2 — Actualité thématique : préparation d'un voyage en Écosse.

Mode `LARGE` : regroupement d'un événement multi-sources sur une seule
Cible, filtrage des sujets hors périmètre par le seuil de pertinence
(F7.2), et plafond quotidien d'ouvertures (RG-07).
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
    ValeurFeedback,
    Veille,
)


def _t(heure: int, minute: int) -> datetime:
    return datetime(2026, 8, 24, 0, 0) + timedelta(hours=heure, minutes=minute)


def _veille_ecosse() -> tuple[Orchestrateur, str]:
    orch = Orchestrateur()
    veille = Veille(
        id="v-ecosse",
        nom="Voyage Écosse — actualité utile",
        patron=Patron.ACTUALITE_THEMATIQUE,
        mode_sources=ModeSources.LARGE,
        seuil_pertinence=50.0,   # F7.3 — écarte le hors-sujet (débat national…)
        plafond_jour=10,          # F3.2 / RG-07 — défaut
    )
    orch.ajouter_veille(veille)
    for i in range(1, 13):
        nom = f"media{i}"
        orch.ajouter_source(
            "v-ecosse",
            Source(id=nom, veille_id="v-ecosse", nom=nom, origine=OrigineSource.DECOUVERTE),
        )
    return orch, "v-ecosse"


def test_evenement_multi_medias_ne_produit_qu_une_seule_ouverture():
    orch, veille_id = _veille_ecosse()

    # --- Étape 5 : un événement couvert par 4 médias -----------------------
    occs = []
    for media, score, minute in [("media1", 90, 0), ("media2", 85, 3), ("media3", 80, 4), ("media4", 75, 6)]:
        occs.append(
            orch.detecter_occurrence(
                veille_id, "fermeture-route-highlands",
                "Fermeture de route dans les Highlands",
                source_id=media, titre=f"{media}: route closure", score=score,
                detectee_le=_t(9, minute),
            )
        )
    orch.avancer_temps(_t(9, 10))  # fin de la fenêtre de consolidation (10 min)

    cible = orch.cibles[occs[0].cible_id]
    assert cible.etat == EtatCible.EN_ATTENTE_FEEDBACK
    ouvertes = [o for o in occs if o.etat == EtatOccurrence.OUVERTE]
    assert len(ouvertes) == 1
    assert ouvertes[0].source_id == "media1"  # meilleur score (90)

    # --- Étape 6 : refus d'un article hors sujet → l'agent tente la suivante
    orch.donner_feedback(
        occs[0].id, ValeurFeedback.NON, _t(9, 15), motif="Ce n'est pas ce que je cherchais"
    )
    assert occs[0].etat == EtatOccurrence.REJETEE
    assert occs[1].etat == EtatOccurrence.OUVERTE  # media2, deuxième meilleur score

    orch.donner_feedback(occs[1].id, ValeurFeedback.OUI, _t(9, 20))
    assert cible.etat == EtatCible.SATISFAITE
    assert occs[2].etat == EtatOccurrence.IGNOREE_DOUBLON  # media3 abandonné (RG-03)
    assert occs[3].etat == EtatOccurrence.IGNOREE_DOUBLON  # media4 abandonné (RG-03)

    # Deux onglets réellement ouverts pour cet événement (media1 puis media2).
    assert [o.id for o in orch.occurrences_ouvertes(veille_id)] == [occs[0].id, occs[1].id]


def test_contenu_hors_sujet_est_filtre_sans_ouverture():
    orch, veille_id = _veille_ecosse()

    # Exemple discriminant du §5.2 : "un débat politique national : non".
    occ = orch.detecter_occurrence(
        veille_id, "debat-politique-national", "Débat politique national",
        source_id="media5", titre="Débat national sans lien avec le voyage",
        score=20,  # sous le seuil de pertinence (50)
        detectee_le=_t(11, 0),
    )
    orch.avancer_temps(_t(11, 10))

    assert occ.etat == EtatOccurrence.FILTREE
    assert occ.ouverte_le is None
    assert orch.occurrences_ouvertes(veille_id) == []


def test_plafond_10_ouvertures_par_jour_en_mode_large():
    orch, veille_id = _veille_ecosse()

    # Dix événements distincts et pertinents dans la même journée : les dix
    # doivent s'ouvrir (F3.2, D2 : plafond par défaut = 10).
    for i in range(10):
        heure = 8 + i
        occ = orch.detecter_occurrence(
            veille_id, f"evenement-{i}", f"Événement utile n°{i}",
            source_id=f"media{i + 1}", titre=f"Actualité utile {i}", score=90,
            detectee_le=_t(heure, 0),
        )
        orch.avancer_temps(_t(heure, 10))
        assert occ.etat == EtatOccurrence.OUVERTE, f"événement {i} aurait dû s'ouvrir"

    assert len(orch.occurrences_ouvertes(veille_id)) == 10

    # Le onzième événement pertinent de la journée est mis en file : le
    # plafond quotidien de 10 est atteint (RG-07), aucune ouverture de plus.
    occ_11 = orch.detecter_occurrence(
        veille_id, "evenement-10", "Événement utile n°10 (11e du jour)",
        source_id="media11", titre="Actualité utile 10", score=90,
        detectee_le=_t(19, 0),
    )
    orch.avancer_temps(_t(19, 10))

    assert occ_11.etat == EtatOccurrence.EN_RESERVE
    assert occ_11.ouverte_le is None
    assert len(orch.occurrences_ouvertes(veille_id)) == 10  # toujours 10, pas 11

    assert any(evt.type == "PLAFOND_ATTEINT" for evt in orch.journal)
