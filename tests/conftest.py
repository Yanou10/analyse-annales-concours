"""Fixtures partagées : un profil réel, et de quoi fabriquer des unités."""

from __future__ import annotations

from pathlib import Path

import pytest

from etage0.config import Profil
from etage0.segmentation import Section, Unite

RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def profil() -> Profil:
    """Le profil réel, et non un double : les tests portent sur des règles dont
    les seuils viennent du profil (valeurs de langage, sections cibles)."""
    return Profil.charger(RACINE / "profils" / "informatique-mpi.yaml")


@pytest.fixture
def section() -> Section:
    return Section(
        numero="4.3",
        titre="Décomposition d'un problème en sous-problèmes",
        niveau=1,
        ligne=336,
        chemin=("4", "4.3"),
    )


@pytest.fixture
def fabrique_unite(section):
    def _unite(numero: int, genre: str = "table") -> Unite:
        return Unite(
            id=f"4.3/{genre}/{numero:02d}",
            section=section,
            genre=genre,
            notions="Notions de l'unité",
            commentaires="Commentaires de l'unité",
            texte="",
            ligne_debut=340 + numero,
            ligne_fin=341 + numero,
            semestre="S2",
        )

    return _unite


@pytest.fixture
def fabrique_notion():
    """Une notion valide, que chaque test dégrade sur le seul point qu'il vise."""

    def _notion(slug: str, **surcharges):
        notion = {
            "slug": slug,
            "libelle": f"Concevoir {slug.replace('_', ' ')}",
            "definition_operatoire": (
                "La question demande de mettre en œuvre l'action décrite et d'en "
                "justifier la correction."
            ),
            "declencheurs": ["Proposer un algorithme qui …", "Justifier que …"],
            "exclusions": [{"motif": "cas voisin à ne pas confondre", "voir_slug": None}],
            "langages_plausibles": ["theorique"],
            "origine_cellule": "notions",
            "section_cible": "strategies",
        }
        notion.update(surcharges)
        return notion

    return _notion
