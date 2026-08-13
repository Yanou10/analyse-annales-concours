"""API HTTP de la chaîne. n8n orchestre, Python calcule, MinIO porte la matière.

Le service ne suppose plus rien de présent : chaque endpoint prend des CLÉS
D'OBJET, descend ce qu'il faut dans un espace jetable, exécute la commande de
l'étage concerné, remonte les sorties et détruit l'espace.

Le référentiel n'est pas un préalable. C'est une donnée d'entrée produite par
`POST /construire`, identifiée par son empreinte, et plusieurs référentiels
coexistent. Conséquence directe, et c'est le point délicat : **l'empreinte du
référentiel entre dans la signature de protocole**, via `--graine`. Sans elle,
deux passes menées sur des référentiels différents partageraient leurs clés de
journal et se réutiliseraient l'une l'autre — la signature de l'étage 3 ne
couvre pas le contenu des notions.

Aucun calcul métier ici. Les commandes appelées sont exactement celles de la
ligne de commande, options comprises.
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
from .config import CheminRefuse, valider_cle, valider_empreinte
from .journalisation import installer, tracer
from .stockage import stockage
from .taches import Execution, Executeur, Plan, Registre

journal = installer(os.environ.get("SERVICE_NIVEAU_LOG", "INFO"))


@asynccontextmanager
async def cycle_de_vie(_):
    au_demarrage()
    yield


application = FastAPI(
    title="Chaîne annales — service",
    version=VERSION,
    description="Expose etage0/1/3/4 en tâches de fond, entrées et sorties dans MinIO.",
    lifespan=cycle_de_vie,
)

registre = Registre(config.TACHES)
executeur = Executeur(registre)

MESURES_UNE_PASSE = (
    "distribution", "fichier", "section", "filiere", "annee", "genre", "langage",
    "exercice", "zero", "top", "croisement", "tout", "dashboard",
)
MESURES_DEUX_PASSES = ("dispersion", "comparer")


def commande(paquet: str, *arguments: str) -> list[str]:
    """`python -m etageN.cli …` plutôt que le script de console : ne dépend ni
    du PATH ni du venv actif, et garantit le même interpréteur."""
    return [sys.executable, "-m", f"{paquet}.cli", *arguments]


def commande_import(*arguments: str) -> list[str]:
    """`annales-import`, joint par son module pour la même raison."""
    return [sys.executable, "-m", "service.base", *arguments]


def _empreinte_dossier(dossier: Path, motif: str = "*.yaml") -> str | None:
    if not dossier.is_dir():
        return None
    condensat = hashlib.sha256()
    for fichier in sorted(dossier.glob(motif)):
        condensat.update(fichier.read_bytes())
    return condensat.hexdigest()[:16]


def _empreinte_fichier(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# corps de requête
# --------------------------------------------------------------------------- #
class Construction(BaseModel):
    programme: str = Field(..., description="clé dans le seau `programmes`")
    dry_run: bool = False
    rejouer: bool = False
    strict: bool = False
    modele: str | None = None


class Extraction(BaseModel):
    sujets: list[str] = Field(..., description="clés dans le seau `corpus`")
    lot: str = Field(..., description="nom du lot sous sorties/corpus/<lot>/")
    filtrer_filiere: bool = False


class Confrontation(BaseModel):
    lot: str
    referentiel: str = Field(..., description="empreinte du référentiel")
    sonde: str | None = None
    minimum: int | None = None
    extraits: int | None = None


class Etiquetage(BaseModel):
    lot: str
    referentiel: str
    passe: str = Field(..., description="nom de la passe sous sorties/etiquettes/<passe>/")
    batch: bool = False
    tranche_lot: int | None = None
    attente_lot: int | None = None
    limite: int | None = None
    exercice: str | None = None
    dry_run: bool = False
    modele: str | None = None


class Import(BaseModel):
    # `url` est volontairement ABSENT : `DATABASE_URL` vient de l'environnement
    # du service et jamais du corps de la requête. Une URL de connexion porte
    # un mot de passe, et un corps HTTP finit dans les journaux de
    # l'orchestrateur — même raison que pour la clé Anthropic.
    passe: str | None = Field(None, description="passe sous sorties/etiquettes/")
    referentiel: str | None = Field(None, description="empreinte du référentiel")
    lot: str | None = Field(None, description="défaut : le lot inscrit dans passe.json")
    verifier_seulement: bool = False
    creer_schema: bool = False


class Mesure(BaseModel):
    sous_commande: str
    passes: list[str] = Field(..., description="noms de passes sous sorties/etiquettes/")
    referentiel: str
    titre: str | None = None
    n: int | None = None
    champ: str | None = None
    sections_vides: bool = False
    sans_entete: bool = False


# --------------------------------------------------------------------------- #
# protocole
# --------------------------------------------------------------------------- #
def signature_protocole(graine: str = "") -> dict[str, Any]:
    """La signature que l'étage 3 calculera, recalculée à l'identique.

    Reprise du code de l'étage, jamais réimplémentée : une signature approchée
    serait pire que pas de signature, puisqu'elle laisserait croire que deux
    passes sont comparables.
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
        return {
            "signature": empreinte(
                "etage3", profil.version_prompt, configuration.modele, graine,
                json.dumps(outil, sort_keys=True, ensure_ascii=False),
                json.dumps({s: protocole.get(s) for s in SECTIONS_OPERANTES},
                           sort_keys=True, ensure_ascii=False),
                contrats.CONSIGNES,
            ),
            "graine": graine or None,
            "version": protocole.get("version_protocole"),
            "date": protocole.get("date"),
            "modele": (protocole.get("modele") or {}).get("id"),
            "reflexion": (protocole.get("modele") or {}).get("reflexion"),
            "protocole": protocole,
        }
    except Exception as err:  # noqa: BLE001 — /sante ne doit jamais tomber
        return {"signature": None, "indisponible": f"{type(err).__name__}: {err}"}


def _prefixe_referentiel(empreinte: str) -> str:
    return f"{config.PREFIXE_REFERENTIELS}/{empreinte}"


def _referentiels_disponibles() -> list[str]:
    try:
        prefixe = f"{config.PREFIXE_REFERENTIELS}/"
        vues = {
            objet.cle[len(prefixe):].split("/", 1)[0]
            for objet in stockage.lister(config.SEAU_SORTIES, prefixe)
            if "/" in objet.cle[len(prefixe):]
        }
        return sorted(v for v in vues if v)
    except Exception:  # noqa: BLE001
        return []


def _exiger_referentiel(empreinte: str) -> str:
    """409 plutôt qu'un échec à mi-parcours.

    `referentiel_absent` est l'état d'une instance neuve : légitime pour le
    service, rédhibitoire pour les endpoints qui en dépendent. Le dire avant de
    mettre la tâche en file évite de faire attendre un travail condamné.
    """
    try:
        empreinte = valider_empreinte(empreinte)
    except CheminRefuse as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    sections = f"{_prefixe_referentiel(empreinte)}/sections/"
    if not any(stockage.lister(config.SEAU_SORTIES, sections)):
        disponibles = _referentiels_disponibles()
        raise HTTPException(
            status_code=409,
            detail={
                "erreur": "referentiel_absent",
                "message": f"aucun référentiel {empreinte} dans "
                           f"{config.SEAU_SORTIES}/{sections}",
                "disponibles": disponibles,
                "remede": "POST /construire sur un programme du seau `programmes`"
                          if not disponibles else
                          "reprendre une empreinte de `disponibles`",
            },
        )
    return empreinte


def _descendre_referentiel(empreinte: str, espace: Path) -> Path:
    cible = espace / "referentiel"
    stockage.descendre_prefixe(
        config.SEAU_SORTIES, f"{_prefixe_referentiel(empreinte)}/", cible)
    return cible


# --------------------------------------------------------------------------- #
# santé
# --------------------------------------------------------------------------- #
@application.get("/sante")
def sante() -> dict[str, Any]:
    referentiels = _referentiels_disponibles()
    return {
        # Une instance neuve n'a pas de référentiel : c'est un état légitime,
        # pas une panne. Le service démarre, répond, et le signale.
        "etat": "ok" if referentiels else "referentiel_absent",
        "version_service": VERSION,
        # Présence seulement : la valeur de la clé ne sort jamais du processus.
        "cle_anthropic_presente": config.etat_environnement().cle_presente,
        "referentiels": {
            "disponibles": referentiels,
            "emplacement": f"{config.SEAU_SORTIES}/{config.PREFIXE_REFERENTIELS}/",
            **({} if referentiels else {
                "remede": "POST /construire sur un programme déposé dans le seau "
                          f"`{config.SEAU_PROGRAMMES}`",
            }),
        },
        "stockage": stockage.etat(),
        "protocole": {k: v for k, v in signature_protocole().items() if k != "protocole"},
        "travail": {
            "chemin": str(config.TRAVAIL),
            "accessible_en_ecriture": os.access(config.TRAVAIL, os.W_OK),
            "journaux": sorted(p.name for p in config.JOURNAUX.glob("*.jsonl")),
        },
        "taches": {
            "par_etat": registre.compter(),
            "lourde_en_cours": executeur.lourde_en_cours,
            "lourdes_en_attente": executeur.attente_lourde,
        },
    }


@application.get("/referentiels")
def referentiels() -> dict[str, Any]:
    """Quels référentiels existent, et contre quoi ils ont été construits."""
    sortie = []
    for empreinte in _referentiels_disponibles():
        origine: dict[str, Any] = {}
        try:
            objets = list(stockage.lister(
                config.SEAU_SORTIES, f"{_prefixe_referentiel(empreinte)}/"))
            cle = f"{_prefixe_referentiel(empreinte)}/origine.json"
            if any(o.cle == cle for o in objets):
                reponse = stockage.client.get_object(config.SEAU_SORTIES, cle)
                origine = json.loads(reponse.read().decode("utf-8"))
                reponse.close()
                reponse.release_conn()
            notions = sum(1 for o in objets if "/sections/" in o.cle)
        except Exception as err:  # noqa: BLE001
            origine, notions = {"erreur": str(err)}, 0
        sortie.append({
            "empreinte": empreinte,
            "fichiers_de_sections": notions,
            "signature_etiquetage": signature_protocole(empreinte).get("signature"),
            "origine": origine,
        })
    return {"total": len(sortie), "referentiels": sortie}


# --------------------------------------------------------------------------- #
# endpoints de travail
# --------------------------------------------------------------------------- #
@application.get("/objets")
def objets(seau: str, prefixe: str = "", limite: int = 500) -> dict[str, Any]:
    """Liste un seau, en lecture seule.

    Existe pour que l'orchestrateur puisse répondre à « y a-t-il des sujets en
    attente ? » sans détenir d'identifiants MinIO. Lui donner un accès S3
    direct pour un simple comptage ferait voyager un secret de plus, et pour
    lire ce que le service voit déjà.
    """
    connus = {config.SEAU_PROGRAMMES, config.SEAU_CORPUS, config.SEAU_SORTIES}
    if seau not in connus:
        raise HTTPException(
            status_code=400,
            detail=f"seau inconnu : {seau!r}. Connus : {', '.join(sorted(connus))}")
    try:
        prefixe = valider_cle(prefixe) + "/" if prefixe else ""
    except CheminRefuse as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    try:
        trouves = list(stockage.lister(seau, prefixe))
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status_code=503,
                            detail=f"stockage injoignable : {err}") from None
    tronque = len(trouves) > limite
    return {
        "seau": seau,
        "prefixe": prefixe,
        "total": len(trouves),
        "tronque": tronque,
        "objets": [
            {"cle": o.cle, "taille": o.taille, "modifie": o.modifie}
            for o in trouves[:limite]
        ],
    }


@application.post("/construire")
def construire(corps: Construction) -> dict[str, Any]:
    """`etage0 construire` — produit un référentiel depuis un programme officiel.

    C'est la commande qui rend le service utilisable sur n'importe quel
    programme : rien n'est figé dans l'image.
    """
    if not corps.dry_run and not config.etat_environnement().cle_presente:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY absente : la construction échouerait après "
                   "avoir été mise en file.",
        )
    try:
        cle = valider_cle(corps.programme)
    except CheminRefuse as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    if not stockage.existe(config.SEAU_PROGRAMMES, cle):
        raise HTTPException(
            status_code=404,
            detail=f"programme introuvable : {config.SEAU_PROGRAMMES}/{cle}")

    def preparer(espace: Path) -> Execution:
        programme = stockage.descendre(
            config.SEAU_PROGRAMMES, cle, espace / "programme.md")
        sortie = espace / "referentiel"
        sortie.mkdir(parents=True, exist_ok=True)
        appel = commande("etage0", "--sortie", str(sortie))
        if corps.modele:
            appel += ["--modele", corps.modele]
        appel.append("construire")
        if corps.dry_run:
            appel.append("--dry-run")
        if corps.rejouer:
            appel.append("--rejouer")
        if corps.strict:
            appel.append("--strict")
        return Execution(
            commande=appel,
            env={
                "ETAGE0_PROGRAMME": str(programme),
                "ETAGE0_SORTIE": str(sortie),
                # Journal segmenté par PROGRAMME : deux programmes n'ont rien à
                # se réutiliser, et un même programme rejoué doit reprendre.
                "ETAGE0_JOURNAL": str(
                    config.journal_de(f"construction-{_empreinte_fichier(programme)}")),
            },
        )

    def reverser(espace: Path) -> dict[str, Any]:
        produit = espace / "referentiel"
        empreinte = _empreinte_dossier(produit / "sections")
        if not empreinte:
            raise RuntimeError("aucune section produite : rien à ranger")
        prefixe = _prefixe_referentiel(empreinte)
        montes = stockage.monter_dossier(produit, config.SEAU_SORTIES, prefixe)
        notions = 0
        for fichier in sorted((produit / "sections").glob("*.yaml")):
            donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
            notions += len(donnees.get("notions") or [])
        origine = {
            "programme": f"{config.SEAU_PROGRAMMES}/{cle}",
            "empreinte_programme": _empreinte_fichier(espace / "programme.md"),
            "empreinte_referentiel": empreinte,
            "notions": notions,
            "modele": corps.modele or os.environ.get("ETAGE0_MODELE"),
            "signature_etiquetage": signature_protocole(empreinte).get("signature"),
        }
        stockage.monter_json(origine, config.SEAU_SORTIES, f"{prefixe}/origine.json")
        return {
            "empreinte": empreinte,
            "notions": notions,
            "objets": len(montes) + 1,
            "prefixe": f"{config.SEAU_SORTIES}/{prefixe}/",
            **origine,
        }

    tache = executeur.soumettre(Plan(
        endpoint="construire", lourde=True, preparer=preparer, reverser=reverser,
        contexte={"programme": cle},
    ))
    return {"tache": tache.id, "etat": tache.etat, "lourde": True,
            "suivi": f"/taches/{tache.id}"}


@application.post("/extraire")
def extraire(corps: Extraction) -> dict[str, Any]:
    """`etage1 extraire` — déterministe, aucun appel de modèle."""
    try:
        cles = [valider_cle(c) for c in corps.sujets]
        lot = valider_cle(corps.lot)
    except CheminRefuse as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    if not cles:
        raise HTTPException(status_code=400, detail="aucun sujet fourni")
    manquants = [c for c in cles if not stockage.existe(config.SEAU_CORPUS, c)]
    if manquants:
        raise HTTPException(
            status_code=404,
            detail=f"introuvables dans {config.SEAU_CORPUS} : {', '.join(manquants)}")

    def preparer(espace: Path) -> Execution:
        sujets = espace / "sujets"
        for cle in cles:
            stockage.descendre(config.SEAU_CORPUS, cle, sujets / Path(cle).name)
        sortie = espace / "corpus"
        sortie.mkdir(parents=True, exist_ok=True)
        appel = commande(
            "etage1", "extraire",
            *[str(p) for p in sorted(sujets.glob("*"))],
            "--sortie", str(sortie),
        )
        if corps.filtrer_filiere:
            appel.append("--filtrer-filiere")
        return Execution(commande=appel)

    def reverser(espace: Path) -> dict[str, Any]:
        prefixe = f"{config.PREFIXE_CORPUS}/{lot}"
        montes = stockage.monter_dossier(espace / "corpus", config.SEAU_SORTIES, prefixe)
        # `documents` compte les JSON extraits ; `objets` compte tout ce qui est
        # remonté, `journal.txt` de l'étage 1 compris. Confondre les deux ferait
        # annoncer un document de plus qu'il n'y en a.
        return {
            "lot": lot,
            "documents": sum(1 for c in montes if c.endswith(".json")),
            "objets": len(montes),
            "prefixe": f"{config.SEAU_SORTIES}/{prefixe}/",
            "cles": montes,
        }

    tache = executeur.soumettre(Plan(
        endpoint="extraire", lourde=False, preparer=preparer, reverser=reverser,
        contexte={"lot": lot, "sujets": len(cles)},
    ))
    return {"tache": tache.id, "etat": tache.etat, "lourde": False,
            "suivi": f"/taches/{tache.id}"}


@application.post("/confronter")
def confronter(corps: Confrontation) -> dict[str, Any]:
    """`etage0 confronter` — déterministe. Exige un référentiel : ses sondes s'y
    réfèrent notion par notion."""
    empreinte = _exiger_referentiel(corps.referentiel)
    try:
        lot = valider_cle(corps.lot)
    except CheminRefuse as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    sondes = f"{_prefixe_referentiel(empreinte)}/sondes.yaml"
    if not stockage.existe(config.SEAU_SORTIES, sondes):
        raise HTTPException(
            status_code=409,
            detail={
                "erreur": "sondes_absentes",
                "message": f"aucun fichier de sondes : {config.SEAU_SORTIES}/{sondes}",
                "remede": "déposer sondes.yaml sous le préfixe du référentiel — "
                          "les sondes sont écrites à la main et se réfèrent aux "
                          "notions de CE référentiel",
            },
        )

    def preparer(espace: Path) -> Execution:
        referentiel = _descendre_referentiel(empreinte, espace)
        corpus = espace / "corpus"
        stockage.descendre_prefixe(
            config.SEAU_SORTIES, f"{config.PREFIXE_CORPUS}/{lot}/", corpus)
        appel = commande(
            "etage0", "confronter",
            *[str(p) for p in sorted(corpus.glob("*.json"))],
            "--sondes", str(referentiel / "sondes.yaml"),
            "--sortie", str(espace / "confrontation.json"),
        )
        if corps.sonde:
            appel += ["--sonde", corps.sonde]
        if corps.minimum is not None:
            appel += ["--minimum", str(corps.minimum)]
        if corps.extraits is not None:
            appel += ["--extraits", str(corps.extraits)]
        return Execution(commande=appel, env={"ETAGE0_SORTIE": str(referentiel)})

    def reverser(espace: Path) -> dict[str, Any]:
        cle = f"{config.PREFIXE_CONFRONTATIONS}/{lot}__{empreinte}.json"
        stockage.monter(espace / "confrontation.json", config.SEAU_SORTIES, cle)
        return {"objet": f"{config.SEAU_SORTIES}/{cle}",
                "lot": lot, "referentiel": empreinte}

    tache = executeur.soumettre(Plan(
        endpoint="confronter", lourde=False, preparer=preparer, reverser=reverser,
        contexte={"lot": lot, "referentiel": empreinte},
    ))
    return {"tache": tache.id, "etat": tache.etat, "lourde": False,
            "suivi": f"/taches/{tache.id}"}


@application.post("/etiqueter")
def etiqueter(corps: Etiquetage) -> dict[str, Any]:
    empreinte = _exiger_referentiel(corps.referentiel)
    if not corps.dry_run and not config.etat_environnement().cle_presente:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY absente : l'étiquetage échouerait après "
                   "avoir été mis en file.",
        )
    try:
        lot, passe = valider_cle(corps.lot), valider_cle(corps.passe)
    except CheminRefuse as err:
        raise HTTPException(status_code=400, detail=str(err)) from None

    protocole = signature_protocole(empreinte)
    signature = protocole.get("signature")

    def preparer(espace: Path) -> Execution:
        referentiel = _descendre_referentiel(empreinte, espace)
        corpus = espace / "corpus"
        stockage.descendre_prefixe(
            config.SEAU_SORTIES, f"{config.PREFIXE_CORPUS}/{lot}/", corpus)
        sortie = espace / "passe"
        sortie.mkdir(parents=True, exist_ok=True)

        globales = ["--modele", corps.modele] if corps.modele else []
        appel = commande(
            "etage3", *globales, "etiqueter",
            *[str(p) for p in sorted(corpus.glob("*.json"))],
            "--sortie", str(sortie),
            # L'empreinte du référentiel passe par la graine : c'est le SEUL
            # levier qui entre dans la signature de l'étage 3 sans le modifier.
            # Sans elle, deux référentiels partageraient leurs clés de journal.
            "--graine", empreinte,
        )
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
        if corps.dry_run:
            appel.append("--dry-run")
        return Execution(
            commande=appel,
            env={
                "ETAGE0_SORTIE": str(referentiel),
                # Journal segmenté par SIGNATURE : une campagne sur un autre
                # référentiel n'a rien à réutiliser de celle-ci.
                "ETAGE0_JOURNAL": str(config.journal_de(signature or "sans-signature")),
            },
        )

    def reverser(espace: Path) -> dict[str, Any]:
        prefixe = f"{config.PREFIXE_ETIQUETTES}/{passe}"
        montes = stockage.monter_dossier(espace / "passe", config.SEAU_SORTIES, prefixe)
        # `passe.json` voyage avec les étiquettes : une passe qui ne sait plus
        # contre quel référentiel ni sous quel protocole elle a été mesurée
        # n'est comparable à rien.
        carte = {
            "passe": passe, "lot": lot, "referentiel": empreinte,
            "signature": signature, "graine": empreinte,
            "batch": corps.batch,
            "protocole": protocole.get("protocole"),
        }
        stockage.monter_json(carte, config.SEAU_SORTIES, f"{prefixe}/passe.json")
        return {"passe": passe, "objets": len(montes) + 1, "signature": signature,
                "referentiel": empreinte,
                "prefixe": f"{config.SEAU_SORTIES}/{prefixe}/"}

    tache = executeur.soumettre(Plan(
        endpoint="etiqueter", lourde=True, preparer=preparer, reverser=reverser,
        contexte={"lot": lot, "passe": passe, "referentiel": empreinte,
                  "signature": signature},
    ))
    return {"tache": tache.id, "etat": tache.etat, "lourde": True,
            "signature": signature, "suivi": f"/taches/{tache.id}"}


@application.post("/mesurer")
def mesurer(corps: Mesure) -> dict[str, Any]:
    empreinte = _exiger_referentiel(corps.referentiel)
    sous = corps.sous_commande
    if sous in MESURES_DEUX_PASSES:
        if len(corps.passes) != 2:
            raise HTTPException(status_code=400,
                                detail=f"{sous} attend exactement deux passes")
    elif sous not in MESURES_UNE_PASSE:
        raise HTTPException(
            status_code=400,
            detail=f"sous-commande inconnue : {sous!r}. Disponibles : "
                   + ", ".join(sorted(MESURES_UNE_PASSE + MESURES_DEUX_PASSES)),
        )
    try:
        passes = [valider_cle(p) for p in corps.passes]
    except CheminRefuse as err:
        raise HTTPException(status_code=400, detail=str(err)) from None

    def preparer(espace: Path) -> Execution:
        referentiel = _descendre_referentiel(empreinte, espace)
        locaux = []
        for nom in passes:
            dossier = espace / "passes" / nom
            stockage.descendre_prefixe(
                config.SEAU_SORTIES, f"{config.PREFIXE_ETIQUETTES}/{nom}/", dossier)
            locaux.append(str(dossier))
        globales = ["--referentiel", str(referentiel / "sections")]
        if corps.sans_entete:
            globales.append("--sans-entete")
        appel = commande("etage4", *globales, sous, *locaux)
        if sous == "dashboard":
            appel += ["--sortie", str(espace / "tableau-de-bord.html")]
            if corps.titre:
                appel += ["--titre", corps.titre]
        else:
            if corps.n is not None and sous in ("top", "distribution", "croisement", "tout"):
                appel += ["--n", str(corps.n)]
            if corps.champ and sous in ("croisement", "tout"):
                appel += ["--champ", corps.champ]
            if corps.sections_vides and sous in ("zero", "tout"):
                appel.append("--sections-vides")
        return Execution(commande=appel, env={"ETAGE0_SORTIE": str(referentiel)})

    def reverser(espace: Path) -> dict[str, Any]:
        if sous != "dashboard":
            # Les ventilations sont du texte : elles vivent dans la tâche, pas
            # dans le seau. Y déposer un fichier par appel le remplirait de
            # sorties jetables.
            return {"sortie": "texte", "passes": passes, "referentiel": empreinte}
        cle = f"{config.PREFIXE_MESURES}/{passes[0]}/tableau-de-bord.html"
        stockage.monter(espace / "tableau-de-bord.html", config.SEAU_SORTIES, cle)
        return {"objet": f"{config.SEAU_SORTIES}/{cle}", "passes": passes,
                "referentiel": empreinte}

    tache = executeur.soumettre(Plan(
        endpoint="mesurer", lourde=False, preparer=preparer, reverser=reverser,
        contexte={"sous_commande": sous, "passes": passes, "referentiel": empreinte},
    ))
    return {"tache": tache.id, "etat": tache.etat, "lourde": False,
            "suivi": f"/taches/{tache.id}"}


@application.post("/importer")
def importer(corps: Import) -> dict[str, Any]:
    """`annales-import` — charge une passe dans Postgres. Idempotent.

    L'import lit des fichiers locaux : le service descend d'abord de MinIO la
    passe, son corpus et son référentiel, puis lance la commande. Le protocole
    écrit dans `passes.protocole` vient de `passe.json`, pas de l'image : c'est
    la configuration sous laquelle la passe a RÉELLEMENT été mesurée, et lui
    substituer le `config/mesure.yaml` courant ferait mentir la base au premier
    changement de protocole.
    """
    if not os.environ.get("DATABASE_URL"):
        raise HTTPException(
            status_code=503,
            detail="DATABASE_URL absente de l'environnement du service : "
                   "l'import échouerait après avoir été mis en file.",
        )

    # Contrôle de schéma : aucune donnée à descendre, aucune passe à nommer.
    if corps.verifier_seulement:
        def preparer_controle(espace: Path) -> Execution:
            options = ["--creer-schema"] if corps.creer_schema else []
            return Execution(commande=commande_import(*options, "--verifier-seulement"))

        tache = executeur.soumettre(Plan(
            endpoint="importer", lourde=False,
            preparer=preparer_controle,
            reverser=lambda espace: {"mode": "verification",
                                     "creer_schema": corps.creer_schema},
            contexte={"mode": "verification"},
        ))
        return {"tache": tache.id, "etat": tache.etat, "lourde": False,
                "mode": "verification", "suivi": f"/taches/{tache.id}"}

    if not corps.passe:
        raise HTTPException(status_code=400,
                            detail="`passe` est requis hors mode verifier_seulement")
    empreinte = _exiger_referentiel(corps.referentiel or "")
    try:
        passe = valider_cle(corps.passe)
    except CheminRefuse as err:
        raise HTTPException(status_code=400, detail=str(err)) from None

    carte_cle = f"{config.PREFIXE_ETIQUETTES}/{passe}/passe.json"
    if not stockage.existe(config.SEAU_SORTIES, carte_cle):
        raise HTTPException(
            status_code=409,
            detail={
                "erreur": "passe_incomplete",
                "message": f"aucun {config.SEAU_SORTIES}/{carte_cle}",
                "remede": "POST /etiqueter dépose etiquettes.json ET passe.json ; "
                          "une passe sans sa carte ne sait plus sous quel "
                          "protocole elle a été mesurée",
            },
        )

    def preparer(espace: Path) -> Execution:
        carte_locale = stockage.descendre(
            config.SEAU_SORTIES, carte_cle, espace / "passe.json")
        carte = json.loads(carte_locale.read_text(encoding="utf-8"))
        lot = corps.lot or carte.get("lot")
        if not lot:
            raise RuntimeError("aucun lot : ni dans la requête, ni dans passe.json")

        referentiel = _descendre_referentiel(empreinte, espace)
        corpus = espace / "corpus"
        stockage.descendre_prefixe(
            config.SEAU_SORTIES, f"{config.PREFIXE_CORPUS}/{valider_cle(lot)}/", corpus)
        etiquettes = espace / "passe"
        stockage.descendre_prefixe(
            config.SEAU_SORTIES, f"{config.PREFIXE_ETIQUETTES}/{passe}/", etiquettes)

        # Le protocole de la passe, réécrit en YAML pour `--protocole`.
        protocole = espace / "protocole.yaml"
        protocole.write_text(
            yaml.safe_dump(carte.get("protocole") or {}, allow_unicode=True,
                           sort_keys=False),
            encoding="utf-8",
        )

        appel = commande_import(
            "--corpus", str(corpus),
            "--referentiel", str(referentiel / "sections"),
            "--etiquettes", str(etiquettes),
            "--passe", passe,
            "--protocole", str(protocole),
        )
        if carte.get("signature"):
            appel += ["--signature", str(carte["signature"])]
        if corps.creer_schema:
            appel.append("--creer-schema")
        return Execution(commande=appel)

    def reverser(espace: Path) -> dict[str, Any]:
        return {"passe": passe, "referentiel": empreinte,
                "mode": "import", "idempotent": True}

    tache = executeur.soumettre(Plan(
        endpoint="importer", lourde=False, preparer=preparer, reverser=reverser,
        contexte={"passe": passe, "referentiel": empreinte},
    ))
    return {"tache": tache.id, "etat": tache.etat, "lourde": False,
            "suivi": f"/taches/{tache.id}"}


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
            {"id": t.id, "endpoint": t.endpoint, "etat": t.etat, "lourde": t.lourde,
             "cree": t.cree, "duree_s": round(t.duree, 2) if t.duree else None,
             "code_retour": t.code_retour, "contexte": t.contexte,
             "resultat": t.resultat}
            for t in liste
        ],
    }


def au_demarrage() -> None:
    for dossier in (config.TRAVAIL, config.TACHES, config.ESPACES, config.JOURNAUX):
        dossier.mkdir(parents=True, exist_ok=True)
    # Des espaces laissés par un arrêt brutal : les tâches correspondantes sont
    # déjà reclassées `interrompu`, leur espace n'a plus de raison d'exister.
    orphelins = 0
    for reste in config.ESPACES.iterdir():
        if reste.is_dir():
            import shutil

            shutil.rmtree(reste, ignore_errors=True)
            orphelins += 1
    tracer(
        "service démarré", version=VERSION, travail=str(config.TRAVAIL),
        cle_presente=config.etat_environnement().cle_presente,
        espaces_orphelins_nettoyes=orphelins,
        taches_connues=sum(registre.compter().values()),
    )
