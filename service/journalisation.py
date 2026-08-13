"""Journalisation structurée en JSON sur stdout, pour que `docker logs` serve.

Une ligne = un objet JSON. Les champs métier passent par `extra={"donnees": …}`
plutôt que par interpolation dans le message : un message formaté se relit à
l'œil, un champ se filtre avec `jq`.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class FormatJSON(logging.Formatter):
    def format(self, enregistrement: logging.LogRecord) -> str:
        ligne: dict[str, Any] = {
            "horodatage": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(enregistrement.created))
            + f".{int(enregistrement.msecs):03d}Z",
            "niveau": enregistrement.levelname.lower(),
            "source": enregistrement.name,
            "message": enregistrement.getMessage(),
        }
        donnees = getattr(enregistrement, "donnees", None)
        if isinstance(donnees, dict):
            ligne.update(donnees)
        if enregistrement.exc_info:
            ligne["exception"] = self.formatException(enregistrement.exc_info)
        return json.dumps(ligne, ensure_ascii=False, default=str)


def installer(niveau: str = "INFO") -> logging.Logger:
    sortie = logging.StreamHandler(sys.stdout)
    sortie.setFormatter(FormatJSON())
    racine = logging.getLogger()
    racine.handlers[:] = [sortie]
    racine.setLevel(niveau)
    # uvicorn installe ses propres gestionnaires : les rabattre sur le nôtre,
    # sinon la moitié des lignes de `docker logs` n'est pas du JSON.
    for nom in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        journal = logging.getLogger(nom)
        journal.handlers[:] = [sortie]
        journal.propagate = False
    return logging.getLogger("service")


journal = logging.getLogger("service")


def tracer(message: str, **donnees: Any) -> None:
    journal.info(message, extra={"donnees": donnees})


def alerter(message: str, **donnees: Any) -> None:
    journal.warning(message, extra={"donnees": donnees})


def echouer(message: str, **donnees: Any) -> None:
    journal.error(message, extra={"donnees": donnees})
