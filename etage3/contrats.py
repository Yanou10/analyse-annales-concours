"""Schémas d'outils et prompts de l'étiquetage.

Deux appels par exercice, et c'est un choix, pas une commodité :

1. un **pré-filtrage** court qui nomme 2 à 3 sections du référentiel ;
2. l'**étiquetage** proprement dit, avec les seules notions de ces sections.

Soumettre les 182 notions à chaque exercice coûterait cher et, surtout,
noierait les notions pertinentes : le modèle choisit mieux dans 30 candidates
que dans 182. Le pré-filtrage est donc un instrument de précision autant que
d'économie.

Le multi-étiquetage est NORMAL : une question porte souvent deux ou trois
notions. Rien ici ne pousse à n'en garder qu'une.
"""

from __future__ import annotations

from typing import Any

NOM_OUTIL_SECTIONS = "choisir_sections"
NOM_OUTIL_ETIQUETTES = "etiqueter_exercice"

STATUTS = ["ok", "hors_referentiel", "figure_manquante", "indecidable"]
#: `absent_du_programme` a été RETIRÉ. Le modèle ne voit jamais le programme —
#: seulement les notions des 2 à 4 sections retenues et la liste des objets
#: exclus. Il ne pouvait donc pas distinguer « absent du programme » de
#: « absent des sections que le pré-filtrage a retenues », et n'a jamais émis
#: le statut sur 130 questions. Ce n'était pas un défaut d'implémentation :
#: on lui demandait un jugement sur un référentiel qu'il n'avait pas.
#: Le cas est désormais calculé à l'étage 4, où il est déterministe : une
#: question qu'AUCUNE notion ne couvre. C'est d'ailleurs ce que le statut
#: voulait dire.
RAISONS_HORS = ["hors_programme"]
#: valeur explicite tenant lieu de null : le mode strict refuse un enum nullable
SANS_OBJET = "sans_objet"

#: Sous ce nombre de mots, une justification n'est pas un extrait : c'est un
#: mot-clé, et un mot-clé ne prouve rien — « graphe » apparaît dans toute
#: question de graphes, y compris celles qui ne portent pas la notion.
MIN_MOTS_JUSTIFICATION = 5

#: Bornes du pré-filtrage. Portées à 4 après mesure : le modèle en
#: demandait 4 sur 5 exercices sur 9, et tronquer aurait supprimé de
#: l'information sur la foi d'un ordre sans portée sémantique.
MIN_SECTIONS, MAX_SECTIONS = 2, 4


# --------------------------------------------------------------------------- #
# Pré-filtrage
# --------------------------------------------------------------------------- #


def schema_sections(ids_sections: list[str]) -> dict[str, Any]:
    return {
        "name": NOM_OUTIL_SECTIONS,
        "description": (
            "Nomme les 2 à 4 sections du référentiel dans lesquelles se trouvent "
            "les notions de cet exercice."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["sections"],
            "properties": {
                "sections": {
                    "type": "array",
                    "description": "2 à 4 identifiants, du plus au moins probable.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "raison"],
                        "properties": {
                            "id": {"type": "string", "enum": ids_sections},
                            "raison": {
                                "type": "string",
                                "description": "Une phrase, ancrée sur ce que l'exercice DEMANDE.",
                            },
                        },
                    },
                }
            },
        },
    }


def prefixe_sections(sections: list[dict[str, str]], matiere: str) -> list[dict[str, Any]]:
    catalogue = "\n".join(
        f"  - {s['id']} ({s['libelle']}) : {' '.join((s.get('perimetre') or '').split())}"
        for s in sections
    )
    texte = (
        f"Tu tries des exercices de concours en {matiere} avant étiquetage.\n\n"
        "On te donne un exercice entier. Tu nommes les 2 à 4 sections du "
        "référentiel où se trouvent les notions qu'il mobilise. Tu ne nommes "
        "PAS de notion : seulement des sections.\n\n"
        "Choisis d'après ce que l'exercice DEMANDE de faire, pas d'après le "
        "vocabulaire qu'il emploie : un énoncé peut parler de graphes tout en "
        "demandant une preuve par récurrence.\n\n"
        "Sois large plutôt qu'étroit : une section oubliée ici fait perdre "
        "définitivement ses notions, une section de trop ne coûte que du bruit "
        "à l'étape suivante.\n\n"
        f"SECTIONS DU RÉFÉRENTIEL :\n{catalogue}"
    )
    return [{"type": "text", "text": texte, "cache_control": {"type": "ephemeral"}}]


# --------------------------------------------------------------------------- #
# Étiquetage
# --------------------------------------------------------------------------- #


def schema_etiquettes(
    ids_notions: list[str], ids_questions: list[str], valeurs_langage: list[str]
) -> dict[str, Any]:
    etiquette = {
        "type": "object",
        "additionalProperties": False,
        "required": ["notion_id", "justification"],
        "properties": {
            "notion_id": {"type": "string", "enum": ids_notions},
            "justification": {
                "type": "string",
                "description": (
                    "EXTRAIT LITTÉRAL de l'énoncé de la question, recopié mot pour "
                    f"mot, d'au moins {MIN_MOTS_JUSTIFICATION} mots. Pas de "
                    "paraphrase, pas de mot-clé isolé : le passage qui déclenche "
                    "la notion. Une justification non littérale fait rejeter "
                    "l'étiquette."
                ),
            },
        },
    }
    question = {
        "type": "object",
        "additionalProperties": False,
        "required": ["question_id", "statut", "raison_hors_referentiel",
                     "objet_hors_referentiel", "langage", "etiquettes"],
        "properties": {
            "question_id": {"type": "string", "enum": ids_questions},
            "statut": {
                "type": "string",
                "enum": STATUTS,
                "description": (
                    "ok : au moins une notion s'applique. "
                    "hors_referentiel : la question porte sur un objet retiré du "
                    "programme, ou absent du programme. "
                    "figure_manquante : la question est indécidable SANS la figure "
                    "à laquelle elle renvoie. "
                    "indecidable : ni énoncé de question, ni objet identifiable "
                    "(fiche réponse, consigne d'organisation)."
                ),
            },
            # Le mode strict refuse un enum nullable (`type: ["string","null"]`
            # avec `enum`). On passe donc par une valeur explicite `sans_objet`
            # plutôt que par null — le schéma reste vérifiable côté serveur, et
            # la conversion en None se fait à la validation.
            "raison_hors_referentiel": {
                "type": "string",
                "enum": RAISONS_HORS + [SANS_OBJET],
                "description": (
                    "hors_programme : la question porte sur un objet de la liste "
                    "des OBJETS RETIRÉS DU PROGRAMME donnée plus haut — c'est la "
                    "seule raison que tu puisses établir, puisque tu ne vois que "
                    "cette liste. N'invente pas d'autre motif : une question que "
                    "le référentiel ne couvre pas relève de `indecidable`, pas de "
                    "`hors_referentiel`. "
                    f"`{SANS_OBJET}` si le statut n'est pas hors_referentiel."
                ),
            },
            "objet_hors_referentiel": {
                "type": "string",
                "description": (
                    "L'objet précis visé, en 1 à 6 mots. Chaîne vide si le statut "
                    "n'est pas hors_referentiel."
                ),
            },
            "langage": {
                "type": "string",
                "enum": valeurs_langage,
                "description": (
                    "Déduit de la CONSIGNE de cette question seule. Si la consigne "
                    "n'impose aucun langage, c'est `theorique` ou `indetermine` — "
                    "JAMAIS le langage du préambule du sujet."
                ),
            },
            "etiquettes": {
                "type": "array",
                "description": (
                    "Vide si statut != ok. Plusieurs notions par question est le "
                    "cas NORMAL, pas l'exception."
                ),
                "items": etiquette,
            },
        },
    }
    return {
        "name": NOM_OUTIL_ETIQUETTES,
        "description": "Étiquette chaque question de l'exercice soumis.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["langage_sujet", "questions"],
            "properties": {
                "langage_sujet": {
                    "type": "string",
                    "enum": valeurs_langage,
                    "description": (
                        "Langage du sujet dans son ensemble, lu dans le préambule. "
                        "Conservé À PART : il ne doit jamais servir de valeur par "
                        "défaut au langage d'une question."
                    ),
                },
                "questions": {
                    "type": "array",
                    "description": "Exactement une entrée par question soumise.",
                    "items": question,
                },
            },
        },
    }


CONSIGNES = """\
MÉTHODE

Pour chaque question de l'exercice, rends une entrée, dans l'ordre, en
reprenant `question_id` tel quel.

Une question porte SOUVENT PLUSIEURS NOTIONS. C'est le cas normal. N'en retiens
pas une seule par principe : retiens toutes celles qu'un candidat devrait avoir
révisées pour traiter la question.

`justification` est un EXTRAIT LITTÉRAL de l'énoncé de la question, recopié mot
pour mot depuis le texte qui t'est donné. Ni résumé, ni reformulation, ni
mot-clé isolé. Une justification qui ne se retrouve pas telle quelle dans
l'énoncé fait rejeter l'étiquette, et l'étiquette seule — pas la question.

`langage` se lit dans la CONSIGNE de la question. « Écrire une fonction OCaml »
donne `ocaml` ; « donner un algorithme » donne `pseudocode` ; « montrer que »
donne `theorique`. Le fait que le sujet entier soit en OCaml ne rend pas
`ocaml` une question qui demande une preuve.

STATUTS

- `ok` dès qu'une notion s'applique.
- `hors_referentiel` UNIQUEMENT si la question porte sur un objet figurant dans
  la liste des OBJETS RETIRÉS DU PROGRAMME ci-dessus. C'est la seule chose que
  tu puisses établir : tu ne vois pas le programme. Une question que les notions
  proposées ne couvrent pas n'est pas hors référentiel — elle est `indecidable`,
  et le cas sera repris en aval.
- `figure_manquante` si, et seulement si, la question est indécidable sans la
  figure à laquelle elle renvoie. Un renvoi décoratif ne suffit pas.
- `indecidable` pour ce qui n'est pas une question d'épreuve : fiche réponse,
  consigne d'organisation, barème.

Le préambule de l'exercice t'est donné pour comprendre les questions. Tu
n'étiquettes PAS le préambule.
"""


def prefixe_etiquetage(
    notions: list[dict[str, Any]],
    matiere: str,
    exclusions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ordre imposé : référentiel, puis consignes, puis l'exercice en message.

    Le point de cache est posé sur le DERNIER bloc système, donc couvre aussi
    le référentiel. Conséquence du pré-filtrage : le préfixe n'est constant que
    pour une même combinaison de sections, et le cache ne joue qu'entre
    exercices qui partagent la même. C'est le prix du pré-filtrage, et il est
    payé sciemment — soumettre les 182 notions à chaque exercice rendrait le
    cache parfait et l'étiquetage moins précis.
    """
    blocs = []
    for notion in notions:
        exclus = "\n".join(
            f"      · PAS : {e['motif']}"
            + (f" → {e['voir']}" if e.get("voir") else "")
            for e in (notion.get("exclusions") or [])
        )
        declencheurs = "\n".join(f"      « {d} »" for d in notion.get("declencheurs") or [])
        blocs.append(
            f"  [{notion['id']}] {notion['libelle']}\n"
            f"    {' '.join(notion['definition_operatoire'].split())}\n"
            f"{declencheurs}\n{exclus}"
        )
    objets_exclus = [
        e for e in exclusions if e.get("portee") == "objet_exclu" and e.get("objet")
    ]
    liste_exclus = "\n".join(f"  - {e['objet']}" for e in objets_exclus[:40])

    texte = (
        f"RÉFÉRENTIEL DE NOTIONS ATTRIBUABLES — {matiere}\n\n"
        "Chaque notion porte sa définition opératoire (ce qu'une question doit "
        "DEMANDER pour qu'elle s'applique), ses déclencheurs typiques, et ses "
        "exclusions — les cas voisins qu'il ne faut pas lui attribuer.\n\n"
        + "\n\n".join(blocs)
        + (
            "\n\nOBJETS RETIRÉS DU PROGRAMME — une question qui porte sur l'un "
            "d'eux relève de `hors_referentiel` / `hors_programme` :\n" + liste_exclus
            if liste_exclus
            else ""
        )
    )
    return [
        {"type": "text", "text": texte},
        {"type": "text", "text": CONSIGNES, "cache_control": {"type": "ephemeral"}},
    ]


def message_exercice(exercice: dict[str, Any], fichier: str) -> str:
    lignes = [
        f"EXERCICE {exercice['id']}",
        f"source   : {fichier} · filière {exercice['filiere']}",
        f"titre    : {exercice['titre']}",
        "",
        "PRÉAMBULE (contexte, NON étiqueté) :",
        (exercice.get("preambule") or "(aucun)")[:6000],
        "",
        f"{len(exercice['questions'])} QUESTION(S) À ÉTIQUETER :",
    ]
    for question in exercice["questions"]:
        marque = " [renvoie à une figure]" if question.get("figure_manquante") else ""
        lignes += ["", f"--- {question['id']}{marque}", question["texte"][:5000]]
    return "\n".join(lignes)
