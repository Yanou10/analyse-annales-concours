"""Schémas d'outils et construction des prompts.

Le modèle ne répond JAMAIS en prose : il appelle un outil dont le schéma est
déclaré ici, en mode `strict`. Les contraintes non supportées par le mode strict
(minItems, maxLength…) sont volontairement absentes du schéma envoyé et validées
côté client dans `valider_decisions`.

Ordre du prompt, strictement : critère d'admission (constant, caché)
                            -> consignes (constant, caché)
                            -> unités de la section (variable, non caché)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import Profil
from .segmentation import Unite

NOM_OUTIL_NOTIONS = "proposer_notions"
NOM_OUTIL_MENTIONS = "classer_mentions"

VERDICTS = ["admis", "admis_reformule", "eclate", "refuse"]
ORIGINES = ["notions", "commentaires", "mise_en_oeuvre", "annexe", "prose"]


def schema_notions(profil: Profil) -> dict[str, Any]:
    notion = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "slug",
            "libelle",
            "definition_operatoire",
            "declencheurs",
            "exclusions",
            "langages_plausibles",
            "origine_cellule",
        ],
        "properties": {
            "slug": {
                "type": "string",
                "description": (
                    "identifiant court en snake_case, sans accent, stable dans le "
                    "temps. Décrit l'action, pas l'objet. Ex : preuve_terminaison_variant"
                ),
            },
            "libelle": {
                "type": "string",
                "description": "Verbe à l'infinitif en tête. Une action, pas un objet.",
            },
            "definition_operatoire": {
                "type": "string",
                "description": (
                    "1 à 2 phrases décrivant CE QU'UNE QUESTION DOIT DEMANDER pour "
                    "que la notion s'applique. Surtout pas une définition de cours."
                ),
            },
            "declencheurs": {
                "type": "array",
                "description": "2 à 4 formulations de consigne typiques.",
                "items": {"type": "string"},
            },
            "exclusions": {
                "type": "array",
                "description": (
                    "Ce que la notion n'est PAS, avec renvoi vers le slug qui "
                    "couvre le cas. Champ anti-étiquette-aimant : le renseigner "
                    "sérieusement est ce qui empêche deux notions de se recouvrir."
                ),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["motif", "voir_slug"],
                    "properties": {
                        "motif": {"type": "string"},
                        "voir_slug": {
                            "type": ["string", "null"],
                            "description": (
                                "slug d'une autre notion, ou null si le cas ne "
                                "relève d'aucune notion du référentiel."
                            ),
                        },
                    },
                },
            },
            "langages_plausibles": {
                "type": "array",
                "description": (
                    "INDICATION seulement. Ne servira jamais de valeur par défaut "
                    "à l'axe langage lors de l'étiquetage."
                ),
                "items": {"type": "string", "enum": profil.valeurs_langage},
            },
            "origine_cellule": {
                "type": "string",
                "enum": ORIGINES,
                "description": "D'où vient l'action retenue dans l'unité source.",
            },
            "section_cible": {
                "type": "string",
                "enum": profil.ids_sections_cibles,
                "description": (
                    "Section thématique du référentiel. On range la notion là où "
                    "un candidat irait la chercher pour réviser, pas là où le "
                    "programme la range."
                ),
            },
        },
    }
    notion["required"].append("section_cible")

    decision = {
        "type": "object",
        "additionalProperties": False,
        "required": ["unite_id", "verdict", "raison", "notions"],
        "properties": {
            "unite_id": {
                "type": "string",
                "description": "identifiant de l'unité, repris tel quel.",
            },
            "verdict": {
                "type": "string",
                "enum": VERDICTS,
                "description": (
                    "admis : l'entrée est déjà nommée par l'action. "
                    "admis_reformule : une seule notion, renommée par l'action. "
                    "eclate : plusieurs notions distinctes en sortent. "
                    "refuse : objet, terme, définition ou chapeau."
                ),
            },
            "raison": {
                "type": "string",
                "description": (
                    "Une phrase justifiant le verdict par le critère d'admission. "
                    "Pour un refus, dire ce qui manque pour être une action révisable."
                ),
            },
            "notions": {
                "type": "array",
                "description": "vide si verdict = refuse.",
                "items": notion,
            },
        },
    }

    return {
        "name": NOM_OUTIL_NOTIONS,
        "description": (
            "Rend une décision d'admission pour chaque unité soumise, et les "
            "notions qui en découlent."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["decisions"],
            "properties": {
                "decisions": {
                    "type": "array",
                    "description": "Exactement une entrée par unité soumise.",
                    "items": decision,
                }
            },
        },
    }


def schema_mentions(profil: Profil) -> dict[str, Any]:
    portees = list(profil.portees_restrictives.keys())
    return {
        "name": NOM_OUTIL_MENTIONS,
        "description": "Classe chaque mention restrictive selon sa portée réelle.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["mentions"],
            "properties": {
                "mentions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["mention_id", "portee", "objet", "justification"],
                        "properties": {
                            "mention_id": {"type": "string"},
                            "portee": {"type": "string", "enum": portees},
                            "objet": {
                                "type": "string",
                                "description": (
                                    "L'objet précis visé, en 1 à 6 mots. Sert à "
                                    "motiver un statut hors_referentiel lisible "
                                    "plutôt qu'un panier opaque."
                                ),
                            },
                            "justification": {"type": "string"},
                        },
                    },
                }
            },
        },
    }


# --------------------------------------------------------------------------- #
# Prompts. Le préfixe constant est identique d'un appel à l'autre : c'est lui
# qui bénéficie du cache. Toute interpolation variable ici tuerait le cache.
# --------------------------------------------------------------------------- #

CONSIGNES = """\
MÉTHODE

Tu reçois les unités d'une seule section du programme. Rends exactement une
décision par unité, dans l'ordre où elles te sont données, en reprenant
`unite_id` tel quel.

Avant de décider, lis toute la section : une entrée qui paraît être un simple
terme est parfois le chapeau des entrées suivantes (donc refusée), et une
entrée qui paraît anodine porte parfois la seule action évaluable de la section.

Pour chaque notion produite :
  - `libelle` commence par un verbe à l'infinitif ;
  - `definition_operatoire` décrit la QUESTION, pas l'objet ;
  - `exclusions` cite au moins un cas voisin qu'il ne faut pas confondre, avec
    le slug qui le couvre — c'est ce champ qui empêchera l'étiquetage de créer
    une étiquette-aimant ;
  - `slug` est stable, sans accent, et ne reprend pas la numérotation du
    programme (la numérotation changera, pas la notion).

Ne produis jamais deux notions dont les définitions opératoires se recouvrent.
Si tu hésites entre deux découpages, choisis celui qui correspond à deux
séances de révision distinctes.

N'invente aucune notion absente de l'unité : tu décides, tu ne complètes pas.
"""


def prefixe_constant(profil: Profil) -> list[dict[str, Any]]:
    """Blocs système constants — le dernier porte le point de cache."""
    genres = "\n".join(f"  - {cle} : {val}" for cle, val in profil.genres.items())
    sections = "\n".join(
        f"  - {s['id']} ({s['libelle']}) : {' '.join(s.get('perimetre', '').split())}"
        for s in profil.sections_cibles
    )
    texte = (
        "Tu construis un référentiel de NOTIONS ATTRIBUABLES à partir du "
        f"programme officiel de la matière « {profil.matiere} ».\n\n"
        "Ce référentiel n'est pas un miroir du programme : il sert à un candidat "
        "qui veut savoir quoi réviser en priorité avant un concours.\n\n"
        f"{profil.critere_admission}\n\n"
        f"GENRES D'UNITÉS QUE TU PEUX RECEVOIR :\n{genres}\n\n"
        f"SECTIONS CIBLES DU RÉFÉRENTIEL :\n{sections}\n\n"
        f"{CONSIGNES}"
    )
    return [
        {
            "type": "text",
            "text": texte,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def message_section(unites: list[Unite]) -> str:
    section = unites[0].section
    chemin = " > ".join(section.chemin)
    corps = "\n\n".join(u.rendu() for u in unites)
    return (
        f"SECTION {section.id} — {chemin}\n"
        f"{len(unites)} unité(s) à décider.\n\n"
        f"{corps}"
    )


def prefixe_mentions(profil: Profil) -> list[dict[str, Any]]:
    portees = "\n".join(
        f"  - {cle} : {val.strip()}" for cle, val in profil.portees_restrictives.items()
    )
    texte = (
        "Tu classes les mentions restrictives d'un programme officiel "
        f"({profil.matiere}).\n\n"
        "Ces mentions ne sont pas de même nature, et les confondre est une faute "
        "coûteuse : seule la première portée autorise à déclarer une question "
        "hors référentiel. Les deux autres bornent l'enseignement, pas l'épreuve "
        "— un concours peut parfaitement poser une technique « non exigible » en "
        "la rappelant dans son énoncé.\n\n"
        f"PORTÉES :\n{portees}\n\n"
        "Rends une entrée par mention, en reprenant `mention_id` tel quel."
    )
    return [{"type": "text", "text": texte, "cache_control": {"type": "ephemeral"}}]


# --------------------------------------------------------------------------- #
# Validation côté client des contraintes non exprimables en mode strict.
#
# Registre de règles, et non plus une suite de `if` levant une exception.
# Deux propriétés que la suite de `if` n'avait pas, et dont l'absence a coûté
# §4.3 (glouton, diviser pour régner, dichotomie, programmation dynamique) :
#
#   - la granularité du rejet est l'OBJET fautif — une notion, ou une unité —
#     jamais la section. §4.3 portait six unités dont une seule était fautive ;
#     l'ancien validateur levait, l'appelant abandonnait la section, et cinq
#     unités valides partaient avec la sixième ;
#   - une violation qui ne porte que sur l'étiquette et non sur le fond est
#     déclarée `REPARABLE` et porte sa normalisation. `eclate` avec une seule
#     notion en est le cas d'école : le modèle a produit une notion utilisable
#     et s'est trompé de mot pour la qualifier.
#
# Toute réparation appliquée est rendue dans les `constats` du rapport, que
# l'appelant reporte dans manifest.yaml. Une correction silencieuse serait le
# même défaut que la section perdue silencieusement.
# --------------------------------------------------------------------------- #

FATALE = "fatale"
REPARABLE = "reparable"

#: Longueur minimale d'une définition opératoire, en caractères.
MIN_DEFINITION = 40
#: Bornes du nombre de déclencheurs par notion.
MIN_DECLENCHEURS, MAX_DECLENCHEURS = 1, 6


class ErreurContrat(ValueError):
    """La charge est inexploitable dans son ensemble : rien à sauver.

    Réservée aux violations qui portent sur l'enveloppe, pas sur son contenu.
    Une unité fautive ne lève JAMAIS : elle est rejetée individuellement.
    """


@dataclass(frozen=True)
class Constat:
    """Une règle violée sur un objet précis, et ce qui en a été fait."""

    code: str
    cible: str  # unite_id, ou unite_id/slug pour une notion
    severite: str
    message: str
    reparation: str | None = None  # renseigné si severite == REPARABLE

    def rendu(self) -> str:
        if self.reparation:
            return f"{self.cible} : {self.message} → {self.reparation}"
        return f"{self.cible} : {self.message}"


@dataclass
class RapportContrat:
    """Ce qui est retenu, et le détail de ce qui a été réparé ou rejeté."""

    decisions: list[dict[str, Any]] = field(default_factory=list)
    constats: list[Constat] = field(default_factory=list)

    @property
    def reparations(self) -> list[Constat]:
        return [c for c in self.constats if c.severite == REPARABLE]

    @property
    def rejets(self) -> list[Constat]:
        return [c for c in self.constats if c.severite == FATALE]


@dataclass(frozen=True)
class Regle:
    """Une contrainte de forme, sa sévérité, et sa normalisation le cas échéant.

    `verifier` rend None si la règle est respectée, sinon le message décrivant
    la violation. `repare` mute l'objet et rend la description de ce qu'elle a
    fait ; elle n'est appelée que pour une règle `REPARABLE`.
    """

    code: str
    severite: str
    verifier: Callable[[dict[str, Any], dict[str, Any]], str | None]
    repare: Callable[[dict[str, Any], dict[str, Any]], str] | None = None

    def __post_init__(self) -> None:
        if self.severite == REPARABLE and self.repare is None:
            raise ValueError(f"règle {self.code} déclarée réparable sans normalisation")
        if self.severite == FATALE and self.repare is not None:
            raise ValueError(f"règle {self.code} déclarée fatale mais porte une normalisation")


def _normaliser_slug(brut: str) -> str:
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", brut or "") if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "_", sans_accent.lower()).strip("_")


# --- Règles portant sur une notion ----------------------------------------- #


def _v_slug_irrecuperable(notion, _ctx):
    if not _normaliser_slug(notion.get("slug", "")):
        return f"slug {notion.get('slug')!r} sans caractère exploitable"
    return None


def _v_slug_non_normalise(notion, _ctx):
    brut = notion.get("slug", "")
    if brut != _normaliser_slug(brut):
        return f"slug {brut!r} hors forme snake_case sans accent"
    return None


def _r_slug_non_normalise(notion, _ctx):
    ancien = notion["slug"]
    notion["slug"] = _normaliser_slug(ancien)
    return f"slug normalisé en {notion['slug']!r}"


def _v_declencheurs_absents(notion, _ctx):
    if len(notion.get("declencheurs") or []) < MIN_DECLENCHEURS:
        return "aucun déclencheur : la notion serait inattribuable"
    return None


def _v_declencheurs_trop_nombreux(notion, _ctx):
    nombre = len(notion.get("declencheurs") or [])
    if nombre > MAX_DECLENCHEURS:
        return f"{nombre} déclencheurs (maximum {MAX_DECLENCHEURS})"
    return None


def _r_declencheurs_trop_nombreux(notion, _ctx):
    retires = len(notion["declencheurs"]) - MAX_DECLENCHEURS
    notion["declencheurs"] = notion["declencheurs"][:MAX_DECLENCHEURS]
    return f"{retires} déclencheur(s) surnuméraire(s) retiré(s)"


def _v_exclusions_absentes(notion, _ctx):
    if not notion.get("exclusions"):
        return "aucun critère d'exclusion (champ anti-étiquette-aimant vide)"
    return None


def _v_definition_trop_courte(notion, _ctx):
    if len(notion.get("definition_operatoire", "")) < MIN_DEFINITION:
        return (
            f"définition opératoire de {len(notion.get('definition_operatoire', ''))} "
            f"caractères (minimum {MIN_DEFINITION})"
        )
    return None


def _v_langages_hors_profil(notion, ctx):
    hors = set(notion.get("langages_plausibles") or []) - ctx["langages"]
    if hors:
        return f"langages hors profil {sorted(hors)}"
    return None


def _r_langages_hors_profil(notion, ctx):
    hors = sorted(set(notion.get("langages_plausibles") or []) - ctx["langages"])
    notion["langages_plausibles"] = [
        v for v in notion.get("langages_plausibles") or [] if v in ctx["langages"]
    ]
    # Le champ est déclaré « INDICATION seulement » et ne sert jamais de valeur
    # par défaut à l'étiquetage : le purger ne fait perdre aucune décision.
    return f"langages {hors} retirés de l'indication"


def _v_section_cible_inconnue(notion, ctx):
    cible = notion.get("section_cible")
    if cible not in ctx["sections"]:
        return f"section_cible inconnue {cible!r}"
    return None


REGLES_NOTION: list[Regle] = [
    Regle("slug_irrecuperable", FATALE, _v_slug_irrecuperable),
    Regle("slug_non_normalise", REPARABLE, _v_slug_non_normalise, _r_slug_non_normalise),
    Regle("declencheurs_absents", FATALE, _v_declencheurs_absents),
    Regle(
        "declencheurs_trop_nombreux",
        REPARABLE,
        _v_declencheurs_trop_nombreux,
        _r_declencheurs_trop_nombreux,
    ),
    Regle("exclusions_absentes", FATALE, _v_exclusions_absentes),
    Regle("definition_trop_courte", FATALE, _v_definition_trop_courte),
    Regle(
        "langages_hors_profil", REPARABLE, _v_langages_hors_profil, _r_langages_hors_profil
    ),
    Regle("section_cible_inconnue", FATALE, _v_section_cible_inconnue),
]


# --- Règles portant sur une décision --------------------------------------- #
#
# Elles s'appliquent APRÈS les règles de notion : le compte de notions qu'elles
# lisent est celui qui subsiste une fois les notions fautives écartées. Une
# unité `eclate` dont une notion sur deux est rejetée devient donc, ici même,
# un `admis_reformule` cohérent plutôt qu'une seconde violation.

def _v_refuse_avec_notions(decision, _ctx):
    if decision.get("verdict") == "refuse" and (decision.get("notions") or []):
        return f"verdict refuse avec {len(decision['notions'])} notion(s)"
    return None


def _v_verdict_sans_notion(decision, _ctx):
    if decision.get("verdict") != "refuse" and not (decision.get("notions") or []):
        return f"verdict {decision.get('verdict')} sans aucune notion retenue"
    return None


def _v_eclate_notion_unique(decision, _ctx):
    if decision.get("verdict") == "eclate" and len(decision.get("notions") or []) == 1:
        return "verdict eclate avec une seule notion"
    return None


def _r_eclate_notion_unique(decision, _ctx):
    decision["verdict"] = "admis_reformule"
    return "verdict normalisé en admis_reformule"


def _v_admis_notions_multiples(decision, _ctx):
    if decision.get("verdict") in ("admis", "admis_reformule") and len(
        decision.get("notions") or []
    ) > 1:
        return f"verdict {decision['verdict']} avec {len(decision['notions'])} notions"
    return None


def _r_admis_notions_multiples(decision, _ctx):
    decision["verdict"] = "eclate"
    return "verdict normalisé en eclate"


def _v_raison_vide(decision, _ctx):
    if not (decision.get("raison") or "").strip():
        return "raison vide"
    return None


def _r_raison_vide(decision, _ctx):
    decision["raison"] = "(raison absente de la réponse du modèle, complétée à la validation)"
    return "raison marquée comme absente"


REGLES_DECISION: list[Regle] = [
    Regle("refuse_avec_notions", FATALE, _v_refuse_avec_notions),
    Regle("verdict_sans_notion", FATALE, _v_verdict_sans_notion),
    Regle(
        "eclate_notion_unique", REPARABLE, _v_eclate_notion_unique, _r_eclate_notion_unique
    ),
    Regle(
        "admis_notions_multiples",
        REPARABLE,
        _v_admis_notions_multiples,
        _r_admis_notions_multiples,
    ),
    Regle("raison_vide", REPARABLE, _v_raison_vide, _r_raison_vide),
]


def _appliquer(
    regles: list[Regle],
    objet: dict[str, Any],
    contexte: dict[str, Any],
    cible: str,
    constats: list[Constat],
) -> bool:
    """Passe le registre sur un objet. Rend False si l'objet est disqualifié."""
    valide = True
    for regle in regles:
        message = regle.verifier(objet, contexte)
        if message is None:
            continue
        if regle.severite == FATALE:
            constats.append(Constat(regle.code, cible, FATALE, message))
            valide = False
            break  # inutile de continuer à mesurer un objet déjà écarté
        reparation = regle.repare(objet, contexte)  # type: ignore[misc]
        constats.append(Constat(regle.code, cible, REPARABLE, message, reparation))
    return valide


def valider_decisions(
    charge: dict[str, Any], unites: list[Unite], profil: Profil
) -> RapportContrat:
    """Filtre et normalise les décisions d'une section.

    Ne lève que si la charge entière est inexploitable. Toute autre violation
    se résout au niveau de l'objet fautif : la section survit à ses unités
    invalides.
    """
    decisions = charge.get("decisions")
    if not isinstance(decisions, list):
        raise ErreurContrat("`decisions` absent ou non tabulaire")

    rapport = RapportContrat()
    contexte = {
        "langages": set(profil.valeurs_langage),
        "sections": set(profil.ids_sections_cibles),
    }

    attendus = [u.id for u in unites]
    vus: set[str] = set()

    for decision in decisions:
        unite_id = decision.get("unite_id")
        cible = str(unite_id)
        if unite_id not in attendus:
            rapport.constats.append(
                Constat(
                    "unite_inventee",
                    cible,
                    FATALE,
                    "unité absente de la section soumise",
                )
            )
            continue
        if unite_id in vus:
            rapport.constats.append(
                Constat("unite_dupliquee", cible, FATALE, "seconde décision pour la même unité")
            )
            continue
        vus.add(unite_id)

        retenues = []
        for notion in decision.get("notions") or []:
            cible_notion = f"{unite_id}/{notion.get('slug', '?')}"
            if _appliquer(REGLES_NOTION, notion, contexte, cible_notion, rapport.constats):
                retenues.append(notion)
        decision["notions"] = retenues

        if _appliquer(REGLES_DECISION, decision, contexte, cible, rapport.constats):
            rapport.decisions.append(decision)

    for manquant in [i for i in attendus if i not in vus]:
        rapport.constats.append(
            Constat("unite_sans_decision", manquant, FATALE, "aucune décision rendue")
        )

    if not rapport.decisions:
        # Aucune unité ne survit : ce n'est plus une unité fautive qu'on écarte,
        # c'est l'appel entier qui est à refaire. Seul cas où la section tombe.
        raise ErreurContrat(
            f"aucune décision exploitable sur {len(attendus)} unité(s) — "
            f"premiers rejets : {[c.rendu() for c in rapport.rejets[:3]]}"
        )
    return rapport
