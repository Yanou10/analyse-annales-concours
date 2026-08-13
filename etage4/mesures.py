"""Calculs de l'étage 4. Aucune entrée-sortie, aucun appel : que des fonctions.

Trois règles de lecture ont été tranchées et sont appliquées ici sans option :

1. La part d'une notion se lit **en part des questions** ET **en part des
   occurrences**, les deux affichées ensemble avec la moyenne d'étiquettes par
   question. Séparément, aucune des deux ne s'interprète : 10 % des occurrences
   veut dire deux choses différentes selon qu'on pose 1,1 ou 2,5 étiquettes par
   question.
2. La couverture des questions se publie comme **intervalle**, jamais comme
   chiffre, et n'est plus une cible : deux passes identiques l'ont fait varier
   de 10,7 points. Son bon usage est comparatif.
3. Une notion à zéro n'est pas une anomalie en soi — c'est une question posée au
   corpus. On les liste par section, parce qu'une section entière à zéro et une
   notion isolée à zéro ne disent pas la même chose.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

#: Demi-amplitude observée sur le taux de couverture des questions entre deux
#: passes identiques (2026-08-11, `2022_InfoLCR-rapport`, 178 questions). À
#: réviser après la mesure de dispersion sous protocole final.
INTERVALLE_COUVERTURE_PT = 10.7

#: Au-delà, un exercice est considéré instable : le référentiel y est à sa
#: limite, et il est à instruire en priorité.
SEUIL_INSTABILITE = 0.5


#: Genres de document, dans l'ordre d'essai — le premier motif qui correspond
#: gagne. `Info-rapport` doit passer avant `InfoA/C/F`, et `TPAlgo` avant tout
#: le reste, sinon `2024_TPAlgo-MPI-rapport` serait classé en rapport de jury.
GENRES = (
    ("TPAlgo", "TPAlgo"),
    ("InfoU-exercices", "InfoU-exercices"),
    ("LCR", "LCR"),
    ("Info-rapport", "Info-rapport"),
    ("InfoA", "InfoA"),
    ("InfoC", "InfoC"),
    ("InfoF", "InfoF"),
)


def genre_de(fichier: str) -> str:
    for motif, genre in GENRES:
        if motif in fichier:
            return genre
    return "autre"


def aplatir(resultats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une question par ligne, enrichie de ce qui porte sur son exercice.

    L'étiquetage rend un objet par exercice ; toutes les ventilations ci-dessous
    travaillent par question. Faire la jointure une fois, ici, évite de la
    refaire — différemment — dans chaque sous-commande.
    """
    questions = []
    # Quatre titres d'exercice se répètent dans leur fichier (`suite-des-questions`
    # sept fois dans `2018_InfoU-exercices`), d'où 12 exercices et 73 questions
    # qui partagent un identifiant. L'ÉTIQUETAGE n'en souffre pas — chaque
    # exercice part dans son propre appel, avec son propre message — mais toute
    # mesure PAR EXERCICE les fusionnerait. On désambiguïse ici, par rang
    # d'apparition, ce qui est stable tant que l'ordre du corpus l'est. Le vrai
    # correctif est à l'étage 1 et coûte une repasse complète : il change
    # `exercice_id`, donc la clé de journal.
    vus: dict[str, int] = {}
    for resultat in resultats:
        fichier = resultat.get("fichier") or ""
        brut = resultat.get("exercice_id")
        rang = vus.get(brut, 0)
        vus[brut] = rang + 1
        commun = {
            "exercice_id": brut if rang == 0 else f"{brut}~{rang + 1}",
            "exercice_id_brut": brut,
            "fichier": fichier,
            # L'année est portée par le nom de fichier (`2021_InfoA.md`) et par
            # rien d'autre. C'est la seule variable qui explique `non_marque` :
            # les sujets antérieurs à la création de MPI n'ont aucune marque de
            # filière à propager, ce qui n'est pas une absence de donnée mais
            # une donnée — ils sont tous MP option info par construction.
            "annee": fichier[:4] if fichier[:4].isdigit() else "?",
            # Le GENRE du document explique l'essentiel de l'écart de
            # couverture entre fichiers : un recueil d'exercices pose des
            # questions courtes et attribuables (1,18–1,44 étiquette par
            # question), un rapport de jury commente (0,92–0,96), une épreuve
            # pratique décrit des manipulations (0,71–0,81). Sans cette
            # variable, l'écart se lit à tort comme une faiblesse du
            # référentiel sur telle ou telle matière.
            "genre": genre_de(fichier),
            "filiere": resultat.get("filiere"),
            "sections_retenues": tuple(resultat.get("sections_retenues") or ()),
            "langage_sujet": resultat.get("langage_sujet"),
        }
        for question in resultat.get("questions") or []:
            questions.append({**commun, **question})
    return questions


@dataclass
class Agregat:
    """Ce qui se calcule sur n'importe quel sous-ensemble de questions."""

    questions: int = 0
    etiquettes: int = 0
    statuts: Counter = field(default_factory=Counter)
    raisons_hors: Counter = field(default_factory=Counter)
    sans_notion: int = 0
    figures_manquantes: int = 0
    par_notion_questions: Counter = field(default_factory=Counter)
    par_notion_occurrences: Counter = field(default_factory=Counter)
    exercices: set = field(default_factory=set)

    @property
    def moyenne(self) -> float:
        return self.etiquettes / self.questions if self.questions else 0.0

    @property
    def couverture(self) -> float:
        """Part des questions au statut `ok`. À publier comme intervalle."""
        return 100 * self.statuts.get("ok", 0) / self.questions if self.questions else 0.0

    @property
    def notions_distinctes(self) -> int:
        return len(self.par_notion_questions)

    def part_questions(self, notion_id: str) -> float:
        return 100 * self.par_notion_questions[notion_id] / self.questions if self.questions else 0.0

    def part_occurrences(self, notion_id: str) -> float:
        return 100 * self.par_notion_occurrences[notion_id] / self.etiquettes if self.etiquettes else 0.0

    def cumul_occurrences(self, n: int) -> float:
        """Part des occurrences captée par les n notions les plus fréquentes.

        Se calcule sur le classement PAR QUESTIONS (c'est le « top n » publié),
        mais s'exprime en occurrences : c'est la mesure de concentration.
        """
        if not self.etiquettes:
            return 0.0
        tetes = [i for i, _ in self.par_notion_questions.most_common(n)]
        return 100 * sum(self.par_notion_occurrences[i] for i in tetes) / self.etiquettes


def agreger(questions: Iterable[dict[str, Any]]) -> Agregat:
    agregat = Agregat()
    for question in questions:
        etiquettes = question.get("etiquettes") or []
        agregat.questions += 1
        agregat.etiquettes += len(etiquettes)
        agregat.statuts[question.get("statut")] += 1
        agregat.exercices.add(question.get("exercice_id"))
        if question.get("statut") == "hors_referentiel":
            agregat.raisons_hors[question.get("raison_hors_referentiel")] += 1
        if question.get("figure_manquante_extraction"):
            agregat.figures_manquantes += 1
        if not etiquettes:
            agregat.sans_notion += 1
        for notion_id in {e["notion_id"] for e in etiquettes}:
            agregat.par_notion_questions[notion_id] += 1
        for etiquette in etiquettes:
            agregat.par_notion_occurrences[etiquette["notion_id"]] += 1
    return agregat


def ventiler(
    questions: Iterable[dict[str, Any]], cle: Callable[[dict[str, Any]], Any]
) -> dict[Any, Agregat]:
    paquets: dict[Any, list] = defaultdict(list)
    for question in questions:
        paquets[cle(question)].append(question)
    return {k: agreger(v) for k, v in paquets.items()}


def section_de(notion_id: str) -> str:
    """Les identifiants de notion sont `section.verbe_objet`."""
    return notion_id.split(".", 1)[0] if "." in notion_id else notion_id


def par_section(agregat: Agregat, notions: list[dict[str, Any]]) -> list[tuple]:
    """(section, notions utilisées, notions au total, occurrences, part).

    La part se lit en occurrences : une section peut concentrer beaucoup
    d'occurrences sur peu de notions — c'est précisément le cas à détecter.
    """
    total_par_section: Counter = Counter()
    for notion in notions:
        total_par_section[notion.get("section_id") or section_de(notion["id"])] += 1

    utilisees: Counter = Counter()
    occurrences: Counter = Counter()
    for notion_id, compte in agregat.par_notion_occurrences.items():
        section = section_de(notion_id)
        utilisees[section] += 1
        occurrences[section] += compte

    lignes = []
    for section, total in total_par_section.items():
        lignes.append(
            (
                section,
                utilisees.get(section, 0),
                total,
                occurrences.get(section, 0),
                100 * occurrences.get(section, 0) / agregat.etiquettes if agregat.etiquettes else 0.0,
            )
        )
    lignes.sort(key=lambda l: (-l[3], l[0]))
    return lignes


def notions_a_zero(
    agregat: Agregat, notions: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Notions jamais posées, groupées par section, sections pleines d'abord."""
    muettes: dict[str, list] = defaultdict(list)
    for notion in notions:
        if agregat.par_notion_questions.get(notion["id"], 0) == 0:
            muettes[notion.get("section_id") or section_de(notion["id"])].append(notion)
    return dict(muettes)


def croiser(
    questions: Iterable[dict[str, Any]], champ: str, notions_retenues: list[str]
) -> dict[str, Counter]:
    """notion → distribution des valeurs de `champ` sur ses occurrences."""
    retenues = set(notions_retenues)
    croisement: dict[str, Counter] = {n: Counter() for n in notions_retenues}
    for question in questions:
        valeur = question.get(champ)
        for etiquette in question.get("etiquettes") or []:
            if etiquette["notion_id"] in retenues:
                croisement[etiquette["notion_id"]][valeur] += 1
    return croisement


def comparer_couverture(
    agregat_a: Agregat, agregat_b: Agregat, notions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Ce qu'un corpus élargi change à la couverture du référentiel.

    La question à laquelle ça répond : une notion à zéro sur l'échantillon
    l'est-elle parce que le référentiel est condensé, ou parce que
    l'échantillon était trop petit ? Seule la seconde passe peut trancher, et
    seulement notion par notion — un compte global de « notions utilisées »
    monterait dans les deux cas.
    """
    tous = {n["id"]: (n.get("section_id") or section_de(n["id"])) for n in notions}
    en_a = {i for i in tous if agregat_a.par_notion_questions.get(i, 0)}
    en_b = {i for i in tous if agregat_b.par_notion_questions.get(i, 0)}

    sections_a = {s for i, s in tous.items() if i in en_a}
    sections_b = {s for i, s in tous.items() if i in en_b}
    return {
        "sorties_du_zero": sorted(en_b - en_a),
        "retombees_a_zero": sorted(en_a - en_b),
        "muettes_dans_les_deux": sorted(set(tous) - en_a - en_b),
        "sections_reveillees": sorted(sections_b - sections_a),
        "sections_muettes_dans_les_deux": sorted(set(tous.values()) - sections_a - sections_b),
        "notions": tous,
    }


def dispersion(passe_a: list[dict], passe_b: list[dict]) -> tuple[list[tuple], int]:
    """Classe les exercices par instabilité d'étiquetage entre deux passes.

    L'instabilité n'est pas du bruit de mesure : le modèle hésite exactement là
    où il n'a rien de bon à choisir. Sur les questions bien couvertes il est
    stable ; là où aucune notion ne convient vraiment, il bascule entre
    s'engager et renoncer. C'est donc un DÉTECTEUR DE TROUS, plus fin que le
    comptage des questions non couvertes : il pointe les zones où le référentiel
    est à la LIMITE plutôt qu'absent — celles à instruire d'abord.
    """
    def indexer(resultats: list[dict]) -> dict[str, tuple]:
        # Même désambiguïsation par rang que `aplatir` : sans elle, les 12
        # exercices à identifiant partagé s'écrasent et la dispersion porte sur
        # 326 exercices au lieu de 338.
        index, vus = {}, {}
        for r in resultats:
            brut = r["exercice_id"]
            rang = vus.get(brut, 0)
            vus[brut] = rang + 1
            cle = brut if rang == 0 else f"{brut}~{rang + 1}"
            index[cle] = (
                len(r["questions"]),
                sum(len(q["etiquettes"]) for q in r["questions"]),
                {e["notion_id"] for q in r["questions"] for e in q["etiquettes"]},
            )
        return index

    a, b = indexer(passe_a), indexer(passe_b)
    lignes = []
    for exercice in (e for e in b if e in a):
        (questions, na, sa), (_, nb, sb) = a[exercice], b[exercice]
        ecart = abs(na - nb)
        lignes.append(
            (
                ecart / max(1, questions),
                ecart,
                questions,
                na,
                nb,
                len(sa & sb) / (len(sa | sb) or 1),
                exercice,
            )
        )
    lignes.sort(reverse=True)
    return lignes, sum(l[1] for l in lignes)
