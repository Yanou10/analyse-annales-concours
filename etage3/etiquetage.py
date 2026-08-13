"""Orchestration de l'étiquetage, et validation des étiquettes rendues.

Le rejet est au grain de l'ÉTIQUETTE : une justification non littérale fait
tomber cette étiquette-là, pas la question, et encore moins l'exercice. C'est
la leçon de la section §4.3 du référentiel, perdue en entier pour une unité
mal étiquetée.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .contrats import MIN_MOTS_JUSTIFICATION, SANS_OBJET


def _ou_none(valeur: str | None) -> str | None:
    """`sans_objet` et la chaîne vide sont les null du mode strict."""
    return valeur or None if valeur != SANS_OBJET else None


#: Balisage de conversion PDF→markdown que le modèle ne peut pas recopier : il
#: lit `join\_right` et écrit `join_right`, il lit `*O*(*h*(t))` et écrit
#: `O(h(t))`. Le retirer des DEUX côtés maintient l'exigence de littéralité —
#: la suite des caractères doit correspondre — sans punir un balisage dont le
#: modèle n'est pas responsable. Sans cela, 17 étiquettes sur 32 tombaient.
RE_BALISAGE = re.compile(r"<[^>]{0,40}>|[\\*_`#$]|\{|\}")

#: Même logique un cran plus bas : la source écrit `\tau`, le modèle écrit `τ` ;
#: la source `⩽`, le modèle `≤`. On compare du TEXTE, pas du LaTeX — les deux
#: notations doivent se rejoindre sur une forme commune.
SYMBOLES = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "ζ": "zeta", "η": "eta", "θ": "theta", "λ": "lambda", "μ": "mu", "ν": "nu",
    "ξ": "xi", "π": "pi", "ρ": "rho", "σ": "sigma", "τ": "tau", "φ": "phi",
    "χ": "chi", "ψ": "psi", "ω": "omega", "Γ": "gamma", "Δ": "delta",
    "Θ": "theta", "Λ": "lambda", "Σ": "sigma", "Φ": "phi", "Ω": "omega",
    "⩽": "<=", "≤": "<=", "⩾": ">=", "≥": ">=", "≠": "!=", "⟺": "<=>",
    "⇔": "<=>", "⟹": "=>", "⇒": "=>", "−": "-", "–": "-", "—": "-",
    "′": "'", "’": "'", "“": '"', "”": '"', "×": "x", "·": ".", "∈": "in",
}
RE_SYMBOLE = re.compile("|".join(map(re.escape, SYMBOLES)))


def _normaliser(texte: str) -> str:
    """Balisage retiré, symboles unifiés, mise en page ignorée, casse ignorée.

    La comparaison porte sur la SUITE DE CARACTÈRES, espaces exclus. C'est
    volontairement insensible à la mise en page — la source écrit `τ (G)` là où
    le modèle écrit `τ(G)` — mais cela reste un test de littéralité : une
    paraphrase change les mots, une élision retire du texte, et les deux
    échouent toujours. Ne pas relâcher au-delà.
    """
    sans_balisage = RE_BALISAGE.sub("", texte or "")
    unifie = RE_SYMBOLE.sub(lambda m: SYMBOLES[m.group(0)], sans_balisage)
    return re.sub(r"\s+", "", unifie).lower()


@dataclass
class RejetEtiquette:
    question_id: str
    notion_id: str
    code: str
    detail: str


@dataclass
class ResultatExercice:
    exercice_id: str
    fichier: str
    filiere: str
    sections_retenues: list[str] = field(default_factory=list)
    langage_sujet: str | None = None
    questions: list[dict[str, Any]] = field(default_factory=list)
    rejets: list[RejetEtiquette] = field(default_factory=list)
    jetons: dict[str, int] = field(default_factory=dict)


def charger_referentiel(dossier: Path) -> tuple[list[dict], dict[str, list[dict]]]:
    notions, par_section = [], {}
    for fichier in sorted(dossier.glob("*.yaml")):
        donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
        section = (donnees.get("section") or {}).get("id")
        liste = []
        for notion in donnees.get("notions") or []:
            enrichie = {**notion, "section_id": section}
            notions.append(enrichie)
            liste.append(enrichie)
        if section:
            par_section[section] = liste
    return notions, par_section


def charger_exclusions(chemin: Path) -> list[dict[str, Any]]:
    if not chemin.is_file():
        return []
    return json.loads(chemin.read_text(encoding="utf-8"))


def charger_corpus(chemins: list[Path]) -> list[dict[str, Any]]:
    documents = []
    for chemin in chemins:
        documents.append(json.loads(chemin.read_text(encoding="utf-8")))
    return documents


def valider_etiquettes(
    charge: dict[str, Any],
    exercice: dict[str, Any],
    ids_notions: set[str],
) -> ResultatExercice:
    """Filtre les étiquettes dont la justification n'est pas un extrait littéral.

    Le contrôle porte sur l'énoncé de la question SEUL, pas sur le préambule ni
    sur la solution : c'est la consigne qui déclenche une notion, et autoriser
    le préambule laisserait passer une justification tirée du contexte, qui ne
    prouve rien sur la question.
    """
    resultat = ResultatExercice(
        exercice_id=exercice["id"], fichier="", filiere=exercice.get("filiere", "")
    )
    resultat.langage_sujet = charge.get("langage_sujet")
    par_id = {q["id"]: q for q in exercice["questions"]}
    vues: set[str] = set()

    for rendue in charge.get("questions") or []:
        question_id = rendue.get("question_id")
        source = par_id.get(question_id)
        if source is None or question_id in vues:
            continue
        vues.add(question_id)
        enonce = _normaliser(source["texte"])

        gardees = []
        for etiquette in rendue.get("etiquettes") or []:
            notion_id = etiquette.get("notion_id")
            justification = (etiquette.get("justification") or "").strip()
            if notion_id not in ids_notions:
                resultat.rejets.append(
                    RejetEtiquette(question_id, str(notion_id), "notion_hors_selection",
                                   "notion absente des sections retenues")
                )
                continue
            if len(justification.split()) < MIN_MOTS_JUSTIFICATION:
                resultat.rejets.append(
                    RejetEtiquette(question_id, notion_id, "justification_trop_courte",
                                   f"{len(justification.split())} mot(s) : {justification!r}")
                )
                continue
            if _normaliser(justification) not in enonce:
                resultat.rejets.append(
                    RejetEtiquette(question_id, notion_id, "justification_non_litterale",
                                   f"absente de l'énoncé : {justification[:70]!r}")
                )
                continue
            if any(g["notion_id"] == notion_id for g in gardees):
                resultat.rejets.append(
                    RejetEtiquette(question_id, notion_id, "etiquette_dupliquee", "")
                )
                continue
            gardees.append({"notion_id": notion_id, "justification": justification})

        statut = rendue.get("statut")
        if statut == "ok" and not gardees:
            # Toutes les étiquettes sont tombées : la question n'est pas
            # étiquetée, et le dire vaut mieux que laisser un `ok` vide.
            statut = "indecidable"
        resultat.questions.append(
            {
                "question_id": question_id,
                "statut": statut,
                "raison_hors_referentiel": _ou_none(rendue.get("raison_hors_referentiel")),
                "objet_hors_referentiel": _ou_none(rendue.get("objet_hors_referentiel")),
                "langage": rendue.get("langage"),
                "figure_manquante_extraction": source.get("figure_manquante", False),
                "etiquettes": gardees,
            }
        )

    for manquante in [q["id"] for q in exercice["questions"] if q["id"] not in vues]:
        resultat.questions.append(
            {
                "question_id": manquante,
                "statut": "indecidable",
                "raison_hors_referentiel": None,
                "objet_hors_referentiel": None,
                "langage": None,
                "figure_manquante_extraction": par_id[manquante].get("figure_manquante", False),
                "etiquettes": [],
                "note": "aucune décision rendue par le modèle",
            }
        )
    return resultat
