"""Construit le DATA du tableau de bord, au format attendu par `moteur.html`.

Le moteur et la mise en forme viennent de `build_dashboard.py` (v1) : carte de
chaleur notion × année à quatre échelles, classement, croisement par langage,
Algorithmique contre Théorie, poids par section. Les fonctions de normalisation
— `humanize`, `parse_year_exam`, `EXAM_MERGE`, `LANG_LABEL` — sont reprises
telles quelles pour que la page reste celle qu'elle était.

Trois choses seulement ont changé, et chacune parce que la v1 s'en trouvait
fausse :

1. **le référentiel remplace le fichier `curriculum`.** La v1 projetait sur un
   `curriculum_labels_MPI.json` figé à 124 notions et annonçait « 5 jamais
   tombées ». Le référentiel courant en compte **182**, dont **63** jamais
   attribuées — la section `bdd` en entier. Un curriculum recopié à côté du
   référentiel dérive ; on lit donc directement `referentiel/genere/sections`.
2. **les agrégats publiés viennent de `mesures.py`**, celui que sert déjà
   `etage4 distribution`, et non d'un comptage refait ici.
3. **les questions SANS étiquette sont comptées.** La v1 les écartait en
   silence (`if not etiquettes: continue`). Elles restent hors des `records` —
   le moteur compte des occurrences, pas des questions — mais `flatten` les
   dénombre et la commande les affiche, pour qu'on sache sur quelle part du
   corpus la page ne dit rien.
"""

from __future__ import annotations

import json
import re
from collections import Counter

from . import mesures

# --------------------------------------------------------------------------- #
# Normalisation — repris de build_dashboard.py
# --------------------------------------------------------------------------- #

#: Fusions d'épreuves. Clé → valeur canonique.
EXAM_MERGE = {
    "InfoC-0": "InfoC",
    "TPAlgo-MPI-rapport": "TPAlgo",
    "TPAlgo-rapport": "TPAlgo",
    "InfoLCR-rapport": "LCR",
    "InfoU-exercices": "InfoU",
    "Info-rapport": "Info-rapport",
}

LANG_IS_PROG = {"ocaml", "c", "pseudocode", "mixte"}
LANG_LABEL = {
    "ocaml": "OCaml", "c": "C", "pseudocode": "Pseudo-code",
    "theorique": "Théorique", "mixte": "Mixte", "indetermine": "Indéterminé",
}


def humanize(token: str) -> str:
    """`graphes_repr` → `Graphes repr`."""
    if not token:
        return token
    return token.replace("_", " ").strip().capitalize()


def parse_year_exam(exercice: dict) -> tuple[int | None, str]:
    source = exercice.get("fichier") or exercice.get("exercice_id") or ""
    trouve = re.match(r"(\d{4})_([A-Za-z0-9\-]+)", source)
    if not trouve:
        return None, "Inconnu"
    return int(trouve.group(1)), EXAM_MERGE.get(trouve.group(2), trouve.group(2))


def lang_to_type(langage: str) -> str:
    return "Algorithmique" if langage in LANG_IS_PROG else "Théorie"


# --------------------------------------------------------------------------- #
# Aplatissement
# --------------------------------------------------------------------------- #


def flatten(resultats: list[dict]) -> tuple[list[dict], Counter]:
    """Un enregistrement par ÉTIQUETTE, comme l'attend le moteur."""
    records: list[dict] = []
    stats: Counter = Counter()
    for exercice in resultats:
        annee, epreuve = parse_year_exam(exercice)
        langage_sujet = exercice.get("langage_sujet") or "indetermine"
        filiere = exercice.get("filiere") or "non_marque"
        for question in exercice.get("questions", []):
            stats["questions"] += 1
            langage = question.get("langage") or "indetermine"
            etiquettes = question.get("etiquettes") or []
            if not etiquettes:
                stats["questions_sans_etiquette"] += 1
                continue
            for etiquette in etiquettes:
                identifiant = (etiquette.get("notion_id") or "").strip()
                if not identifiant:
                    continue
                section, notion = (
                    identifiant.split(".", 1) if "." in identifiant
                    else ("(sans section)", identifiant)
                )
                records.append({
                    "annee": annee,
                    "epreuve": epreuve,
                    "section": humanize(section),
                    "notion": humanize(notion),
                    "notion_id": identifiant,
                    "langage": LANG_LABEL.get(langage, humanize(langage)),
                    "langage_sujet": LANG_LABEL.get(langage_sujet, humanize(langage_sujet)),
                    "filiere": filiere,
                    "type": lang_to_type(langage),
                    "poids": 1, "quantite": 1,
                })
                stats["etiquettes"] += 1
    return records, stats


def referentiel_en_curriculum(notions: list[dict]) -> tuple[dict, list]:
    """Le référentiel courant, dans la forme que `build_data` attend.

    Remplace le fichier `curriculum` de la v1 : une copie du référentiel dans un
    JSON à côté finit toujours par décrire un autre référentiel que celui qu'on
    mesure — c'est ce qui a produit le « 5 jamais tombées » de la v1.
    """
    reference, ordre = {}, []
    for notion in notions:
        section = notion.get("section_id") or mesures.section_de(notion["id"])
        affichage = humanize(notion["id"].split(".", 1)[-1])
        reference[affichage] = (humanize(section), None)
        ordre.append(affichage)
    return reference, ordre


def build_data(records: list[dict], curriculum: tuple[dict, list] | None = None) -> dict:
    annees = sorted({r["annee"] for r in records if r["annee"] is not None})
    epreuves = sorted({r["epreuve"] for r in records})
    langages = sorted({r["langage"] for r in records})
    types = sorted({r["type"] for r in records})

    notion_section: dict[str, str] = {}
    notion_type: dict[str, str] = {}
    for r in records:
        notion_section.setdefault(r["notion"], r["section"])
        notion_type.setdefault(r["notion"], r["type"])

    freq = Counter(r["notion"] for r in records)
    present = set(freq)
    if curriculum:
        ref_map, ref_order = curriculum
        for affichage, (section, typ) in ref_map.items():
            notion_section.setdefault(affichage, section)
            if typ:
                notion_type.setdefault(affichage, typ)
        # Une notion jamais posée n'a pas de `type` observé : sans ce repli elle
        # disparaîtrait des vues filtrées par type, c'est-à-dire exactement là
        # où on la cherche.
        for affichage in ref_order:
            notion_type.setdefault(affichage, "Théorie")
        notions_off = list(ref_order) + [n for n in freq if n not in set(ref_order)]
        jamais = [n for n in notions_off if n not in present]
    else:
        notions_off = [n for n, _ in freq.most_common()]
        jamais = []

    sec_freq = Counter(r["section"] for r in records)
    sections = [s for s, _ in sec_freq.most_common()]
    for n in notions_off:
        s = notion_section.get(n)
        if s and s not in sections:
            sections.append(s)
    for n in notions_off:
        t = notion_type.get(n)
        if t and t not in types:
            types.append(t)

    return {
        "records": records,
        "annees": annees,
        "epreuves": epreuves,
        "langages": langages,
        "types": sorted(set(types)),
        "sections": sections,
        "notions_officielles": notions_off,
        "notion_section": notion_section,
        "notion_type": notion_type,
        "jamais_tombes": jamais,
    }


# --------------------------------------------------------------------------- #


def construire(
    resultats: list[dict],
    notions: list[dict],
) -> tuple[dict, mesures.Agregat, Counter]:
    """Rend (DATA, agrégat de référence, statistiques).

    L'agrégat vient de `mesures.agreger` — le même que `etage4 distribution` —
    et sert au récapitulatif console. La page, elle, ne montre que les vues du
    moteur.
    """
    records, stats = flatten(resultats)
    curriculum = referentiel_en_curriculum(notions)
    data = build_data(records, curriculum)
    agregat = mesures.agreger(mesures.aplatir(resultats))
    return data, agregat, stats


def serialiser(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, allow_nan=False)
