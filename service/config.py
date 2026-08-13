"""Configuration du service et garde-fou de chemins."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Racine du code installé : `config/`, `profils/` et `referentiel/` y vivent,
#: et les sous-processus tournent avec ce répertoire courant pour que les
#: chemins par défaut des étages (`config/mesure.yaml`,
#: `referentiel/genere/sections`) continuent de résoudre.
RACINE_CODE = Path(os.environ.get("SERVICE_RACINE_CODE", "/app")).resolve()

#: Volume de travail : corpus, sorties, journal, état des tâches. C'est le SEUL
#: endroit où le service accepte de lire et d'écrire ce qui vient du client.
TRAVAIL = Path(os.environ.get("SERVICE_TRAVAIL", "/travail")).resolve()

TACHES = TRAVAIL / "taches"
JOURNAL_ETAGES = Path(os.environ.get("ETAGE0_JOURNAL", str(TRAVAIL / "journal" / "journal.jsonl")))

#: Une seule tâche lourde à la fois. L'étiquetage appelle l'API et se paie :
#: deux passes concurrentes sur le même corpus doubleraient la facture sans
#: rien apporter, le journal ne dédoublonnant qu'APRÈS l'appel.
COMMANDES_LOURDES = frozenset({"etiqueter"})

DUREE_MAX = int(os.environ.get("SERVICE_DUREE_MAX", 26 * 3600))
SORTIE_MAX = int(os.environ.get("SERVICE_SORTIE_MAX", 20_000))


class CheminRefuse(ValueError):
    """Chemin hors du volume de travail."""


def resoudre(chemin: str, doit_exister: bool = True) -> Path:
    """Résout un chemin client sous `TRAVAIL`, ou refuse.

    La vérification porte sur le chemin RÉSOLU, pas sur la chaîne : filtrer
    `..` par recherche de motif laisse passer les liens symboliques et les
    chemins absolus, et c'est le genre de contrôle qu'on croit avoir fait.
    """
    if not chemin or chemin.strip() != chemin:
        raise CheminRefuse(f"chemin vide ou mal formé : {chemin!r}")
    candidat = Path(chemin)
    absolu = (candidat if candidat.is_absolute() else TRAVAIL / candidat).resolve()
    try:
        absolu.relative_to(TRAVAIL)
    except ValueError:
        raise CheminRefuse(
            f"chemin hors du volume de travail : {chemin!r} → {absolu} "
            f"(autorisé : {TRAVAIL})"
        ) from None
    if doit_exister and not absolu.exists():
        raise CheminRefuse(f"introuvable : {chemin!r}")
    return absolu


def resoudre_plusieurs(chemins: list[str], doit_exister: bool = True) -> list[Path]:
    if not chemins:
        raise CheminRefuse("aucun chemin fourni")
    return [resoudre(c, doit_exister) for c in chemins]


def environnement_etages() -> dict[str, str]:
    """L'environnement passé aux sous-processus.

    `ANTHROPIC_API_KEY` est reprise de l'environnement du SERVICE et jamais du
    corps de la requête : une clé qui transite par HTTP finit dans les journaux
    de l'orchestrateur.
    """
    env = dict(os.environ)
    env.setdefault("ETAGE0_RACINE", str(RACINE_CODE))
    env.setdefault("ETAGE0_JOURNAL", str(JOURNAL_ETAGES))
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


@dataclass(frozen=True)
class Etat:
    cle_presente: bool
    travail: Path
    code: Path


def etat_environnement() -> Etat:
    return Etat(
        cle_presente=bool(os.environ.get("ANTHROPIC_API_KEY")),
        travail=TRAVAIL,
        code=RACINE_CODE,
    )
