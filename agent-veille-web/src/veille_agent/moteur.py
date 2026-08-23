"""Machine à états Cible/Occurrence — règles RG-01 à RG-07 (M8).

Lot 1 / Jalon J1 : **aucun accès réseau**. L'``Orchestrateur`` ne fait que
réagir à des occurrences qui lui sont fournies (simulant ce qu'un
Collecteur/Extracteur produirait à partir de J2) et applique les règles de
gestion de l'orchestrateur d'ouverture. Rien ici n'ouvre de vrai onglet ni
n'envoie de vraie notification Windows : ``_log`` matérialise ces actions
dans le journal d'audit (F11.6), consultable par les tests.

Portée volontairement exclue de ce fichier (renvoyée aux jalons suivants) :
- M4/M5/M6 (collecte réseau, extraction, calcul de la clé logique d'une
  Cible à partir d'une page réelle) : ici, la clé logique est fournie en
  entrée, comme le prévoit le découpage en jalons (§12.3, J1 vs J2).
- RG-08/RG-09/RG-10 (forme de la notification Windows, lancement du
  navigateur, disponibilité machine) : ce sont des préoccupations
  d'intégration système, hors de la machine à états logique de J1.

Aucune ligne de ce fichier ne mentionne un domaine particulier (§1.3) : le
même code traite indifféremment un chapitre de manga, un résultat sportif
ou une actualité de voyage, comme l'exigent les quatre parcours du §5.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import Optional

from .models import (
    Caractere,
    Cible,
    EtatCible,
    EtatOccurrence,
    EvenementJournal,
    Feedback,
    ModeSources,
    Occurrence,
    OrigineSource,
    Source,
    StatutVeille,
    ValeurFeedback,
    Veille,
)

# RG-07 — garde-fou de sécurité en mode CIBLÉ (anomalie probable au-delà)
GARDE_FOU_OUVERTURES_CIBLE = 30


class Orchestrateur:
    """Applique RG-01 à RG-07 sur un ensemble de Veilles/Cibles/Occurrences."""

    def __init__(self) -> None:
        self.veilles: dict[str, Veille] = {}
        self.cibles: dict[str, Cible] = {}
        self.occurrences: dict[str, Occurrence] = {}
        self.feedbacks: list[Feedback] = []
        self.journal: list[EvenementJournal] = []

        self._compteurs = itertools.count(1)
        # RG-07 — compteur d'ouvertures par (veille, jour, portée)
        # portée = "TOUTES" (mode CIBLÉ, garde-fou) ou "PLAFONNEES" (LARGE,
        # ou part élargie en HYBRIDE)
        self._ouvertures_jour: dict[tuple[str, str, str], int] = {}

    # ------------------------------------------------------------------
    # Enregistrement (M1/M3 minimal, nécessaire pour dérouler les tests)
    # ------------------------------------------------------------------

    def _nouvel_id(self, prefixe: str) -> str:
        return f"{prefixe}-{next(self._compteurs)}"

    def ajouter_veille(self, veille: Veille) -> Veille:
        self.veilles[veille.id] = veille
        return veille

    def ajouter_source(self, veille_id: str, source: Source) -> Source:
        self.veilles[veille_id].sources[source.id] = source
        return source

    def _log(self, veille_id: str, type_: str, detail: str, horodatage: datetime) -> None:
        self.journal.append(
            EvenementJournal(
                id=self._nouvel_id("evt"),
                veille_id=veille_id,
                type=type_,
                detail=detail,
                horodatage=horodatage,
            )
        )

    def journaliser(self, veille_id: str, type_: str, detail: str, horodatage: datetime) -> None:
        """F11.6 — point d'entrée public pour qu'un appelant externe (ex. le
        pipeline de collecte, M4→M5→M6) ajoute une entrée au journal d'audit
        sans avoir à connaître les détails internes de l'orchestrateur."""
        self._log(veille_id, type_, detail, horodatage)

    # ------------------------------------------------------------------
    # RG-01 / RG-02 — détection d'une Occurrence
    # ------------------------------------------------------------------

    def detecter_occurrence(
        self,
        veille_id: str,
        cle_logique: str,
        libelle: str,
        source_id: str,
        titre: str,
        score: float,
        detectee_le: datetime,
        caractere: Caractere = Caractere.DEFINITIF,
        attributs: Optional[dict] = None,
    ) -> Occurrence:
        """Point d'entrée unique pour signaler qu'une Occurrence a été vue.

        Applique successivement :
        - le rattachement à une Cible existante ou la création d'une
          nouvelle Cible (F6.2) ;
        - le filtrage par score/condition de déclenchement (F7.2) ;
        - RG-01 (première Occurrence) et RG-02 (fenêtre de consolidation) ;
        - RG-03/RG-04 pour les Occurrences ultérieures d'une Cible déjà en
          attente de feedback ou déjà satisfaite.
        """
        veille = self.veilles[veille_id]
        cible = self._trouver_ou_creer_cible(veille, cle_logique, libelle, detectee_le)

        occurrence = Occurrence(
            id=self._nouvel_id("occ"),
            cible_id=cible.id,
            source_id=source_id,
            titre=titre,
            score=score,
            detectee_le=detectee_le,
            caractere=caractere,
            attributs=attributs or {},
        )
        self.occurrences[occurrence.id] = occurrence

        # RG-03 — une Cible déjà satisfaite n'ouvre plus jamais rien.
        if cible.etat == EtatCible.SATISFAITE:
            occurrence.etat = EtatOccurrence.IGNOREE_DOUBLON
            self._log(
                veille_id, "OCCURRENCE_IGNOREE_DOUBLON",
                f"cible={cible.cle_logique} source={source_id} "
                "(cible déjà satisfaite — RG-03)",
                detectee_le,
            )
            return occurrence

        # Une Cible déjà expirée n'accepte plus de nouvelles ouvertures non
        # plus (hors périmètre détaillé des expirations en J1, traité par
        # prudence pour ne jamais rouvrir une Cible terminée).
        if cible.etat == EtatCible.EXPIREE:
            occurrence.etat = EtatOccurrence.IGNOREE_DOUBLON
            self._log(
                veille_id, "OCCURRENCE_IGNOREE_DOUBLON",
                f"cible={cible.cle_logique} source={source_id} (cible expirée)",
                detectee_le,
            )
            return occurrence

        # F7.2 — score et condition de déclenchement.
        if not self._est_eligible(veille, occurrence):
            occurrence.etat = EtatOccurrence.FILTREE
            self._log(
                veille_id, "OCCURRENCE_FILTREE",
                f"cible={cible.cle_logique} source={source_id} score={score} "
                "(score < seuil ou condition de déclenchement non remplie — F7.2)",
                detectee_le,
            )
            return occurrence

        cible.occurrence_ids.append(occurrence.id)

        if cible.etat == EtatCible.DETECTEE:
            self._traiter_candidate_pour_cible_detectee(veille, cible, detectee_le)
        elif cible.etat == EtatCible.EN_ATTENTE_FEEDBACK:
            # RG-04 — une nouvelle source (ou une mise à jour, F4.6) arrive
            # pendant que la Cible attend un feedback : si aucune Occurrence
            # n'est actuellement ouverte, l'ouverture reprend immédiatement.
            if not self._a_occurrence_ouverte(cible) and self._delai_courtoisie_ecoule(cible, detectee_le):
                self._ouvrir_meilleure_candidate(veille, cible, detectee_le)

        return occurrence

    def _trouver_ou_creer_cible(
        self, veille: Veille, cle_logique: str, libelle: str, maintenant: datetime
    ) -> Cible:
        for cible in self.cibles.values():
            if cible.veille_id == veille.id and cible.cle_logique == cle_logique:
                return cible
        cible = Cible(
            id=self._nouvel_id("cible"),
            veille_id=veille.id,
            cle_logique=cle_logique,
            libelle=libelle,
            creee_le=maintenant,
        )
        self.cibles[cible.id] = cible
        self._log(veille.id, "CIBLE_CREEE", f"cible={cle_logique} ({libelle})", maintenant)
        return cible

    def _est_eligible(self, veille: Veille, occurrence: Occurrence) -> bool:
        """F7.2 — (a) score au-dessus du seuil ET (b) condition remplie."""
        if occurrence.score < veille.seuil_pertinence:
            return False
        return bool(veille.condition_declenchement(occurrence))

    def _traiter_candidate_pour_cible_detectee(
        self, veille: Veille, cible: Cible, maintenant: datetime
    ) -> None:
        if cible.fenetre_ouverte_le is None:
            # RG-02 — ouverture de la fenêtre de consolidation.
            cible.fenetre_ouverte_le = maintenant
            self._log(
                veille.id, "FENETRE_CONSOLIDATION_OUVERTE",
                f"cible={cible.cle_logique} jusqu'à "
                f"{maintenant + timedelta(minutes=veille.fenetre_consolidation_min)}",
                maintenant,
            )
            self._verifier_fenetre(veille, cible, maintenant)
        elif not cible.fenetre_fermee:
            # Une autre source publie pendant la fenêtre encore ouverte :
            # elle rejoint le pool de candidates, sans ouverture immédiate.
            self._verifier_fenetre(veille, cible, maintenant)
        else:
            # La fenêtre a déjà été traitée sans qu'aucune candidate ne
            # soit retenue (tout était filtré) : la Cible reste DÉTECTÉE et
            # cette nouvelle candidate éligible peut ouvrir tout de suite.
            self._ouvrir_meilleure_candidate(veille, cible, maintenant)

    # ------------------------------------------------------------------
    # RG-02 — fenêtre de consolidation
    # ------------------------------------------------------------------

    def avancer_temps(self, maintenant: datetime) -> None:
        """Force le traitement des fenêtres de consolidation expirées.

        Dans un service réel, ceci se produit naturellement au fil des
        cycles de collecte (M4). En simulation, on l'appelle explicitement
        pour représenter l'écoulement du temps sans nouvelle détection.
        """
        for cible in list(self.cibles.values()):
            veille = self.veilles[cible.veille_id]
            if cible.etat == EtatCible.DETECTEE:
                if cible.fenetre_ouverte_le is not None and not cible.fenetre_fermee:
                    self._verifier_fenetre(veille, cible, maintenant)
            elif cible.etat == EtatCible.EN_ATTENTE_FEEDBACK:
                # RG-05 — le délai de courtoisie peut s'être écoulé sans
                # qu'aucune nouvelle Occurrence ne soit détectée entre
                # temps : on retente l'ouverture sur les candidates déjà
                # en réserve, s'il y en a.
                if not self._a_occurrence_ouverte(cible):
                    self._ouvrir_meilleure_candidate(veille, cible, maintenant)

    def _verifier_fenetre(self, veille: Veille, cible: Cible, maintenant: datetime) -> None:
        fin_fenetre = cible.fenetre_ouverte_le + timedelta(
            minutes=veille.fenetre_consolidation_min
        )
        if maintenant >= fin_fenetre and not cible.fenetre_fermee:
            cible.fenetre_fermee = True
            self._ouvrir_meilleure_candidate(veille, cible, maintenant)

    # ------------------------------------------------------------------
    # RG-01/RG-02/RG-07 — sélection et ouverture
    # ------------------------------------------------------------------

    def _a_occurrence_ouverte(self, cible: Cible) -> bool:
        return any(
            self.occurrences[oid].etat == EtatOccurrence.OUVERTE
            for oid in cible.occurrence_ids
        )

    def _delai_courtoisie_ecoule(self, cible: Cible, maintenant: datetime) -> bool:
        return cible.pas_avant is None or maintenant >= cible.pas_avant

    def _candidates(self, cible: Cible) -> list[Occurrence]:
        return [
            self.occurrences[oid]
            for oid in cible.occurrence_ids
            if self.occurrences[oid].etat == EtatOccurrence.EN_RESERVE
        ]

    def _cle_tri(self, veille: Veille, occurrence: Occurrence):
        source = veille.sources.get(occurrence.source_id)
        rang = source.rang_preference if source else 0
        fiabilite = source.score_fiabilite if source else 0.0
        # Meilleur score d'abord, puis rang de préférence utilisateur (plus
        # petit = préféré), puis score de fiabilité appris (F10.2).
        return (-occurrence.score, rang, -fiabilite)

    def _ouvrir_meilleure_candidate(
        self, veille: Veille, cible: Cible, maintenant: datetime
    ) -> Optional[Occurrence]:
        candidates = self._candidates(cible)
        if not candidates:
            # RG-04 — rien à ouvrir pour l'instant, on attend une nouvelle
            # source ou une mise à jour (F4.6).
            return None

        if not self._delai_courtoisie_ecoule(cible, maintenant):
            return None  # RG-05 — délai de courtoisie non écoulé

        meilleure = min(candidates, key=lambda o: self._cle_tri(veille, o))

        if self._plafond_atteint(veille, maintenant, occurrence_test=meilleure):
            self._log(
                veille.id, "PLAFOND_ATTEINT",
                f"cible={cible.cle_logique} — mise en file d'attente (RG-07)",
                maintenant,
            )
            return None

        meilleure.etat = EtatOccurrence.OUVERTE
        meilleure.ouverte_le = maintenant
        cible.etat = EtatCible.EN_ATTENTE_FEEDBACK
        # Les autres candidates restent EN_RÉSERVE (RG-02) : elles ne sont
        # ni ouvertes, ni écartées — elles pourront servir en cas de "Non".

        self._incrementer_ouvertures(veille, maintenant, meilleure)
        self._log(
            veille.id, "OUVERTURE",
            f"cible={cible.cle_logique} source={meilleure.source_id} "
            f"score={meilleure.score} (RG-01/RG-02)",
            maintenant,
        )
        return meilleure

    # -- RG-07 : plafonds d'ouverture, asymétriques selon le mode --------

    def _portee_plafond(self, veille: Veille, occurrence: Occurrence) -> str:
        """Détermine si une ouverture compte pour le plafond quotidien.

        - CIBLÉ : jamais plafonnée fonctionnellement (seul le garde-fou
          anti-anomalie à 30/jour s'applique).
        - LARGE : toujours plafonnée.
        - HYBRIDE : seules les Occurrences issues de l'élargissement au Web
          (source DÉCOUVERTE) sont plafonnées ; les sources déclarées
          conservent le régime CIBLÉ.
        """
        if veille.mode_sources == ModeSources.LARGE:
            return "PLAFONNEE"
        if veille.mode_sources == ModeSources.HYBRIDE:
            source = veille.sources.get(occurrence.source_id)
            if source and source.origine == OrigineSource.DECOUVERTE:
                return "PLAFONNEE"
            return "NON_PLAFONNEE"
        return "NON_PLAFONNEE"  # CIBLÉ

    def _cle_compteur(self, veille: Veille, maintenant: datetime, portee: str) -> tuple[str, str, str]:
        return (veille.id, maintenant.date().isoformat(), portee)

    def _plafond_atteint(
        self, veille: Veille, maintenant: datetime, occurrence_test: Occurrence
    ) -> bool:
        # Garde-fou anti-anomalie (RG-07) : spécifique au mode CIBLÉ, seul
        # mode fonctionnellement sans plafond (cf. tableau RG-07).
        if veille.mode_sources == ModeSources.CIBLE:
            cle_toutes = self._cle_compteur(veille, maintenant, "TOUTES")
            if self._ouvertures_jour.get(cle_toutes, 0) >= GARDE_FOU_OUVERTURES_CIBLE:
                if veille.statut == StatutVeille.ACTIVE:
                    veille.statut = StatutVeille.EN_PAUSE
                    self._log(
                        veille.id, "GARDE_FOU_ANOMALIE",
                        f"{GARDE_FOU_OUVERTURES_CIBLE} ouvertures atteintes — "
                        "veille mise en pause automatiquement (RG-07)",
                        maintenant,
                    )
                return True

        portee = self._portee_plafond(veille, occurrence_test)
        if portee == "NON_PLAFONNEE":
            return False

        plafond = veille.plafond_effectif()
        if plafond is None:
            return False
        cle = self._cle_compteur(veille, maintenant, portee)
        return self._ouvertures_jour.get(cle, 0) >= plafond

    def _incrementer_ouvertures(
        self, veille: Veille, maintenant: datetime, occurrence: Occurrence
    ) -> None:
        cle_toutes = self._cle_compteur(veille, maintenant, "TOUTES")
        self._ouvertures_jour[cle_toutes] = self._ouvertures_jour.get(cle_toutes, 0) + 1

        portee = self._portee_plafond(veille, occurrence)
        if portee == "PLAFONNEE":
            cle = self._cle_compteur(veille, maintenant, portee)
            self._ouvertures_jour[cle] = self._ouvertures_jour.get(cle, 0) + 1

    # ------------------------------------------------------------------
    # RG-03 / RG-04 — feedback
    # ------------------------------------------------------------------

    def donner_feedback(
        self,
        occurrence_id: str,
        valeur: ValeurFeedback,
        horodatage: datetime,
        motif: Optional[str] = None,
    ) -> Feedback:
        occurrence = self.occurrences[occurrence_id]
        cible = self.cibles[occurrence.cible_id]
        veille = self.veilles[cible.veille_id]

        feedback = Feedback(
            id=self._nouvel_id("fb"),
            occurrence_id=occurrence_id,
            valeur=valeur,
            horodatage=horodatage,
            motif=motif,
        )
        self.feedbacks.append(feedback)

        if valeur == ValeurFeedback.OUI:
            self._appliquer_feedback_oui(veille, cible, occurrence, horodatage)
        else:
            self._appliquer_feedback_non(veille, cible, occurrence, horodatage, motif)

        return feedback

    def _appliquer_feedback_oui(
        self, veille: Veille, cible: Cible, occurrence: Occurrence, maintenant: datetime
    ) -> None:
        """RG-03 — la Cible est satisfaite, les réserves sont abandonnées."""
        occurrence.etat = EtatOccurrence.VALIDEE
        cible.etat = EtatCible.SATISFAITE
        cible.resolue_le = maintenant

        for oid in cible.occurrence_ids:
            autre = self.occurrences[oid]
            if autre.etat == EtatOccurrence.EN_RESERVE:
                autre.etat = EtatOccurrence.IGNOREE_DOUBLON

        self._ajuster_score_source(veille, occurrence.source_id, succes=True)
        self._log(
            veille.id, "CIBLE_SATISFAITE",
            f"cible={cible.cle_logique} source={occurrence.source_id} (RG-03)",
            maintenant,
        )

    def _appliquer_feedback_non(
        self,
        veille: Veille,
        cible: Cible,
        occurrence: Occurrence,
        maintenant: datetime,
        motif: Optional[str],
    ) -> None:
        """RG-04 — portée du refus strictement limitée à la Cible courante."""
        occurrence.etat = EtatOccurrence.REJETEE
        occurrence.motif_rejet = motif
        # La Cible reste EN_ATTENTE_FEEDBACK (elle ne devient jamais
        # SATISFAITE ni FILTRÉE sur un "Non").
        cible.etat = EtatCible.EN_ATTENTE_FEEDBACK

        self._ajuster_score_source(veille, occurrence.source_id, succes=False)
        self._log(
            veille.id, "OCCURRENCE_REJETEE",
            f"cible={cible.cle_logique} source={occurrence.source_id} "
            f"motif={motif or '(aucun)'} (RG-04)",
            maintenant,
        )

        # Ouvre immédiatement l'Occurrence suivante disponible, s'il y en a
        # une ; sinon l'agent attend (RG-04).
        self._ouvrir_meilleure_candidate(veille, cible, maintenant)

    def _ajuster_score_source(self, veille: Veille, source_id: str, succes: bool) -> None:
        """F10.1/F10.2 — apprentissage du score, jamais d'exclusion (D3)."""
        source = veille.sources.get(source_id)
        if source is None:
            return
        delta = 5.0 if succes else -5.0
        source.score_fiabilite = max(0.0, min(100.0, source.score_fiabilite + delta))

    # ------------------------------------------------------------------
    # RG-05 — absence de feedback
    # ------------------------------------------------------------------

    def expirer_sans_reponse(self, occurrence_id: str, maintenant: datetime) -> None:
        """RG-05 — onglet fermé sans réponse après le délai (défaut 6 h).

        Comportement paramétrable par veille : ``NON_TRAITE`` (défaut) ou
        ``SATISFAIT``.
        """
        occurrence = self.occurrences[occurrence_id]
        cible = self.cibles[occurrence.cible_id]
        veille = self.veilles[cible.veille_id]

        occurrence.etat = EtatOccurrence.SANS_REPONSE

        if veille.comportement_sans_reponse == "SATISFAIT":
            cible.etat = EtatCible.SATISFAITE
            cible.resolue_le = maintenant
            for oid in cible.occurrence_ids:
                autre = self.occurrences[oid]
                if autre.etat == EtatOccurrence.EN_RESERVE:
                    autre.etat = EtatOccurrence.IGNOREE_DOUBLON
            self._log(
                veille.id, "CIBLE_SATISFAITE",
                f"cible={cible.cle_logique} (sans réponse considérée comme "
                "satisfaite — RG-05)",
                maintenant,
            )
        else:
            cible.etat = EtatCible.EN_ATTENTE_FEEDBACK
            cible.pas_avant = maintenant + timedelta(hours=veille.delai_courtoisie_h)
            self._log(
                veille.id, "SANS_REPONSE",
                f"cible={cible.cle_logique} — délai de courtoisie jusqu'à "
                f"{cible.pas_avant} (RG-05)",
                maintenant,
            )

    # ------------------------------------------------------------------
    # Accesseurs de confort pour les tests
    # ------------------------------------------------------------------

    def occurrences_ouvertes(self, veille_id: Optional[str] = None) -> list[Occurrence]:
        """Toutes les Occurrences ayant été effectivement ouvertes (RG-01),
        dans l'ordre chronologique — c'est le résultat observable que les
        parcours du §5 doivent reproduire exactement."""
        ouvertes = [
            occ for occ in self.occurrences.values()
            if occ.ouverte_le is not None
            and (veille_id is None or self.cibles[occ.cible_id].veille_id == veille_id)
        ]
        return sorted(ouvertes, key=lambda o: o.ouverte_le)
