"""Confrontation du corpus au référentiel.

La méthode qui a produit 10 des 182 notions, sortie du scratchpad où elle
mourait. Elle doit tourner à l'identique sur les 33 nouveaux sujets, sinon les
notions du second lot ne seront pas comparables à celles du premier.

Trois choix la définissent, tous payés par une erreur :

1. **Quatre zones de texte**, pas une. La technique de preuve attendue est
   nommée dans le CORRIGÉ, presque jamais dans la question. La première passe
   ne lisait que les énoncés et a manqué deux disjonctions de cas.
2. **La règle des deux fichiers distincts.** Dix attestations dans un seul
   sujet ne décrivent que ce sujet. Le comptage se fait par fichier, jamais par
   occurrence.
3. **Un anti-motif facultatif.** `dénombrable` n'est pas `dénombrer` : sans lui,
   4 attestations sur 6 étaient fausses et la notion passait à tort.

La sortie ne juge pas et ne crée rien. Elle ramène des passages avec leur
provenance ; la rédaction de la notion reste humaine.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

MINIMUM_PAR_DEFAUT = 2
CONTEXTE_PAR_DEFAUT = 80


@dataclass(frozen=True)
class Sonde:
    nom: str
    motif: str
    notion: str | None = None
    statut: str = "ouverte"
    anti: str | None = None
    commentaire: str | None = None

    def compilee(self) -> re.Pattern:
        return re.compile(self.motif, re.I)

    def anti_compile(self) -> re.Pattern | None:
        return re.compile(self.anti, re.I) if self.anti else None


@dataclass
class Attestation:
    fichier: str
    origine: str
    zone: str
    extrait: str


@dataclass
class Resultat:
    sonde: Sonde
    attestations: list[Attestation] = field(default_factory=list)
    ecartees: int = 0  # retirées par l'anti-motif

    @property
    def fichiers(self) -> list[str]:
        return sorted({a.fichier for a in self.attestations})

    def admise(self, minimum: int) -> bool:
        return len(self.fichiers) >= minimum

    def verdict(self, minimum: int) -> str:
        n = len(self.fichiers)
        if n >= minimum:
            return f"ADMISE — {n} fichiers distincts"
        return f"refusée — {n} fichier(s) distinct(s), il en faut {minimum}"


def charger_sondes(chemin: Path) -> tuple[list[Sonde], dict[str, Any]]:
    if not chemin.is_file():
        raise SystemExit(f"Fichier de sondes introuvable : {chemin}")
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    sondes = []
    for brute in donnees.get("sondes") or []:
        if not brute.get("nom") or not brute.get("motif"):
            raise SystemExit(f"Sonde sans nom ou sans motif : {brute!r}")
        try:
            re.compile(brute["motif"])
        except re.error as err:  # une sonde illisible doit casser au chargement
            raise SystemExit(f"Sonde {brute['nom']} : motif invalide — {err}")
        sondes.append(
            Sonde(
                nom=brute["nom"],
                motif=brute["motif"],
                notion=brute.get("notion"),
                statut=brute.get("statut", "ouverte"),
                anti=brute.get("anti"),
                commentaire=brute.get("commentaire"),
            )
        )
    return sondes, donnees


def zones(chemins: list[Path]) -> Iterator[tuple[str, str, str, str]]:
    """(fichier, origine, zone, texte) sur les quatre zones du corpus extrait."""
    for chemin in sorted(chemins):
        document = json.loads(chemin.read_text(encoding="utf-8"))
        fichier = document.get("fichier") or chemin.stem
        for exercice in document.get("exercices") or []:
            titre = (exercice.get("titre") or exercice.get("id") or "?")[:34]
            if exercice.get("preambule"):
                yield fichier, f"{titre} (préambule)", "preambule", exercice["preambule"]
            if exercice.get("corrige_non_attribue"):
                yield (fichier, f"{titre} (corrigé)", "corrige_non_attribue",
                       exercice["corrige_non_attribue"])
            for question in exercice.get("questions") or []:
                repere = f"{titre[:28]} Q{question.get('numero')}"
                if question.get("texte"):
                    yield fichier, repere, "question", question["texte"]
                if question.get("solution"):
                    yield fichier, f"{repere} [sol]", "solution", question["solution"]


def confronter(
    liste_zones: list[tuple[str, str, str, str]],
    sondes: list[Sonde],
    contexte: int = CONTEXTE_PAR_DEFAUT,
) -> list[Resultat]:
    resultats = []
    for sonde in sondes:
        motif, anti = sonde.compilee(), sonde.anti_compile()
        resultat = Resultat(sonde=sonde)
        for fichier, origine, zone, texte in liste_zones:
            trouve = motif.search(texte or "")
            if not trouve:
                continue
            debut = max(0, trouve.start() - contexte)
            extrait = " ".join((texte[debut : trouve.end() + contexte]).split())
            if anti and anti.search(extrait):
                resultat.ecartees += 1
                continue
            resultat.attestations.append(
                Attestation(fichier=fichier, origine=origine, zone=zone, extrait=extrait)
            )
        resultats.append(resultat)
    return resultats


def en_json(
    resultats: list[Resultat], liste_zones: list, chemins: list[Path], minimum: int
) -> dict[str, Any]:
    """Sortie relisible : sert à ne pas refaire la lecture au lot suivant."""
    return {
        "_note": (
            "Confrontation du corpus au référentiel. Une candidate n'est admise "
            f"qu'attestée dans au moins {minimum} fichiers distincts. Ce fichier "
            "conserve les attestations exactes pour que le lot suivant n'ait qu'à "
            "chercher la seconde."
        ),
        "_corpus_lu": {
            "fichiers": len({z[0] for z in liste_zones}),
            "zones": len(liste_zones),
            "sources": [c.name for c in sorted(chemins)],
        },
        "regle": {"fichiers_distincts_minimum": minimum},
        "sondes": [
            {
                "nom": r.sonde.nom,
                "notion": r.sonde.notion,
                "statut_declare": r.sonde.statut,
                "verdict": r.verdict(minimum),
                "fichiers_distincts": len(r.fichiers),
                "fichiers": r.fichiers,
                "zones_attestees": len(r.attestations),
                "ecartees_par_anti_motif": r.ecartees,
                "attestations": [
                    {
                        "fichier": a.fichier,
                        "origine": a.origine,
                        "zone": a.zone,
                        "extrait": a.extrait[:300],
                    }
                    for a in r.attestations[:12]
                ],
            }
            for r in resultats
        ],
    }
