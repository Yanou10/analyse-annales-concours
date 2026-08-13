"""API HTTP de la chaîne. n8n orchestre, Python calcule.

Chaque appel lance une commande en tâche de fond et rend un identifiant tout de
suite : un étiquetage dure des minutes, une requête synchrone expirerait chez
l'orchestrateur avant la fin — et un client qui réessaie relancerait des appels
payants.

Le service ne fait AUCUN calcul métier. Il valide, il lance, il rend l'état.
Les commandes appelées sont exactement celles de la ligne de commande, options
comprises, pour qu'une passe HTTP et une passe manuelle soient la même passe.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import VERSION, config
from .config import CheminRefuse, resoudre, resoudre_plusieurs
from .journalisation import installer, tracer
from .taches import Executeur, Registre

journal = installer(os.environ.get("SERVICE_NIVEAU_LOG", "INFO"))

@asynccontextmanager
async def cycle_de_vie(_):
    au_demarrage()
    yield


application = FastAPI(
    title="Chaîne annales — service",
    version=VERSION,
    description="Expose etage0/1/3/4 en tâches de fond. Aucune logique métier ici.",
    lifespan=cycle_de_vie,
)

registre = Registre(config.TACHES)
executeur = Executeur(registre)

#: Sous-commandes de l'étage 4, par nombre de passes attendues. Vérifiées
#: contre `etage4 --help` : y ajouter un nom qui n'existe pas produirait une
#: tâche qui échoue à l'exécution plutôt qu'un refus immédiat.
MESURES_UNE_PASSE = (
    "distribution", "fichier", "section", "filiere", "annee", "genre", "langage",
    "exercice", "zero", "top", "croisement", "tout", "dashboard",
)
MESURES_DEUX_PASSES = ("dispersion", "comparer")


def commande(paquet: str, *arguments: str) -> list[str]:
    """`python -m etageN.cli …` plutôt que le script de console.

    Le script `etage1` n'existe que si le paquet est installé ET que le
    répertoire des scripts est dans le PATH du processus — deux conditions que
    le service ne contrôle pas. `-m` avec `sys.executable` ne dépend ni de
    l'une ni de l'autre, et garantit que les étages tournent sous le MÊME
    interpréteur que le service. Le `Dockerfile`, lui, vérifie les scripts de
    console au build : c'est le packaging qu'il contrôle, pas l'exécution.
    """
    return [sys.executable, "-m", f"{paquet}.cli", *arguments]


# --------------------------------------------------------------------------- #
# corps de requête
# --------------------------------------------------------------------------- #
class Extraction(BaseModel):
    fichiers: list[str] = Field(..., description="chemins .md sous /travail")
    sortie: str = Field("corpus", description="dossier de sortie sous /travail")
    filtrer_filiere: bool = False


class Confrontation(BaseModel):
    corpus: list[str]
    sondes: str | None = None
    sonde: str | None = None
    minimum: int | None = None
    extraits: int | None = None
    sortie: str | None = None


class Etiquetage(BaseModel):
    corpus: list[str]
    sortie: str
    batch: bool = False
    tranche_lot: int | None = None
    attente_lot: int | None = None
    limite: int | None = None
    exercice: str | None = None
    graine: str | None = None
    dry_run: bool = False
    modele: str | None = None
    protocole: str | None = None


class Mesure(BaseModel):
    sous_commande: str
    passes: list[str]
    sortie: str | None = None
    titre: str | None = None
    n: int | None = None
    champ: str | None = None
    sections_vides: bool = False
    sans_entete: bool = False
    referentiel: str | None = None


# --------------------------------------------------------------------------- #
# santé
# --------------------------------------------------------------------------- #
def _empreinte_dossier(dossier: Path, motif: str) -> str | None:
    if not dossier.is_dir():
        return None
    condensat = hashlib.sha256()
    for fichier in sorted(dossier.glob(motif)):
        condensat.update(fichier.read_bytes())
    return condensat.hexdigest()[:16]


def _signature_protocole() -> dict[str, Any]:
    """La signature que l'étage 3 calculera, recalculée à l'identique.

    Elle est reprise du code de l'étage, jamais réimplémentée : une signature
    approchée serait pire que pas de signature, puisqu'elle laisserait croire
    que deux passes sont comparables.
    """
    try:
        from etage0.config import Config
        from etage0.journal import empreinte
        from etage3 import contrats
        from etage3.cli import SECTIONS_OPERANTES, charger_protocole

        configuration = Config.depuis_env()
        profil = configuration.profil
        outil = contrats.schema_sections([s["id"] for s in profil.sections_cibles])
        protocole = charger_protocole(config.RACINE_CODE / "config" / "mesure.yaml")
        signature = empreinte(
            "etage3", profil.version_prompt, configuration.modele, "",
            json.dumps(outil, sort_keys=True, ensure_ascii=False),
            json.dumps({s: protocole.get(s) for s in SECTIONS_OPERANTES},
                       sort_keys=True, ensure_ascii=False),
            contrats.CONSIGNES,
        )
        return {
            "signature": signature,
            "version": protocole.get("version_protocole"),
            "date": protocole.get("date"),
            "modele": (protocole.get("modele") or {}).get("id"),
            "reflexion": (protocole.get("modele") or {}).get("reflexion"),
        }
    except Exception as err:  # noqa: BLE001 — /sante ne doit jamais tomber
        return {"signature": None, "indisponible": f"{type(err).__name__}: {err}"}


@application.get("/sante")
def sante() -> dict[str, Any]:
    sections = config.REFERENTIEL
    notions = 0
    if sections.is_dir():
        for fichier in sections.glob("*.yaml"):
            donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
            notions += len(donnees.get("notions") or [])
    # Un référentiel absent n'est pas « 0 notion » : c'est un volume non
    # approvisionné, et le service ne peut rien étiqueter. Le dire franchement
    # plutôt que de rendre un zéro qui se lit comme une mesure.
    approvisionne = sections.is_dir() and notions > 0
    return {
        "etat": "ok" if approvisionne else "referentiel_absent",
        "version_service": VERSION,
        # Présence seulement : la valeur de la clé ne sort jamais du processus.
        "cle_anthropic_presente": config.etat_environnement().cle_presente,
        "referentiel": {
            "chemin": str(sections),
            "approvisionne": approvisionne,
            "notions": notions,
            "empreinte": _empreinte_dossier(sections, "*.yaml"),
            **({} if approvisionne else {
                "remede": f"déposer le référentiel dans {sections} "
                          "(volume /travail), il ne voyage pas dans l'image",
            }),
        },
        "protocole": _signature_protocole(),
        "travail": {
            "chemin": str(config.TRAVAIL),
            "accessible_en_ecriture": os.access(config.TRAVAIL, os.W_OK),
        },
        "taches": {
            "par_etat": registre.compter(),
            "lourde_en_cours": executeur.lourde_en_cours,
            "lourdes_en_attente": executeur.attente_lourde,
        },
    }


# --------------------------------------------------------------------------- #
# lancement des commandes
# --------------------------------------------------------------------------- #
def _lancer(appel: list[str], endpoint: str, sous_commande: str) -> dict[str, Any]:
    """Met en file et rend l'identifiant. Ne bloque jamais."""
    lourde = sous_commande in config.COMMANDES_LOURDES
    tache = registre.creer(appel, endpoint, lourde)
    executeur.soumettre(tache)
    return {
        "tache": tache.id,
        "etat": tache.etat,
        "lourde": lourde,
        "commande": appel,
        "suivi": f"/taches/{tache.id}",
    }


def _refuser(err: CheminRefuse) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@application.post("/extraire")
def extraire(corps: Extraction) -> dict[str, Any]:
    """`etage1 extraire <fichiers…> --sortie <dossier>`"""
    try:
        fichiers = resoudre_plusieurs(corps.fichiers)
        sortie = resoudre(corps.sortie, doit_exister=False)
    except CheminRefuse as err:
        raise _refuser(err) from None
    sortie.mkdir(parents=True, exist_ok=True)
    appel = commande("etage1", "extraire", *map(str, fichiers), "--sortie", str(sortie))
    if corps.filtrer_filiere:
        appel.append("--filtrer-filiere")
    return _lancer(appel, "extraire", "extraire")


@application.post("/confronter")
def confronter(corps: Confrontation) -> dict[str, Any]:
    """`etage0 confronter <corpus…>` — déterministe, aucun appel de modèle."""
    try:
        corpus = resoudre_plusieurs(corps.corpus)
        sondes = resoudre(corps.sondes) if corps.sondes else None
        sortie = resoudre(corps.sortie, doit_exister=False) if corps.sortie else None
    except CheminRefuse as err:
        raise _refuser(err) from None
    appel = commande("etage0", "confronter", *map(str, corpus))
    # Le défaut de l'étage 0 (`referentiel/sondes.yaml`, relatif à /app) ne
    # vaut plus : le référentiel est dans le volume. On passe donc toujours le
    # chemin, explicitement.
    appel += ["--sondes", str(sondes or config.SONDES)]
    if corps.sonde:
        appel += ["--sonde", corps.sonde]
    if corps.minimum is not None:
        appel += ["--minimum", str(corps.minimum)]
    if corps.extraits is not None:
        appel += ["--extraits", str(corps.extraits)]
    if sortie:
        sortie.parent.mkdir(parents=True, exist_ok=True)
        # `--sortie` de `confronter` a pour dest `sortie_confrontation` : le
        # drapeau reste `--sortie`, c'est le nom interne qui diffère.
        appel += ["--sortie", str(sortie)]
    return _lancer(appel, "confronter", "confronter")


@application.post("/etiqueter")
def etiqueter(corps: Etiquetage) -> dict[str, Any]:
    """`etage3 [--modele X] etiqueter <corpus…> --sortie <dossier> [--batch]`

    `--modele` est une option GLOBALE de l'étage 3 : elle se place avant la
    sous-commande, sans quoi l'analyse des arguments échoue.
    """
    if not corps.dry_run and not config.etat_environnement().cle_presente:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY absente de l'environnement du service : "
                   "l'étiquetage échouerait après avoir été mis en file.",
        )
    try:
        corpus = resoudre_plusieurs(corps.corpus)
        sortie = resoudre(corps.sortie, doit_exister=False)
        protocole = resoudre(corps.protocole) if corps.protocole else None
    except CheminRefuse as err:
        raise _refuser(err) from None
    sortie.mkdir(parents=True, exist_ok=True)

    globales = ["--modele", corps.modele] if corps.modele else []
    appel = commande("etage3", *globales, "etiqueter", *map(str, corpus),
                     "--sortie", str(sortie))
    if corps.batch:
        appel.append("--batch")
    if corps.tranche_lot is not None:
        appel += ["--tranche-lot", str(corps.tranche_lot)]
    if corps.attente_lot is not None:
        appel += ["--attente-lot", str(corps.attente_lot)]
    if corps.limite is not None:
        appel += ["--limite", str(corps.limite)]
    if corps.exercice:
        appel += ["--exercice", corps.exercice]
    if corps.graine:
        appel += ["--graine", corps.graine]
    if corps.dry_run:
        appel.append("--dry-run")
    if protocole:
        appel += ["--protocole", str(protocole)]
    return _lancer(appel, "etiqueter", "etiqueter")


@application.post("/mesurer")
def mesurer(corps: Mesure) -> dict[str, Any]:
    """`etage4 [--referentiel X] [--sans-entete] <sous-commande> <passe…>`

    `--referentiel`, `--protocole` et `--sans-entete` sont GLOBAUX : ils se
    placent avant la sous-commande.
    """
    sous = corps.sous_commande
    if sous in MESURES_DEUX_PASSES:
        attendu = 2
    elif sous in MESURES_UNE_PASSE:
        attendu = None
    else:
        raise HTTPException(
            status_code=400,
            detail=f"sous-commande inconnue : {sous!r}. Disponibles : "
                   + ", ".join(sorted(MESURES_UNE_PASSE + MESURES_DEUX_PASSES)),
        )
    if attendu == 2 and len(corps.passes) != 2:
        raise HTTPException(status_code=400, detail=f"{sous} attend exactement deux passes")

    try:
        passes = resoudre_plusieurs(corps.passes)
        sortie = resoudre(corps.sortie, doit_exister=False) if corps.sortie else None
        referentiel = resoudre(corps.referentiel) if corps.referentiel else None
    except CheminRefuse as err:
        raise _refuser(err) from None

    # Même raison qu'aux sondes : le défaut de l'étage 4 est relatif à /app,
    # où le référentiel n'est plus. Toujours explicite.
    globales: list[str] = ["--referentiel", str(referentiel or config.REFERENTIEL)]
    if corps.sans_entete:
        globales.append("--sans-entete")
    appel = commande("etage4", *globales, sous, *map(str, passes))
    if sous == "dashboard":
        if sortie:
            sortie.parent.mkdir(parents=True, exist_ok=True)
            appel += ["--sortie", str(sortie)]
        if corps.titre:
            appel += ["--titre", corps.titre]
    else:
        if corps.n is not None and sous in ("top", "distribution", "croisement", "tout"):
            appel += ["--n", str(corps.n)]
        if corps.champ and sous in ("croisement", "tout"):
            appel += ["--champ", corps.champ]
        if corps.sections_vides and sous in ("zero", "tout"):
            appel.append("--sections-vides")
    return _lancer(appel, "mesurer", sous)


# --------------------------------------------------------------------------- #
# suivi
# --------------------------------------------------------------------------- #
@application.get("/taches/{identifiant}")
def tache(identifiant: str) -> dict[str, Any]:
    trouvee = registre.lire(identifiant)
    if trouvee is None:
        raise HTTPException(status_code=404, detail=f"tâche inconnue : {identifiant}")
    return trouvee.en_dict()


@application.get("/taches")
def taches(
    limite: int = 50,
    etat: Literal["en_attente", "en_cours", "fini", "echec", "interrompu"] | None = None,
) -> dict[str, Any]:
    liste = registre.lister(limite=min(limite, 500), etat=etat)
    return {
        "total": len(liste),
        "par_etat": registre.compter(),
        "taches": [
            {
                "id": t.id, "endpoint": t.endpoint, "etat": t.etat, "lourde": t.lourde,
                "cree": t.cree, "duree_s": round(t.duree, 2) if t.duree else None,
                "code_retour": t.code_retour,
            }
            for t in liste
        ],
    }


def au_demarrage() -> None:
    config.TRAVAIL.mkdir(parents=True, exist_ok=True)
    config.JOURNAL_ETAGES.parent.mkdir(parents=True, exist_ok=True)
    tracer(
        "service démarré",
        version=VERSION,
        travail=str(config.TRAVAIL),
        code=str(config.RACINE_CODE),
        cle_presente=config.etat_environnement().cle_presente,
        taches_connues=sum(registre.compter().values()),
    )
