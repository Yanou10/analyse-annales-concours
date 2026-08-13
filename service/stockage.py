"""MinIO : l'entrée et la sortie du service.

Le service ne suppose plus qu'un fichier est déjà là. Il descend ce dont la
commande a besoin dans un espace de travail jetable, exécute, remonte ce qui a
été produit, et détruit l'espace — que la commande ait réussi ou non.

Deux règles portent la sûreté :

1. **Une clé d'objet n'est pas un chemin.** Elle est validée avant d'être
   transformée en chemin local, et le chemin obtenu est vérifié comme
   appartenant à l'espace de travail. Un objet nommé `../../etc/passwd`
   écrirait ailleurs, et MinIO accepte parfaitement ce nom.
2. **Rien n'est reversé avant que la commande ait réussi.** Une sortie partielle
   déposée dans le seau se lirait comme un résultat.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from . import config
from .config import CheminRefuse, valider_cle
from .journalisation import tracer


class StockageIndisponible(RuntimeError):
    """MinIO injoignable ou mal configuré."""


@dataclass
class Objet:
    cle: str
    taille: int
    modifie: str | None


class Stockage:
    """Enveloppe mince autour du client MinIO. Aucune logique métier."""

    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from minio import Minio
            except ImportError:  # pragma: no cover
                raise StockageIndisponible(
                    "le paquet `minio` est absent — installer '.[service]'"
                ) from None
            if not config.MINIO_CLE or not config.MINIO_SECRET:
                raise StockageIndisponible(
                    "identifiants MinIO absents : définir MINIO_ACCESS_KEY et "
                    "MINIO_SECRET_KEY (ou MINIO_ROOT_USER / MINIO_ROOT_PASSWORD)"
                )
            self._client = Minio(
                config.MINIO_URL,
                access_key=config.MINIO_CLE,
                secret_key=config.MINIO_SECRET,
                secure=config.MINIO_TLS,
            )
        return self._client

    # -- diagnostic --------------------------------------------------------- #
    def etat(self) -> dict[str, Any]:
        """Pour `/sante` : ne lève jamais, décrit ce qu'il en est."""
        try:
            client = self.client
            seaux = {
                nom: client.bucket_exists(nom)
                for nom in (config.SEAU_PROGRAMMES, config.SEAU_CORPUS, config.SEAU_SORTIES)
            }
            return {"joignable": True, "url": config.MINIO_URL, "seaux": seaux}
        except Exception as err:  # noqa: BLE001 — /sante ne doit pas tomber
            return {
                "joignable": False,
                "url": config.MINIO_URL,
                "erreur": f"{type(err).__name__}: {err}",
            }

    def assurer_seaux(self) -> None:
        for nom in (config.SEAU_PROGRAMMES, config.SEAU_CORPUS, config.SEAU_SORTIES):
            if not self.client.bucket_exists(nom):
                self.client.make_bucket(nom)
                tracer("seau créé", seau=nom)

    # -- lecture ------------------------------------------------------------ #
    def lister(self, seau: str, prefixe: str = "", recursif: bool = True) -> Iterator[Objet]:
        for objet in self.client.list_objects(seau, prefix=prefixe, recursive=recursif):
            yield Objet(
                cle=objet.object_name,
                taille=objet.size or 0,
                modifie=objet.last_modified.isoformat() if objet.last_modified else None,
            )

    def existe(self, seau: str, cle: str) -> bool:
        try:
            self.client.stat_object(seau, cle)
            return True
        except Exception:  # noqa: BLE001 — l'absence est une réponse, pas une panne
            return False

    def descendre(self, seau: str, cle: str, destination: Path) -> Path:
        """Un objet vers un fichier local, sous `destination` (déjà contrainte)."""
        cle = valider_cle(cle)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.fget_object(seau, cle, str(destination))
        return destination

    def descendre_prefixe(self, seau: str, prefixe: str, dossier: Path) -> list[Path]:
        """Tout un préfixe vers un dossier, en conservant l'arborescence.

        Le chemin de chaque objet est vérifié APRÈS résolution : c'est la seule
        vérification qui tienne, un nom d'objet pouvant contenir n'importe quoi.
        """
        dossier.mkdir(parents=True, exist_ok=True)
        racine = dossier.resolve()
        descendus: list[Path] = []
        for objet in self.lister(seau, prefixe):
            relatif = objet.cle[len(prefixe):].lstrip("/")
            if not relatif:
                continue
            cible = (racine / relatif).resolve()
            try:
                cible.relative_to(racine)
            except ValueError:
                raise CheminRefuse(
                    f"objet refusé, il sortirait de l'espace de travail : {objet.cle!r}"
                ) from None
            cible.parent.mkdir(parents=True, exist_ok=True)
            self.client.fget_object(seau, objet.cle, str(cible))
            descendus.append(cible)
        return descendus

    # -- écriture ----------------------------------------------------------- #
    def monter(self, chemin: Path, seau: str, cle: str) -> str:
        cle = valider_cle(cle)
        self.client.fput_object(seau, cle, str(chemin))
        return cle

    def monter_dossier(self, dossier: Path, seau: str, prefixe: str) -> list[str]:
        racine = dossier.resolve()
        montes: list[str] = []
        for chemin in sorted(racine.rglob("*")):
            if chemin.is_file():
                relatif = chemin.relative_to(racine).as_posix()
                montes.append(self.monter(chemin, seau, f"{prefixe.rstrip('/')}/{relatif}"))
        return montes

    def monter_json(self, donnees: Any, seau: str, cle: str) -> str:
        cle = valider_cle(cle)
        charge = json.dumps(donnees, ensure_ascii=False, indent=2).encode("utf-8")
        self.client.put_object(
            seau, cle, io.BytesIO(charge), length=len(charge),
            content_type="application/json",
        )
        return cle


stockage = Stockage()
