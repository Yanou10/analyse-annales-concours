"""Interface d'appel LLM et ses implémentations.

Toute la pipeline passe par `FournisseurLLM.appeler_outil` : aucune couche
au-dessus ne sait quel fournisseur est actif. Un seul est branché
(anthropic) ; l'indirection est conservée comme point d'architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Reponse:
    charge: dict[str, Any]
    modele: str
    jetons_entree: int = 0
    jetons_sortie: int = 0
    jetons_cache_lus: int = 0
    jetons_cache_ecrits: int = 0
    notes: list[str] = field(default_factory=list)

    def usage(self) -> dict[str, Any]:
        """Comptage complet d'un appel, à écrire dans le journal.

        Les ÉCRITURES en cache en font partie : facturées 1,25x le prix
        d'entrée, elles n'étaient additionnées nulle part, et leur absence
        expliquait l'essentiel de l'écart entre nos comptes et la console.
        Le prompt réellement facturé est `entree + cache_lus + cache_ecrits`.
        """
        return {
            "modele": self.modele,
            "entree": self.jetons_entree,
            "cache_lus": self.jetons_cache_lus,
            "cache_ecrits": self.jetons_cache_ecrits,
            "sortie": self.jetons_sortie,
            "prompt_total": self.jetons_entree + self.jetons_cache_lus + self.jetons_cache_ecrits,
        }


class ErreurFournisseur(RuntimeError):
    pass


class RefusModele(ErreurFournisseur):
    """Le modèle a décliné la requête (stop_reason == 'refusal')."""


class FournisseurLLM(Protocol):
    nom: str

    def appeler_outil(
        self,
        blocs_systeme: list[dict[str, Any]],
        message: str,
        outil: dict[str, Any],
        max_tokens: int,
    ) -> Reponse: ...


# --------------------------------------------------------------------------- #


class FournisseurAnthropic:
    nom = "anthropic"

    #: Le repli serveur est activé par défaut : les classificateurs de sûreté
    #: d'Opus 5 peuvent décliner une requête et renvoyer un HTTP 200 portant
    #: `stop_reason: "refusal"`. Avec le repli, la requête est réexécutée
    #: côté serveur sur le modèle de repli recommandé, dans le même appel.
    BETA_REPLI = "server-side-fallback-2026-07-01"

    def __init__(
        self,
        modele: str,
        effort: str = "high",
        fallbacks: bool = True,
        reflexion: bool = True,
    ) -> None:
        import anthropic  # import différé : inutile en --dry-run

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self.modele = modele
        self.effort = effort
        self.fallbacks = fallbacks
        #: Les modèles courants n'exposent AUCUN réglage d'échantillonnage :
        #: `temperature`, `top_p` et `top_k` sont rejetés en 400 sur Sonnet 5
        #: comme sur Opus 5, 4.8 et 4.7. Il n'existe donc pas de bouton
        #: « déterminisme » ; les deux seuls leviers sont la réflexion et
        #: `output_config.effort`. Couper la réflexion est le seul moyen de
        #: réduire la variance d'une passe à l'autre — au prix de la
        #: délibération, qui garde sa place là où il faut trancher sans corrigé.
        self.reflexion = reflexion

    def appeler_outil(
        self,
        blocs_systeme: list[dict[str, Any]],
        message: str,
        outil: dict[str, Any],
        max_tokens: int,
    ) -> Reponse:
        parametres: dict[str, Any] = {
            "model": self.modele,
            "max_tokens": max_tokens,
            "system": blocs_systeme,
            "messages": [{"role": "user", "content": message}],
            "tools": [outil],
            "tool_choice": {"type": "tool", "name": outil["name"]},
            "output_config": {"effort": self.effort},
        }
        if self.reflexion:
            parametres["thinking"] = {"type": "adaptive"}

        notes: list[str] = []
        try:
            if self.fallbacks:
                try:
                    reponse = self._client.beta.messages.create(
                        betas=[self.BETA_REPLI], fallbacks="default", **parametres
                    )
                except self._anthropic.BadRequestError as err:
                    # Le repli serveur n'est pas offert par tous les modèles :
                    # Sonnet 5 rejette `fallbacks` en 400. Dégrader vaut mieux
                    # qu'échouer — sans repli on perd la reprise automatique
                    # sur refus, pas la réponse.
                    if "fallbacks" not in str(err):
                        raise
                    notes.append(f"repli serveur indisponible sur {self.modele}, appel direct")
                    reponse = self._client.messages.create(**parametres)
            else:
                reponse = self._client.messages.create(**parametres)
        except self._anthropic.NotFoundError as err:
            raise ErreurFournisseur(
                f"Modèle introuvable : {self.modele}. Vérifier ETAGE0_MODELE."
            ) from err
        except self._anthropic.RateLimitError as err:
            raise ErreurFournisseur(
                "Quota atteint. Le SDK a déjà réessayé ; relancer avec --reprendre."
            ) from err
        except self._anthropic.APIStatusError as err:
            raise ErreurFournisseur(f"Erreur API {err.status_code} : {err.message}") from err
        except self._anthropic.APIConnectionError as err:
            raise ErreurFournisseur("Réseau indisponible.") from err

        # Toujours inspecter stop_reason AVANT de lire content : sur un refus,
        # `content` est vide (refus avant génération) ou partiel (refus en cours
        # de flux) et l'indexer lèverait une IndexError trompeuse.
        if getattr(reponse, "stop_reason", None) == "refusal":
            details = getattr(reponse, "stop_details", None)
            categorie = getattr(details, "category", None) if details else None
            raise RefusModele(
                f"Requête déclinée par les classificateurs (catégorie : {categorie}). "
                "Le repli serveur n'a pas produit de réponse utilisable."
            )

        charge = None
        for bloc in reponse.content:
            if getattr(bloc, "type", None) == "tool_use" and bloc.name == outil["name"]:
                charge = bloc.input
                break
        if charge is None:
            raise ErreurFournisseur(
                f"Aucun appel à l'outil {outil['name']} "
                f"(stop_reason={getattr(reponse, 'stop_reason', '?')})"
            )

        usage = reponse.usage
        if getattr(reponse, "model", self.modele) != self.modele:
            notes.append(f"servi par {reponse.model} (repli)")
        return Reponse(
            charge=charge,
            modele=getattr(reponse, "model", self.modele),
            jetons_entree=getattr(usage, "input_tokens", 0) or 0,
            jetons_sortie=getattr(usage, "output_tokens", 0) or 0,
            jetons_cache_lus=getattr(usage, "cache_read_input_tokens", 0) or 0,
            jetons_cache_ecrits=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            notes=notes,
        )

    # ----------------------------------------------------------------------- #
    # Lots (Batch API) — moitié prix, retour asynchrone, ordre quelconque.
    # ----------------------------------------------------------------------- #

    def parametres_appel(
        self,
        blocs_systeme: list[dict[str, Any]],
        message: str,
        outil: dict[str, Any],
        max_tokens: int,
    ) -> dict[str, Any]:
        """Les paramètres EXACTS d'un appel, partagés par le synchrone et le lot.

        Deux constructions séparées finiraient par diverger, et une passe en lot
        mesurerait alors autre chose qu'une passe directe sans que rien ne le
        dise. `fallbacks` est volontairement absent : le repli serveur ne
        s'applique pas aux lots, et Sonnet 5 le rejette de toute façon.
        """
        parametres: dict[str, Any] = {
            "model": self.modele,
            "max_tokens": max_tokens,
            "system": blocs_systeme,
            "messages": [{"role": "user", "content": message}],
            "tools": [outil],
            "tool_choice": {"type": "tool", "name": outil["name"]},
            "output_config": {"effort": self.effort},
        }
        if self.reflexion:
            parametres["thinking"] = {"type": "adaptive"}
        return parametres

    def soumettre_lot(self, requetes: list[dict[str, Any]]) -> str:
        """`requetes` : [{custom_id, params}]. Rend l'identifiant du lot."""
        try:
            lot = self._client.messages.batches.create(requests=requetes)
        except self._anthropic.APIStatusError as err:
            raise ErreurFournisseur(f"Soumission du lot refusée ({err.status_code}) : {err.message}") from err
        return lot.id

    def etat_lot(self, identifiant: str) -> tuple[str, dict[str, int]]:
        lot = self._client.messages.batches.retrieve(identifiant)
        compteurs = lot.request_counts
        return lot.processing_status, {
            "aboutis": getattr(compteurs, "succeeded", 0),
            "erreurs": getattr(compteurs, "errored", 0),
            "expires": getattr(compteurs, "expired", 0),
            "annules": getattr(compteurs, "canceled", 0),
            "en_cours": getattr(compteurs, "processing", 0),
        }

    def resultats_lot(
        self, identifiant: str, outils_par_id: dict[str, str]
    ) -> dict[str, Reponse | str]:
        """custom_id → Reponse, ou une chaîne décrivant l'échec.

        Les résultats reviennent dans un ordre quelconque : c'est le `custom_id`
        qui réassocie, jamais la position. On rend un dictionnaire pour que
        l'appelant ne puisse pas se tromper d'ordre même s'il le voulait.
        """
        sorties: dict[str, Reponse | str] = {}
        for entree in self._client.messages.batches.results(identifiant):
            custom_id = entree.custom_id
            resultat = entree.result
            if resultat.type != "succeeded":
                # Remonter le MESSAGE, pas seulement le type : « errored (error) »
                # ne dit rien, et c'est ce qui a masqué pendant un temps un
                # simple plafond de compilation de grammaires.
                erreur = getattr(resultat, "error", None)
                interne = getattr(erreur, "error", None) if erreur is not None else None
                message = getattr(interne, "message", None) or getattr(erreur, "message", None)
                sorties[custom_id] = f"{resultat.type} : {message or erreur or 'sans détail'}"
                continue
            message = resultat.message
            if getattr(message, "stop_reason", None) == "refusal":
                sorties[custom_id] = "refus des classificateurs"
                continue
            nom_outil = outils_par_id.get(custom_id)
            charge = None
            for bloc in message.content:
                if getattr(bloc, "type", None) == "tool_use" and bloc.name == nom_outil:
                    charge = bloc.input
                    break
            if charge is None:
                sorties[custom_id] = (
                    f"aucun appel à l'outil {nom_outil} "
                    f"(stop_reason={getattr(message, 'stop_reason', '?')})"
                )
                continue
            usage = message.usage
            sorties[custom_id] = Reponse(
                charge=charge,
                modele=getattr(message, "model", self.modele),
                jetons_entree=getattr(usage, "input_tokens", 0) or 0,
                jetons_sortie=getattr(usage, "output_tokens", 0) or 0,
                jetons_cache_lus=getattr(usage, "cache_read_input_tokens", 0) or 0,
                jetons_cache_ecrits=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            )
        return sorties

    def compter_jetons(
        self, blocs_systeme: list[dict[str, Any]], message: str, outil: dict[str, Any]
    ) -> int:
        reponse = self._client.messages.count_tokens(
            model=self.modele,
            system=blocs_systeme,
            messages=[{"role": "user", "content": message}],
            tools=[outil],
        )
        return reponse.input_tokens


# --------------------------------------------------------------------------- #


#: Fournisseurs branchés. `FournisseurLLM` reste un Protocol et `construire`
#: reste indirecté : c'est le point d'architecture qui permettra d'en brancher
#: un autre sans que les couches au-dessus ne sachent lequel est actif.
#:
#: Le fournisseur local (ollama) a été retiré : mettre au point les prompts
#: contre les erreurs d'un modèle qu'on n'utilisera pas revient à corriger le
#: mauvais problème. La répétition sans frais se fait en `--dry-run`, qui
#: montre les prompts exacts sans joindre le moindre service — c'est là que se
#: trouvent les erreurs de plomberie.
FOURNISSEURS = ("anthropic",)


def construire(config) -> FournisseurLLM:  # noqa: ANN001 - évite un import circulaire
    if config.fournisseur == "anthropic":
        return FournisseurAnthropic(
            modele=config.modele,
            effort=config.effort,
            fallbacks=config.fallbacks,
            reflexion=config.reflexion,
        )
    raise SystemExit(
        f"Fournisseur inconnu : {config.fournisseur} "
        f"(attendu : {' | '.join(FOURNISSEURS)})"
    )
