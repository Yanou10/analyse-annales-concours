"""Détection et classement des mentions restrictives du programme.

Produit `exclusions.json`, dont l'unique rôle est de motiver un statut
`hors_referentiel` LISIBLE à l'étage 3 (« hors programme : automates à pile »)
au lieu d'un panier opaque.

Point de conception essentiel : les mentions ne sont pas de même nature.
Seule la portée `objet_exclu` autorise un `hors_referentiel`. Les deux autres
bornent l'enseignement, pas l'épreuve — un concours peut poser une technique
« non exigible » en la rappelant dans son énoncé, et c'est exactement ce qui
se produit dans le corpus.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

RE_PHRASE = re.compile(r"[^.;]*?(?:{motifs})[^.;]*[.;]?", re.IGNORECASE)


@dataclass(frozen=True)
class Mention:
    id: str
    phrase: str
    ligne: int
    section: str


def detecter(chemin: Path, motifs: list[str], sections_par_ligne: dict[int, str]) -> list[Mention]:
    motif = "|".join(re.escape(m) for m in motifs)
    regex = re.compile(RE_PHRASE.pattern.format(motifs=motif), re.IGNORECASE)

    mentions: list[Mention] = []
    lignes = chemin.read_text(encoding="utf-8").splitlines()
    compteur = 0
    for numero, ligne in enumerate(lignes, start=1):
        nettoyee = re.sub(r"<[^>]+>|\*\*|\|", " ", ligne)
        nettoyee = re.sub(r"\s+", " ", nettoyee).strip()
        if not nettoyee:
            continue
        for trouve in regex.finditer(nettoyee):
            phrase = trouve.group(0).strip()
            if len(phrase) < 15:
                continue
            compteur += 1
            mentions.append(
                Mention(
                    id=f"m{compteur:03d}",
                    phrase=phrase,
                    ligne=numero,
                    section=_section_de(numero, sections_par_ligne),
                )
            )
    return mentions


def _section_de(ligne: int, sections_par_ligne: dict[int, str]) -> str:
    candidate = ""
    for depart in sorted(sections_par_ligne):
        if depart <= ligne:
            candidate = sections_par_ligne[depart]
        else:
            break
    return candidate


def message_mentions(mentions: list[Mention]) -> str:
    corps = "\n".join(
        f"[{m.id}] (section {m.section or '?'}, ligne {m.ligne})\n  {m.phrase}"
        for m in mentions
    )
    return f"{len(mentions)} mention(s) à classer.\n\n{corps}"


def fusionner(mentions: list[Mention], classements: list[dict]) -> list[dict]:
    par_id = {m.id: m for m in mentions}
    resultat: list[dict] = []
    for classement in classements:
        mention = par_id.get(classement["mention_id"])
        if mention is None:
            continue
        entree = asdict(mention)
        entree.update(
            {
                "portee": classement["portee"],
                "objet": classement["objet"],
                "justification": classement["justification"],
                # Seul `objet_exclu` peut motiver un hors_referentiel en aval.
                "attribuable": False,
                "autorise_hors_referentiel": classement["portee"] == "objet_exclu",
            }
        )
        resultat.append(entree)
    return resultat
