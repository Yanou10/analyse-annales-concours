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

#: Espace de travail temporaire : un dossier par tâche, détruit à la fin QUOI
#: QU'IL ARRIVE. Il est sur le volume et non dans /tmp, pour que le conteneur
#: n'enfle pas et que le contenu soit inspectable pendant l'exécution.
ESPACES = TRAVAIL / "espaces"

#: Le journal reste LOCAL — c'est la reprise sur appels déjà payés, elle doit
#: être rapide — mais segmenté par signature : deux campagnes menées sur des
#: référentiels différents n'ont rien à partager, et les mélanger ferait
#: réutiliser des étiquettes calculées contre un autre référentiel.
JOURNAUX = TRAVAIL / "journal"


def journal_de(signature: str) -> Path:
    return JOURNAUX / f"{signature}.jsonl"


# --------------------------------------------------------------------------- #
# MinIO — l'entrée et la sortie du service
# --------------------------------------------------------------------------- #
MINIO_URL = os.environ.get("MINIO_URL", "minio:9000")
MINIO_CLE = os.environ.get("MINIO_ACCESS_KEY") or os.environ.get("MINIO_ROOT_USER", "")
MINIO_SECRET = os.environ.get("MINIO_SECRET_KEY") or os.environ.get("MINIO_ROOT_PASSWORD", "")
MINIO_TLS = os.environ.get("MINIO_TLS", "0") not in ("0", "", "false", "False")

SEAU_PROGRAMMES = os.environ.get("SERVICE_SEAU_PROGRAMMES", "programmes")
SEAU_CORPUS = os.environ.get("SERVICE_SEAU_CORPUS", "corpus")
SEAU_SORTIES = os.environ.get("SERVICE_SEAU_SORTIES", "sorties")

#: Arborescence dans `sorties/`. Une seule définition, pour que le service et
#: l'humain qui ouvre la console MinIO parlent des mêmes chemins.
PREFIXE_REFERENTIELS = "referentiels"
PREFIXE_CORPUS = "corpus"
PREFIXE_ETIQUETTES = "etiquettes"
PREFIXE_CONFRONTATIONS = "confrontations"
PREFIXE_MESURES = "mesures"

DUREE_MAX = int(os.environ.get("SERVICE_DUREE_MAX", 26 * 3600))
SORTIE_MAX = int(os.environ.get("SERVICE_SORTIE_MAX", 20_000))


class CheminRefuse(ValueError):
    """Chemin hors du volume, ou clé d'objet mal formée."""


#: Une clé d'objet ne doit pas pouvoir remonter l'arborescence une fois
#: transformée en chemin local : `../../etc/passwd` déposé comme nom d'objet
#: écrirait hors de l'espace de travail au téléchargement.
def valider_cle(cle: str) -> str:
    if not cle or cle != cle.strip() or cle.startswith("/"):
        raise CheminRefuse(f"clé d'objet mal formée : {cle!r}")
    morceaux = [m for m in cle.split("/") if m]
    if any(m in ("..", ".") for m in morceaux) or "\\" in cle:
        raise CheminRefuse(f"clé d'objet refusée (remontée d'arborescence) : {cle!r}")
    return "/".join(morceaux)


#: Empreinte de référentiel : 16 caractères hexadécimaux, telle que la rend
#: `/construire`. Tout le reste est refusé — une empreinte libre permettrait
#: d'écrire n'importe où sous `sorties/referentiels/`.
def valider_empreinte(empreinte: str) -> str:
    normalisee = (empreinte or "").strip().lower()
    if len(normalisee) != 16 or any(c not in "0123456789abcdef" for c in normalisee):
        raise CheminRefuse(
            f"empreinte de référentiel invalide : {empreinte!r} "
            "(attendu : 16 caractères hexadécimaux)"
        )
    return normalisee


def environnement_etages() -> dict[str, str]:
    """L'environnement passé aux sous-processus.

    `ANTHROPIC_API_KEY` est reprise de l'environnement du SERVICE et jamais du
    corps de la requête : une clé qui transite par HTTP finit dans les journaux
    de l'orchestrateur.
    """
    env = dict(os.environ)
    env["ETAGE0_RACINE"] = str(RACINE_CODE)
    # `ETAGE0_SORTIE` et `ETAGE0_JOURNAL` sont posés PAR TÂCHE, selon le
    # référentiel et la signature : les laisser fuir depuis l'environnement du
    # service ferait écrire deux campagnes dans le même journal.
    env.pop("ETAGE0_SORTIE", None)
    env.pop("ETAGE0_JOURNAL", None)
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
