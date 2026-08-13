"""Configuration — exclusivement par variables d'environnement, aucun chemin en dur."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _chemin(var: str, defaut: str | None = None) -> Path:
    brut = os.environ.get(var, defaut)
    if not brut:
        raise SystemExit(
            f"Variable d'environnement {var} absente et sans valeur par défaut. "
            f"Voir .env.example."
        )
    return Path(brut).expanduser()


def _entier(var: str, defaut: int) -> int:
    return int(os.environ.get(var, defaut))


def _drapeau(var: str, defaut: bool) -> bool:
    brut = os.environ.get(var)
    if brut is None:
        return defaut
    return brut.strip().lower() in {"1", "true", "oui", "yes", "on"}


@dataclass(frozen=True)
class Profil:
    """Contenu spécifique à la matière. Le code n'en connaît que la forme."""

    chemin: Path
    donnees: dict[str, Any]

    @property
    def matiere(self) -> str:
        return self.donnees["matiere"]

    @property
    def version_prompt(self) -> str:
        return self.donnees.get("version_prompt", "p1")

    @property
    def critere_admission(self) -> str:
        return self.donnees["critere_admission"].strip()

    @property
    def valeurs_langage(self) -> list[str]:
        return list(self.donnees["axe_langage"]["valeurs"])

    @property
    def genres(self) -> dict[str, str]:
        return dict(self.donnees["genres"])

    @property
    def sections_cibles(self) -> list[dict[str, str]]:
        return list(self.donnees.get("sections_cibles", []))

    @property
    def sections_programme_attendues(self) -> int:
        """Combien de sections la segmentation trouve sur un vrai programme.

        Sert au garde-fou d'entrée, et à lui seul : les identifiants de section
        du PROGRAMME (`1`, `3.2`, `4.3`) et ceux du profil (`preuve`,
        `langages`) vivent dans deux espaces de noms distincts, on ne peut donc
        pas vérifier les seconds avant que le modèle ait tranché.
        """
        return int((self.donnees.get("programme") or {}).get("sections_attendues", 0))

    @property
    def part_minimale_programme(self) -> float:
        return float((self.donnees.get("programme") or {}).get("part_minimale", 0.5))

    @property
    def part_numerotee_minimale(self) -> float:
        """Part des sections dont l'identifiant est une numérotation
        hiérarchique. C'est la FORME, et non le nombre, qui sépare un programme
        d'un rapport de jury."""
        return float((self.donnees.get("programme") or {}).get("part_numerotee_minimale", 0.0))

    @property
    def ids_sections_cibles(self) -> list[str]:
        return [s["id"] for s in self.sections_cibles]

    @property
    def motifs_restrictifs(self) -> list[str]:
        return list(self.donnees["mentions_restrictives"]["motifs"])

    @property
    def portees_restrictives(self) -> dict[str, str]:
        return dict(self.donnees["mentions_restrictives"]["portees"])

    @property
    def titres_exclus(self) -> list[str]:
        return list(self.donnees["exclusions_deterministes"].get("titres_sections", []))

    @property
    def prefixes_exclus(self) -> list[str]:
        return list(
            self.donnees["exclusions_deterministes"].get("prefixes_numerotation", [])
        )

    @property
    def genres_ecartes(self) -> set[str]:
        return set(self.donnees["exclusions_deterministes"].get("genres_ecartes", []))

    @property
    def cibles(self) -> dict[str, int]:
        return dict(self.donnees.get("cibles", {}))

    @classmethod
    def charger(cls, chemin: Path) -> "Profil":
        if not chemin.is_file():
            raise SystemExit(f"Profil introuvable : {chemin}")
        donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        manquants = [
            c
            for c in ("matiere", "critere_admission", "axe_langage", "genres")
            if c not in donnees
        ]
        if manquants:
            raise SystemExit(f"Profil {chemin} : clés manquantes {manquants}")
        return cls(chemin=chemin, donnees=donnees)


@dataclass(frozen=True)
class Config:
    programme: Path
    profil: Profil
    sortie: Path
    journal: Path
    fournisseur: str
    modele: str
    effort: str
    max_tokens: int
    fallbacks: bool
    reflexion: bool
    etalon: Path | None
    version_referentiel: str

    @classmethod
    def depuis_env(cls) -> "Config":
        racine = Path(os.environ.get("ETAGE0_RACINE", ".")).expanduser().resolve()
        profil = Profil.charger(
            _chemin("ETAGE0_PROFIL", str(racine / "profils" / "informatique-mpi.yaml"))
        )
        etalon_brut = os.environ.get("ETAGE0_ETALON")
        return cls(
            programme=_chemin("ETAGE0_PROGRAMME"),
            profil=profil,
            sortie=_chemin("ETAGE0_SORTIE", str(racine / "referentiel" / "genere")),
            journal=_chemin("ETAGE0_JOURNAL", str(racine / ".etage0" / "journal.jsonl")),
            fournisseur=os.environ.get("ETAGE0_FOURNISSEUR", "anthropic"),
            modele=os.environ.get("ETAGE0_MODELE", "claude-opus-5"),
            effort=os.environ.get("ETAGE0_EFFORT", "high"),
            max_tokens=_entier("ETAGE0_MAX_TOKENS", 16000),
            fallbacks=_drapeau("ETAGE0_FALLBACKS", True),
            reflexion=_drapeau("ETAGE0_REFLEXION", True),
            etalon=Path(etalon_brut).expanduser() if etalon_brut else None,
            version_referentiel=os.environ.get("ETAGE0_VERSION", "1.0.0"),
        )
