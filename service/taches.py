"""Exécution des commandes en tâche de fond, avec état persistant.

Deux décisions structurent ce fichier :

1. **L'état vit sur disque, pas en mémoire.** Un étiquetage dure des minutes et
   coûte de l'argent ; si le service redémarre pendant, il faut pouvoir dire ce
   qui tournait. Au démarrage, toute tâche restée `en_cours` est reclassée
   `interrompu` — plutôt que de laisser croire qu'elle avance encore.
2. **Une seule tâche lourde à la fois.** L'étiquetage passe par une file à un
   seul exécutant ; les commandes déterministes ont leur propre file. Sans
   cela, deux passes concurrentes sur le même corpus paieraient deux fois les
   mêmes appels — le journal des étages ne dédoublonne qu'après la réponse.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from queue import Queue
from typing import Any

from . import config
from .journalisation import alerter, echouer, tracer

EN_ATTENTE, EN_COURS, FINI, ECHEC, INTERROMPU = (
    "en_attente", "en_cours", "fini", "echec", "interrompu",
)


@dataclass
class Tache:
    id: str
    commande: list[str]
    endpoint: str
    lourde: bool
    etat: str = EN_ATTENTE
    cree: float = field(default_factory=time.time)
    demarre: float | None = None
    fini: float | None = None
    code_retour: int | None = None
    stdout: str = ""
    stderr: str = ""
    tronque: bool = False
    erreur: str | None = None

    @property
    def duree(self) -> float | None:
        if self.demarre is None:
            return None
        return (self.fini or time.time()) - self.demarre

    def en_dict(self) -> dict[str, Any]:
        donnees = asdict(self)
        donnees["duree_s"] = round(self.duree, 2) if self.duree is not None else None
        return donnees


class Registre:
    """Le magasin de tâches. Écriture atomique, relecture au démarrage."""

    def __init__(self, dossier: Path) -> None:
        self.dossier = dossier
        self.dossier.mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()
        self._taches: dict[str, Tache] = {}
        self._recharger()

    def _chemin(self, identifiant: str) -> Path:
        return self.dossier / f"{identifiant}.json"

    def _recharger(self) -> None:
        reprises = 0
        for fichier in sorted(self.dossier.glob("*.json")):
            try:
                brut = json.loads(fichier.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue  # écriture interrompue : on ignore plutôt que de casser
            brut.pop("duree_s", None)
            tache = Tache(**brut)
            if tache.etat in (EN_COURS, EN_ATTENTE):
                # Le service a redémarré pendant : le dire, plutôt que de
                # laisser une tâche « en cours » qui n'avance plus.
                tache.etat = INTERROMPU
                tache.erreur = "service redémarré pendant l'exécution"
                tache.fini = tache.fini or time.time()
                reprises += 1
                self._ecrire(tache)
            self._taches[tache.id] = tache
        if reprises:
            alerter("tâches reclassées interrompues au démarrage", nombre=reprises)

    def _ecrire(self, tache: Tache) -> None:
        cible = self._chemin(tache.id)
        temporaire = cible.with_suffix(".json.tmp")
        temporaire.write_text(
            json.dumps(tache.en_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporaire, cible)  # atomique : jamais de fichier à moitié écrit

    def creer(self, commande: list[str], endpoint: str, lourde: bool) -> Tache:
        tache = Tache(id=uuid.uuid4().hex[:16], commande=commande, endpoint=endpoint, lourde=lourde)
        with self._verrou:
            self._taches[tache.id] = tache
            self._ecrire(tache)
        return tache

    def majorer(self, tache: Tache, **champs: Any) -> None:
        with self._verrou:
            for cle, valeur in champs.items():
                setattr(tache, cle, valeur)
            self._ecrire(tache)

    def lire(self, identifiant: str) -> Tache | None:
        return self._taches.get(identifiant)

    def lister(self, limite: int = 50, etat: str | None = None) -> list[Tache]:
        taches = sorted(self._taches.values(), key=lambda t: t.cree, reverse=True)
        if etat:
            taches = [t for t in taches if t.etat == etat]
        return taches[:limite]

    def compter(self) -> dict[str, int]:
        compte: dict[str, int] = {}
        for tache in self._taches.values():
            compte[tache.etat] = compte.get(tache.etat, 0) + 1
        return compte


def _tronquer(texte: str) -> tuple[str, bool]:
    """Garde la TÊTE et la QUEUE : le début dit ce qui a été lancé, la fin dit
    pourquoi ça a échoué. Couper au milieu perd la seconde."""
    if len(texte) <= config.SORTIE_MAX:
        return texte, False
    moitie = config.SORTIE_MAX // 2
    coupe = len(texte) - config.SORTIE_MAX
    return (
        texte[:moitie] + f"\n\n… [{coupe} caractères retirés] …\n\n" + texte[-moitie:],
        True,
    )


class Executeur:
    """Deux files : une pour les commandes payantes, une pour les gratuites."""

    def __init__(self, registre: Registre) -> None:
        self.registre = registre
        self._file_lourde: Queue[Tache] = Queue()
        self._legeres = ThreadPoolExecutor(max_workers=2, thread_name_prefix="legere")
        self._ouvrier = threading.Thread(target=self._boucle_lourde, daemon=True, name="lourde")
        self._ouvrier.start()
        self._en_cours_lourde: str | None = None

    # -- files ------------------------------------------------------------- #
    def soumettre(self, tache: Tache) -> Tache:
        tracer("tâche acceptée", tache=tache.id, endpoint=tache.endpoint,
               lourde=tache.lourde, commande=tache.commande)
        if tache.lourde:
            self._file_lourde.put(tache)
        else:
            self._legeres.submit(self._executer, tache)
        return tache

    def _boucle_lourde(self) -> None:
        while True:
            tache = self._file_lourde.get()
            self._en_cours_lourde = tache.id
            try:
                self._executer(tache)
            finally:
                self._en_cours_lourde = None
                self._file_lourde.task_done()

    @property
    def attente_lourde(self) -> int:
        return self._file_lourde.qsize()

    @property
    def lourde_en_cours(self) -> str | None:
        return self._en_cours_lourde

    # -- exécution --------------------------------------------------------- #
    def _executer(self, tache: Tache) -> None:
        self.registre.majorer(tache, etat=EN_COURS, demarre=time.time())
        tracer("tâche démarrée", tache=tache.id, commande=tache.commande)
        try:
            acheve = subprocess.run(
                tache.commande,
                cwd=str(config.RACINE_CODE),
                env=config.environnement_etages(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.DUREE_MAX,
            )
        except subprocess.TimeoutExpired:
            self.registre.majorer(
                tache, etat=ECHEC, fini=time.time(),
                erreur=f"dépassement de {config.DUREE_MAX} s",
            )
            echouer("tâche expirée", tache=tache.id, duree_max=config.DUREE_MAX)
            return
        except (OSError, ValueError) as err:
            self.registre.majorer(tache, etat=ECHEC, fini=time.time(), erreur=str(err))
            echouer("tâche non lançable", tache=tache.id, erreur=str(err))
            return

        sortie, coupe_o = _tronquer(acheve.stdout or "")
        erreur, coupe_e = _tronquer(acheve.stderr or "")
        self.registre.majorer(
            tache,
            etat=FINI if acheve.returncode == 0 else ECHEC,
            fini=time.time(),
            code_retour=acheve.returncode,
            stdout=sortie,
            stderr=erreur,
            tronque=coupe_o or coupe_e,
        )
        tracer(
            "tâche terminée", tache=tache.id, code_retour=acheve.returncode,
            duree_s=round(tache.duree or 0, 2),
            etat=FINI if acheve.returncode == 0 else ECHEC,
        )
