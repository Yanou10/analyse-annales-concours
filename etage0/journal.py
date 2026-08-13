"""Reprise sur résultats partiels.

Chaque appel réussi est écrit dans un journal JSONL, indexé par une empreinte
qui couvre TOUT ce qui pourrait changer la réponse : le contenu des unités, le
modèle, le fournisseur, la version du prompt et le critère d'admission. Changer
l'un d'eux invalide l'entrée et déclenche un réappel — silencieusement réutiliser
un résultat obtenu sous un autre prompt est la meilleure façon de mesurer une
chose et d'en publier une autre.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


def empreinte(*morceaux: str) -> str:
    condensat = hashlib.sha256()
    for morceau in morceaux:
        condensat.update(morceau.encode("utf-8"))
        condensat.update(b"\x1e")
    return condensat.hexdigest()[:16]


@dataclass
class Journal:
    chemin: Path
    _index: dict[str, dict[str, Any]]

    @classmethod
    def ouvrir(cls, chemin: Path) -> "Journal":
        index: dict[str, dict[str, Any]] = {}
        if chemin.is_file():
            for ligne in chemin.read_text(encoding="utf-8").splitlines():
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    entree = json.loads(ligne)
                except json.JSONDecodeError:
                    continue  # ligne tronquée par une interruption : on l'ignore
                index[entree["cle"]] = entree
        return cls(chemin=chemin, _index=index)

    def __contains__(self, cle: str) -> bool:
        return cle in self._index

    def lire(self, cle: str) -> dict[str, Any] | None:
        entree = self._index.get(cle)
        return entree["charge"] if entree else None

    def ecrire(self, cle: str, etiquette: str, charge: dict[str, Any], meta: dict[str, Any]) -> None:
        entree = {"cle": cle, "etiquette": etiquette, "charge": charge, "meta": meta}
        self._index[cle] = entree
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self.chemin.open("a", encoding="utf-8") as flux:
            flux.write(json.dumps(entree, ensure_ascii=False) + "\n")

    def oublier(self, prefixe_etiquette: str | None = None) -> int:
        """Purge le journal (tout, ou les entrées d'une étiquette donnée)."""
        if prefixe_etiquette is None:
            compte = len(self._index)
            self._index.clear()
            if self.chemin.is_file():
                self.chemin.unlink()
            return compte
        gardees = {
            cle: entree
            for cle, entree in self._index.items()
            if not entree["etiquette"].startswith(prefixe_etiquette)
        }
        compte = len(self._index) - len(gardees)
        self._index = gardees
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self.chemin.open("w", encoding="utf-8") as flux:
            for entree in gardees.values():
                flux.write(json.dumps(entree, ensure_ascii=False) + "\n")
        return compte

    def entrees(self) -> Iterator[dict[str, Any]]:
        yield from self._index.values()

    @property
    def taille(self) -> int:
        return len(self._index)
