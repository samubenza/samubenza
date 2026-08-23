#!/usr/bin/env python3
"""Lance le Collecteur en continu sur trois sources réelles (jalon J2, §12.3).

Critère de validation du jalon : *« en laissant tourner sur trois sites
réels pendant 48 h, le journal montre les Cibles correctement identifiées
et dédupliquées — toujours sans ouvrir d'onglet »*.

Ce script exécute exactement ça : un cycle de collecte périodique (M4→M5→
M6→M8), rien d'autre. Aucun onglet n'est ouvert, aucun navigateur n'est
piloté (RG-10 est un sujet du jalon J7).

⚠️ **Ne peut pas être exécuté depuis la session Claude Code où ce dépôt a
été développé** : l'accès réseau sortant y est restreint par une politique
d'égress qui n'autorise que quelques hôtes (PyPI, npm, GitHub...) — les
trois sites ci-dessous en sont exclus (voir docs/DECISIONS-J2.md). Lancez
ce script depuis votre machine, ou tout environnement avec un accès
Internet normal.

Usage :
    pip install -e .
    python scripts/collecte_continue.py --duree-heures 48 --intervalle-min 15
    # Ctrl+C à tout moment : le journal accumulé jusque-là est conservé.

Les trois sources ci-dessous sont des exemples raisonnables mais non
garantis à long terme : la structure HTML d'un site évolue (F3.4). Si un
sélecteur ne trouve plus rien, le journal l'indiquera (COLLECTE_ECHEC ou
candidats_vus=0) — ajustez alors `extraire_*` ci-dessous à la structure
réelle de la page au moment de l'exécution.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bs4 import BeautifulSoup  # noqa: E402

from veille_agent import (  # noqa: E402
    CandidatBrut,
    ModeSources,
    Orchestrateur,
    Patron,
    Politesse,
    Source,
    SourceCollecte,
    Veille,
    executer_cycle,
)
from veille_agent.collecteur import DELAI_MIN_ENTRE_CYCLES_S  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Flux RSS statique — actualité technique
# ---------------------------------------------------------------------------
# Hacker News (hnrss.org est un générateur RSS tiers pensé pour être lu par
# des agrégateurs — flux stable, robots.txt permissif). Toute autre source
# d'actualité technique disposant d'un flux RSS convient tout autant.
URL_RSS_ACTUALITE = "https://hnrss.org/frontpage"


# ---------------------------------------------------------------------------
# 2. Site de listing HTML — résultats sportifs
# ---------------------------------------------------------------------------
# Exemple : une page Wikipédia de résultats de championnat. À adapter : les
# tableaux Wikipédia varient beaucoup d'une page à l'autre (§F3.4 — pas de
# structure universelle), donc `extraire_resultats_sportifs` ci-dessous
# est un point de départ à ajuster à la page réellement choisie.
URL_LISTING_SPORTIF = "https://en.wikipedia.org/wiki/2024%E2%80%9325_Premier_League"


def extraire_resultats_sportifs(soupe: BeautifulSoup) -> list[CandidatBrut]:
    candidats = []
    for ligne in soupe.select("table.results-table tr, table.wikitable tr"):
        cellules = ligne.find_all(["td", "th"])
        lien = ligne.find("a", href=True)
        if len(cellules) < 2 or lien is None:
            continue
        texte = " ".join(c.get_text(strip=True) for c in cellules if c.get_text(strip=True))
        if not texte:
            continue
        candidats.append(
            CandidatBrut(titre=texte[:200], url="https://en.wikipedia.org" + lien["href"])
        )
    return candidats


# ---------------------------------------------------------------------------
# 3. Site sériel — blog/webcomic à chapitres numérotés
# ---------------------------------------------------------------------------
# xkcd publie une page d'archive listant tous les strips, chacun avec un
# numéro dans son URL (.../2960/) — un cas d'école pour SORTIE_SÉRIELLE.
URL_ARCHIVE_SERIE = "https://xkcd.com/archive/"
NOM_SERIE = "xkcd"


def extraire_archive_serie(soupe: BeautifulSoup) -> list[CandidatBrut]:
    conteneur = soupe.select_one("#middleContainer") or soupe
    candidats = []
    for lien in conteneur.find_all("a", href=True):
        candidats.append(
            CandidatBrut(
                titre=lien.get_text(strip=True) or lien["href"],
                url="https://xkcd.com" + lien["href"],
                date_publication_brute=lien.get("title"),
            )
        )
    return candidats


def construire_orchestrateur() -> tuple[Orchestrateur, list[SourceCollecte]]:
    orch = Orchestrateur()

    orch.ajouter_veille(Veille(
        id="v-actu-tech", nom="Actualité technique (démo J2)",
        patron=Patron.ACTUALITE_THEMATIQUE, mode_sources=ModeSources.CIBLE,
    ))
    orch.ajouter_source("v-actu-tech", Source(id="hn", veille_id="v-actu-tech", nom="Hacker News"))

    orch.ajouter_veille(Veille(
        id="v-sport", nom="Résultats sportifs (démo J2)",
        patron=Patron.RESULTAT_EVENEMENTIEL, mode_sources=ModeSources.CIBLE,
    ))
    orch.ajouter_source("v-sport", Source(id="wikipedia", veille_id="v-sport", nom="Wikipédia"))

    orch.ajouter_veille(Veille(
        id="v-serie", nom=f"{NOM_SERIE} — nouveaux numéros (démo J2)",
        patron=Patron.SORTIE_SERIELLE, mode_sources=ModeSources.CIBLE,
    ))
    orch.ajouter_source("v-serie", Source(id="xkcd", veille_id="v-serie", nom=NOM_SERIE))

    sources = [
        SourceCollecte(
            veille_id="v-actu-tech", source_id="hn", type_collecte="RSS", url=URL_RSS_ACTUALITE,
        ),
        SourceCollecte(
            veille_id="v-sport", source_id="wikipedia", type_collecte="LISTING_HTML",
            url=URL_LISTING_SPORTIF, extraire_candidats=extraire_resultats_sportifs,
        ),
        SourceCollecte(
            veille_id="v-serie", source_id="xkcd", type_collecte="LISTING_HTML",
            url=URL_ARCHIVE_SERIE, extraire_candidats=extraire_archive_serie, nom_serie=NOM_SERIE,
        ),
    ]
    return orch, sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duree-heures", type=float, default=48.0)
    parser.add_argument("--intervalle-min", type=float, default=15.0, help="≥ 5 min (F4.1.1)")
    parser.add_argument("--journal-out", type=Path, default=Path("journal_collecte_j2.jsonl"))
    args = parser.parse_args()

    intervalle_s = max(args.intervalle_min * 60, DELAI_MIN_ENTRE_CYCLES_S)
    fin = time.monotonic() + args.duree_heures * 3600

    orch, sources = construire_orchestrateur()
    politesse = Politesse()
    derniere_taille_journal = 0
    cycle_num = 0

    print(f"Démarrage : cycles toutes les {intervalle_s / 60:.0f} min, "
          f"pendant {args.duree_heures:.0f} h. Journal → {args.journal_out}")

    with args.journal_out.open("a", encoding="utf-8") as f_journal:
        try:
            while time.monotonic() < fin:
                cycle_num += 1
                maintenant = datetime.now(timezone.utc)
                bilan = executer_cycle(orch, sources, maintenant, politesse=politesse)

                for evt in orch.journal[derniere_taille_journal:]:
                    f_journal.write(json.dumps({
                        "id": evt.id, "veille_id": evt.veille_id, "type": evt.type,
                        "detail": evt.detail, "horodatage": evt.horodatage.isoformat(),
                    }, ensure_ascii=False) + "\n")
                derniere_taille_journal = len(orch.journal)
                f_journal.flush()

                print(f"[cycle {cycle_num}] {maintenant.isoformat()} — " + " | ".join(
                    f"{vid}: +{b['candidats_vus']} candidats, "
                    f"+{b['cibles_nouvelles']} cibles nouvelles, "
                    f"{b['cibles_apres']} cibles au total"
                    for vid, b in bilan.items()
                ))

                if time.monotonic() + intervalle_s < fin:
                    time.sleep(intervalle_s)
                else:
                    break
        except KeyboardInterrupt:
            print("\nInterrompu — journal conservé jusqu'au dernier cycle.")

    print(f"Terminé après {cycle_num} cycle(s). "
          f"Cibles totales : {len(orch.cibles)}. Occurrences : {len(orch.occurrences)}. "
          f"Journal : {args.journal_out} ({len(orch.journal)} entrées).")


if __name__ == "__main__":
    main()
