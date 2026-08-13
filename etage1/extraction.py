"""Segmentation d'un sujet en exercices, questions et solutions.

Trois principes, chacun tiré d'un défaut mesuré de l'extraction précédente :

1. **On segmente par exercice, via les titres markdown.** Jamais par expression
   régulière sur « Question N » : la numérotation redémarre à chaque exercice
   (`2024_InfoC` numérote même `Question I.4`, `Question II.1`…), si bien que
   le seul identifiant stable est le couple (exercice, numéro).

2. **Chaque caractère de la source est attribué à un segment.** Le ratio
   `caractères_extraits / caractères_source` est mesuré et rendu : c'est le
   garde-fou contre la perte silencieuse de 30 % du texte, dont on a vu
   qu'elle changeait des conclusions — deux disjonctions de cas de
   `2022_InfoU-exercices` étaient tombées avec les corrigés non extraits.

3. **Rien n'est traité avant la déduplication par empreinte de contenu.**
   `2024_InfoF` est identique octet pour octet à `2024_InfoC` ; le compter
   deux fois rendait vraie d'office toute règle « attesté dans deux fichiers ».
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Marqueurs. Volontairement peu nombreux et tous ancrés : un motif trop lâche
# rattacherait du texte à la mauvaise question, ce qui est pire que de le
# laisser dans le préambule de l'exercice.
# --------------------------------------------------------------------------- #

#: Un sujet peut faire courir PLUSIEURS séries de numérotation en parallèle :
#: `2024_TPAlgo` alterne « Question N » et « Question à développer pendant
#: l'oral N », chacune repartant de 1. Le qualificatif est donc capturé et
#: entre dans l'identifiant, sans quoi les deux séries se percutent — c'est ce
#: que faisait l'ancienne extraction, dont les libellés sortaient en double.
_QUALIF = r"(?P<qualif>(?:[^\d\n*#.]{1,40}?)\s)?"
_NUMERO = r"(?P<numero>[IVXLC]+(?:\.\d+)*|\d+(?:\.\d+)*)"

#: `**Question 12.**`, `#### Question 0 (Préliminaires).`, `**Question I.4.**`
RE_QUESTION = re.compile(
    r"^[ \t]{0,3}(?:<span[^>]*></span>)?[ \t]*(?:[-*+][ \t]+)?(?:#{1,6}\s*)?\*{0,2}Question\s+" + _QUALIF + _NUMERO +
    r"\s*(?P<glose>\([^)]{0,40}\))?\s*\.?\s*\*{0,2}\s*$",
    re.MULTILINE,
)
#: même chose mais en tête de ligne suivie du texte de la question. Le préfixe
#: de titre `#{1,6}` est admis ici aussi : `#### **Question 1.** Définir un
#: type…` n'était reconnu par aucun des deux motifs — ni par la forme ancrée
#: (du texte suit le numéro), ni par celle-ci (un dièse précède) — et devenait
#: un exercice à part entière dans `2024_Info-rapport`.
RE_QUESTION_INLINE = re.compile(
    r"^[ \t]{0,3}(?:<span[^>]*></span>)?[ \t]*(?:[-*+][ \t]+)?(?:#{1,6}[ \t]*)?\*{0,2}Question\s+" + _QUALIF + _NUMERO +
    r"\s*(?P<glose>\([^)]{0,40}\))?\s*\.?\*{0,2}\s*(?=\S)",
    re.MULTILINE,
)
RE_TITRE = re.compile(r"^(?P<diese>#{1,6})\s*(?P<titre>.+?)\s*$", re.MULTILINE)
RE_SOLUTION = re.compile(
    r"^[ \t]{0,3}(?:#{1,6}\s*)?\*{0,2}(?:Solution|Corrig[ée]|R[ée]ponse)\s*\*{0,2}\s*:?\s*\*{0,2}\s*$",
    re.MULTILINE | re.IGNORECASE,
)
#: `**Solution :** 1. On peut procéder…` — la solution démarre sur la ligne du
#: marqueur. C'est la forme majoritaire de `2024_Info-rapport`, et l'ignorer
#: laissait 46 solutions sur 54 non rattachées.
RE_SOLUTION_INLINE = re.compile(
    r"^[ \t]{0,3}(?:#{1,6}\s*)?\*{0,2}(?:Solution|Corrig[ée]|R[ée]ponse)\s*\*{0,2}\s*:\s*\*{0,2}\s*(?=\S)",
    re.MULTILINE | re.IGNORECASE,
)
#: image markdown, renvoi explicite à une figure, ou légende « Figure 2 »
RE_FIGURE = re.compile(
    r"!\[\]\([^)]*\)|\b(?:voir|cf\.?|dans|sur|à|de)\s+la\s+figure\b|\bfigure\s+\d+\b"
    r"|\bci-(?:dessus|dessous|contre)\b",
    re.IGNORECASE,
)
#: bruit de conversion PDF : ancres de page, numéros de page isolés
RE_BRUIT = re.compile(r"<span id=\"page-[^\"]*\"></span>|^\s*\d{1,3}\s*$", re.MULTILINE)

FILIERES = ("mpi", "mp_info", "non_marque")
#: Ordre d'essai = ordre de priorité. Les motifs exigent un CONTEXTE de filière
#: (« banque », « filières », « épreuve ») : un `\bMPI\b` nu classait en MPI les
#: quatre fichiers, dont deux « Banque MP inter-ENS » qui n'en sont pas.
RE_FILIERE = (
    (
        "mpi",
        re.compile(
            # « concours MPI » est volontairement absent : la phrase
            # « les candidats … des concours MPI et Informatique » classait
            # 2022_InfoLCR-rapport en MPI alors que son titre dit « Banque MP
            # inter-ENS ». Seuls les contextes de BANQUE ou de FILIÈRE valent.
            r"BANQUES?\s+MPI\b|fili[èe]res?\s+MP\s*[-et]+\s*MPI|banques?\s+MP\s+et\s+MPI"
            r"|fili[èe]re\s+MPI\b",
            re.IGNORECASE,
        ),
    ),
    (
        "mp_info",
        re.compile(
            r"banques?\s+MP\s+inter-ENS|fili[èe]re\s+MP\b|MP\s+option\s+info", re.IGNORECASE
        ),
    ),
)


def _empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


def _pente(texte: str) -> str:
    """Identifiant lisible et stable tiré d'un titre."""
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "-", sans_accent.lower()).strip("-")[:48] or "sans-titre"


# --------------------------------------------------------------------------- #


@dataclass
class Question:
    id: str
    numero: str
    texte: str
    solution: str | None = None
    figure_manquante: bool = False
    ligne: int = 0

    def caracteres(self) -> int:
        return len(self.texte) + len(self.solution or "")


@dataclass
class Exercice:
    id: str
    titre: str
    niveau: int
    filiere: str
    preambule: str = ""
    corrige_non_attribue: str = ""
    questions: list[Question] = field(default_factory=list)
    ligne: int = 0

    def caracteres(self) -> int:
        return (
            len(self.preambule)
            + len(self.corrige_non_attribue)
            + sum(q.caracteres() for q in self.questions)
        )


@dataclass
class Document:
    fichier: str
    empreinte: str
    filiere: str
    niveau_exercice: int
    entete: str = ""
    exercices: list[Exercice] = field(default_factory=list)
    journal: list[str] = field(default_factory=list)
    caracteres_source: int = 0
    caracteres_bruit: int = 0
    #: figé juste après le découpage, AVANT tout filtrage par filière : le
    #: ratio mesure la fidélité de l'extraction, pas l'effet d'un choix
    #: éditorial ultérieur, sans quoi écarter une filière le ferait chuter.
    ratio_extraction: float = 0.0

    @property
    def questions(self) -> list[Question]:
        return [q for e in self.exercices for q in e.questions]

    @property
    def caracteres_extraits(self) -> int:
        return len(self.entete) + sum(e.caracteres() for e in self.exercices)

    @property
    def ratio(self) -> float:
        """Part du texte source qui se retrouve dans un champ de sortie.

        Le bruit de conversion PDF explicitement retiré (ancres de page,
        numéros de page isolés) est sorti du dénominateur : le compter ferait
        échouer un extracteur qui, lui, ne perd rien.
        """
        return self.ratio_extraction

    def resume(self) -> dict[str, Any]:
        return {
            "fichier": self.fichier,
            "filiere": self.filiere,
            "exercices": len(self.exercices),
            "questions": len(self.questions),
            "solutions_rattachees": sum(1 for q in self.questions if q.solution),
            "figures_manquantes": sum(1 for q in self.questions if q.figure_manquante),
            "ratio_texte_conserve": self.ratio,
        }


# --------------------------------------------------------------------------- #


def _detecter_filiere(texte: str) -> str:
    for nom, motif in RE_FILIERE:
        if motif.search(texte):
            return nom
    return "non_marque"


def _titres(texte: str) -> list[tuple[int, int, str, int, int]]:
    """(niveau, position, titre, début_ligne, fin_ligne) pour chaque titre."""
    resultat = []
    for m in RE_TITRE.finditer(texte):
        titre = m.group("titre").strip()
        resultat.append((len(m.group("diese")), m.start(), titre, m.start(), m.end()))
    return resultat


def _positions_questions(texte: str) -> list[tuple[int, int, str]]:
    """(début, fin_du_marqueur, numéro qualifié), sans doublon de position.

    Le numéro rendu porte sa série : `12` pour « Question 12 », `oral.3` pour
    « Question à développer pendant l'oral 3 ».
    """
    trouvees: dict[int, tuple[int, str]] = {}
    for motif in (RE_QUESTION, RE_QUESTION_INLINE):
        for m in motif.finditer(texte):
            if m.start() in trouvees:
                continue
            qualif = (m.group("qualif") or "").strip()
            # Le DERNIER mot du qualificatif est le terme discriminant :
            # « à développer pendant l'oral » → `oral`, lisible dans les
            # identifiants, là où tronquer le slug entier donnait `adevelopperp`.
            # Le test sur `qualif` doit précéder l'appel : `_pente("")` retombe
            # sur son défaut « sans-titre » et fabriquait une série `titre`.
            mots = (
                [x for x in re.split(r"[^\w]+", _pente(qualif).replace("-", " ")) if x]
                if qualif
                else []
            )
            serie = mots[-1][:10] if mots else ""
            trouvees[m.start()] = (m.end(), f"{serie}.{m.group('numero')}" if serie else m.group("numero"))
    return sorted((d, f, n) for d, (f, n) in trouvees.items())


def _choisir_niveau_exercice(
    texte: str, titres, positions_q, positions_s
) -> tuple[int, list[str]]:
    """Quel niveau de titre découpe le document en exercices ?

    Un titre qui est lui-même un marqueur de question ou de solution ne peut
    pas délimiter un exercice. Parmi les niveaux restants, on retient celui qui
    place le plus de questions dans des groupes nommés — c'est-à-dire celui qui
    correspond à l'unité que le sujet lui-même appelle un exercice.
    """
    journal = []
    debuts_q = {d for d, _, _ in positions_q}
    debuts_s = {d for d, _ in positions_s}
    candidats = [
        (niveau, pos, titre)
        for niveau, pos, titre, _, _ in titres
        if pos not in debuts_q and pos not in debuts_s
    ]
    meilleur, meilleur_score = 1, (-1, 0)
    for niveau in sorted({n for n, _, _ in candidats}):
        bornes = [p for n, p, _ in candidats if n == niveau]
        groupes_avec_q, groupes_vides = 0, 0
        for i, debut in enumerate(bornes):
            fin = bornes[i + 1] if i + 1 < len(bornes) else len(texte)
            if any(debut <= d < fin for d in debuts_q):
                groupes_avec_q += 1
            else:
                groupes_vides += 1
        score = (groupes_avec_q, -groupes_vides)
        journal.append(
            f"niveau {niveau} : {len(bornes)} titre(s), {groupes_avec_q} avec question(s), "
            f"{groupes_vides} sans"
        )
        if score > meilleur_score:
            meilleur, meilleur_score = niveau, score
    journal.append(f"niveau d'exercice retenu : {meilleur}")
    return meilleur, journal


_ROMAINS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _cle_numero(numero: str) -> tuple[int, ...] | None:
    """Rend un numéro comparable, ou None s'il n'est pas ordonnable."""
    corps = numero.split(".", 1)[-1] if numero[:1].isalpha() and "." in numero else numero
    morceaux = []
    for morceau in corps.split("."):
        if morceau.isdigit():
            morceaux.append(int(morceau))
        elif morceau and all(c in _ROMAINS for c in morceau.upper()):
            valeur, precedent = 0, 0
            for c in reversed(morceau.upper()):
                v = _ROMAINS[c]
                valeur += -v if v < precedent else v
                precedent = max(precedent, v)
            morceaux.append(valeur)
        else:
            return None
    return tuple(morceaux)


def _serie(numero: str) -> str:
    return numero.split(".", 1)[0] if numero[:1].isalpha() else ""


def _est_romain(marque: str) -> bool:
    return bool(marque) and all(c in _ROMAINS for c in marque.upper())


def _partie(numero: str) -> str:
    """Préfixe de PARTIE d'un numéro hiérarchique — romain OU arabe.

    `II.3` → `II`, `2.3` → `2`, `Q4` → `` (pas de hiérarchie, donc pas de
    partie). Le cas arabe manquait : quatre sujets `InfoF` numérotent leurs
    parties en chiffres et mettent leurs titres à des niveaux markdown
    incohérents (2022 : partie 1 en `###`, 2 et 3 en `##`, 4 en `#`). Le niveau
    retenu tombait alors sur les sous-sections, et la partie suivante était
    avalée par la précédente — `2020_InfoF` sortait « Partie I » avec les sept
    questions de la partie II, et un ratio de conservation de 1,0021, au-dessus
    de 1, c'est-à-dire du double comptage.

    L'argument est le même que pour les romains : quand la question s'annonce
    elle-même « 2.3 », ce préfixe est un signal plus fiable que la mise en page.
    """
    serie = _serie(numero)
    if serie:
        return serie if _est_romain(serie) else ""
    tete = numero.split(".", 1)[0] if "." in numero else ""
    return tete if tete.isdigit() else ""


def _bornes_par_reprise(texte, candidats, bornes_base, positions_q) -> list[tuple[int, str]]:
    """Ajoute une frontière d'exercice là où la numérotation REPART.

    C'est le critère d'identité lui-même retourné en règle de découpage : si le
    numéro qui suit un sous-titre est inférieur à celui qui le précède, les
    deux ne relèvent pas du même exercice. Sans cela, « Logique Temporelle
    Linéaire » de `2022_InfoLCR-rapport` sortait à 25 questions en agrégeant
    trois exercices dont la numérotation repartait de 1 à chaque fois.
    """
    niveaux_base = {p for p, _ in bornes_base}
    sup = [(pos, titre) for niveau, pos, titre in candidats if pos not in niveaux_base]
    ajouts = []
    for pos, titre in sup:
        avant = [(d, n) for d, _, n in positions_q if d < pos]
        apres = [(d, n) for d, _, n in positions_q if d > pos]
        if not avant or not apres:
            continue
        precedent, suivant = avant[-1][1], apres[0][1]
        sp, ss = _serie(precedent), _serie(suivant)
        if sp != ss:
            # Changement de PARTIE (`I.5` → `II.1`) : c'est une frontière, même
            # si le numéro ne baisse pas. `2024_InfoC` met ses parties en titre
            # de niveau 1 et ses sous-sections en niveau 3 ; sans cette règle,
            # la question II.3 était rattachée à « Notations et définitions ».
            # Un changement de série de QUALIFICATIF (« Question N » →
            # « Question à développer pendant l'oral N ») n'en est pas une :
            # les deux séries s'entrelacent dans `2024_TPAlgo`.
            if _est_romain(sp) and _est_romain(ss):
                ajouts.append((pos, titre))
            continue
        a, b = _cle_numero(precedent), _cle_numero(suivant)
        # Changement de partie ARABE (`3.7` → `4.1`) : le numéro monte, donc la
        # règle de reprise ne voit rien, et pourtant la frontière est là. On
        # n'ouvre ce cas que sur une numérotation franchement hiérarchique des
        # deux côtés, pour ne pas couper une série plate `1, 2, 3` à chaque
        # dizaine.
        if _partie(precedent) and _partie(suivant) and _partie(precedent) != _partie(suivant):
            ajouts.append((pos, titre))
            continue
        if a and b and b <= a:
            ajouts.append((pos, titre))
    return ajouts


def _positions_solutions(texte: str) -> list[tuple[int, int]]:
    trouvees: dict[int, int] = {}
    for motif in (RE_SOLUTION, RE_SOLUTION_INLINE):
        for m in motif.finditer(texte):
            trouvees.setdefault(m.start(), m.end())
    return sorted(trouvees.items())


def _nettoyer(bloc: str) -> str:
    return "\n".join(l.rstrip() for l in bloc.strip().splitlines()).strip()


def extraire(chemin: Path, empreintes_vues: dict[str, str] | None = None) -> Document | None:
    """Extrait un fichier. Rend None si son contenu a déjà été vu."""
    source = chemin.read_text(encoding="utf-8")
    empreinte = _empreinte(source)
    if empreintes_vues is not None:
        if empreinte in empreintes_vues:
            return None
        empreintes_vues[empreinte] = chemin.name

    bruit = sum(len(m.group(0)) for m in RE_BRUIT.finditer(source))
    titres = _titres(source)
    positions_q = _positions_questions(source)
    positions_s = _positions_solutions(source)
    niveau, journal_niveau = _choisir_niveau_exercice(source, titres, positions_q, positions_s)

    document = Document(
        fichier=chemin.name,
        empreinte=empreinte,
        filiere=_detecter_filiere(source[:4000]),
        niveau_exercice=niveau,
        caracteres_source=len(source),
        caracteres_bruit=bruit,
    )
    document.journal.extend(journal_niveau)

    debuts_q = {d for d, _, _ in positions_q}
    debuts_s = {d for d, _ in positions_s}
    candidats = [
        (n, pos, titre)
        for n, pos, titre, _, _ in titres
        if pos not in debuts_q and pos not in debuts_s
    ]
    bornes = [(pos, titre) for n, pos, titre in candidats if n == niveau]
    reprises = _bornes_par_reprise(source, candidats, bornes, positions_q)
    if reprises:
        document.journal.append(
            f"{len(reprises)} frontière(s) ajoutée(s) sur reprise de numérotation : "
            + ", ".join(t[:28] for _, t in reprises)
        )
        bornes = sorted(set(bornes + reprises))
    if not bornes:
        bornes = [(0, chemin.stem)]

    # Une question placée AVANT le premier titre d'exercice tombait dans
    # l'en-tête, d'où rien ne la relit : 34 questions de 5 sujets
    # disparaissaient — `2021_InfoA` en perdait 11 sur 27, `2022_InfoC-0` 10 sur
    # 25. Le ratio de conservation n'en disait rien, PARCE QUE l'en-tête compte
    # dans les caractères extraits : le texte était conservé, seule son
    # attribution était perdue. C'est le même défaut que partout ailleurs ici —
    # vrai au fichier, faux à l'unité — et il demande son propre garde-fou,
    # que porte désormais `_verifier_conservation`.
    if debuts_q and min(debuts_q) < bornes[0][0]:
        premiere = min(debuts_q)
        avant = [(pos, titre) for _, pos, titre in candidats if pos <= premiere]
        ouverture = avant[-1] if avant else (0, chemin.stem)
        orphelines = sum(1 for d in debuts_q if d < bornes[0][0])
        document.journal.append(
            f"borne ouverte en tête sur « {ouverture[1][:34]} » : {orphelines} "
            "question(s) précédaient le premier exercice"
        )
        bornes = sorted(set(bornes + [ouverture]))

    document.entete = _nettoyer(source[: bornes[0][0]])
    base = chemin.stem

    for i, (debut, titre) in enumerate(bornes):
        fin = bornes[i + 1][0] if i + 1 < len(bornes) else len(source)
        bloc = source[debut:fin]
        # La filière d'un exercice ne se lit que dans son TITRE : la chercher
        # dans son corps ferait basculer tout exercice citant « filière MP » au
        # détour d'une phrase. À défaut de marque, l'exercice hérite du fichier.
        exercice = Exercice(
            id=f"{base}/{_pente(titre)}",
            titre=_nettoyer(titre),
            niveau=niveau,
            filiere=_detecter_filiere(titre),
            ligne=source[:debut].count("\n") + 1,
        )
        if exercice.filiere == "non_marque":
            exercice.filiere = document.filiere
        _decouper_exercice(source, debut, fin, exercice, positions_q, positions_s)
        document.exercices.append(exercice)

    _regrouper_par_partie(document)
    # L'ordre compte : un en-tête d'annexe ne porte aucune question, il serait
    # absorbé — et son marqueur de filière perdu — si l'absorption passait la
    # première.
    _propager_filiere(document)
    _absorber_groupes_vides(document)
    _verifier_conservation(document, source)
    return document


def _propager_filiere(document: Document) -> None:
    """Un en-tête d'annexe vaut pour tout ce qui le suit, jusqu'au rang égal.

    La filière du fichier n'est qu'une valeur par défaut, valable avant le
    premier marqueur. Sans propagation, les sujets de l'annexe « filière MP »
    de `2024_Info-rapport` héritaient du `mpi` du fichier et entraient dans le
    corpus alors que la consigne est MPI en priorité, MP option info à défaut :
    du contenu qui n'aurait pas dû être là, mêlé au contenu légitime, sans
    qu'aucun indicateur ne le signale.
    """
    courante = document.filiere
    niveau_marque: int | None = None
    bascules: list[tuple[str, str, str]] = []

    for exercice in document.exercices:
        marque = _detecter_filiere(exercice.titre)
        if marque != "non_marque":
            courante, niveau_marque = marque, exercice.niveau
            continue
        if niveau_marque is not None and exercice.niveau < niveau_marque:
            # titre de rang SUPÉRIEUR : la portée de l'annexe s'arrête là
            courante, niveau_marque = document.filiere, None
        if exercice.filiere != courante:
            bascules.append((exercice.id, exercice.filiere, courante))
            exercice.filiere = courante

    if bascules:
        document.journal.append(
            f"propagation de filière : {len(bascules)} exercice(s) rebasculé(s)"
        )
        for identifiant, avant, apres in bascules:
            document.journal.append(f"    {identifiant} : {avant} -> {apres}")


def _absorber_groupes_vides(document: Document) -> None:
    """Un groupe sans question n'est pas un exercice.

    En tête de document, c'est l'en-tête de l'épreuve : il rejoint `entete`.
    Ailleurs, c'est du matériel introductif : il rejoint le préambule du groupe
    SUIVANT — `2024_TPAlgo` enchaîne deux sujets dans un même fichier et refait
    un bloc « ATTENTION ! / Important. / Préliminaires » avant le second.

    Aucun caractère ne quitte le document : le texte change de champ, pas de
    fichier, et le ratio de conservation est inchangé.
    """
    premier = next((i for i, e in enumerate(document.exercices) if e.questions), None)
    if premier is None:
        return

    for exercice in document.exercices[:premier]:
        for morceau in (exercice.preambule, exercice.corrige_non_attribue):
            if morceau:
                document.entete += ("\n\n" if document.entete else "") + morceau

    resultat: list[Exercice] = []
    en_attente = ""
    for exercice in document.exercices[premier:]:
        if not exercice.questions:
            for morceau in (exercice.preambule, exercice.corrige_non_attribue):
                if morceau:
                    en_attente += ("\n\n" if en_attente else "") + morceau
            continue
        if en_attente:
            exercice.preambule = (
                en_attente + ("\n\n" + exercice.preambule if exercice.preambule else "")
            )
            en_attente = ""
        resultat.append(exercice)
    if en_attente:
        resultat[-1].corrige_non_attribue += (
            "\n\n" if resultat[-1].corrige_non_attribue else ""
        ) + en_attente

    absorbes = len(document.exercices) - len(resultat)
    if absorbes:
        document.journal.append(
            f"{absorbes} groupe(s) sans question absorbé(s) "
            f"({premier} en en-tête, {absorbes - premier} en matériel introductif)"
        )
    document.exercices = resultat


def _regrouper_par_partie(document: Document) -> None:
    """Regroupe par préfixe de partie quand les questions en portent un.

    `2024_InfoC` titre ses parties I, II, III et V en niveau 1, mais IV et VI
    en niveau 3 : aucun choix de niveau de titre ne peut les découper
    correctement. Quand la question s'annonce elle-même « II.3 », ce préfixe
    est un signal plus fiable que la mise en forme, et c'est lui qui décide.
    Les titres markdown ne servent plus qu'à nommer les groupes.
    """
    questions = document.questions
    if not questions:
        return
    avec_partie = [q for q in questions if _partie(q.numero)]
    if len(avec_partie) < 0.8 * len(questions):
        return

    groupes: list[Exercice] = []
    partie_courante: str | None = None
    for exercice in document.exercices:
        if not exercice.questions:
            # exercice sans question : son texte rejoint le groupe en cours,
            # ou ouvre le suivant s'il n'y en a pas encore. Rien n'est jeté.
            cible = groupes[-1] if groupes else None
            if cible is None:
                groupes.append(
                    Exercice(
                        id=exercice.id, titre=exercice.titre, niveau=exercice.niveau,
                        filiere=exercice.filiere, preambule=exercice.preambule,
                        corrige_non_attribue=exercice.corrige_non_attribue, ligne=exercice.ligne,
                    )
                )
            else:
                cible.preambule += ("\n\n" if cible.preambule else "") + exercice.preambule
                cible.corrige_non_attribue += exercice.corrige_non_attribue
            continue

        premiere = _partie(exercice.questions[0].numero)
        preambule_place = False
        for question in exercice.questions:
            partie = _partie(question.numero)
            if partie != partie_courante or not groupes:
                titre = exercice.titre if partie == premiere else f"Partie {partie}"
                groupes.append(
                    Exercice(
                        id=f"{document.fichier.rsplit('.', 1)[0]}/partie-{_pente(partie) or 'unique'}",
                        titre=titre, niveau=exercice.niveau, filiere=exercice.filiere,
                        ligne=question.ligne,
                    )
                )
                partie_courante = partie
            if not preambule_place:
                groupes[-1].preambule += (
                    "\n\n" if groupes[-1].preambule else ""
                ) + exercice.preambule
                preambule_place = True
            question.id = f"{groupes[-1].id}#Q{question.numero}"
            groupes[-1].questions.append(question)
        groupes[-1].corrige_non_attribue += exercice.corrige_non_attribue

    document.exercices = groupes
    document.journal.append(
        f"regroupement par préfixe de partie : {len(groupes)} exercice(s)"
    )


def _decouper_exercice(
    source: str,
    debut: int,
    fin: int,
    exercice: Exercice,
    positions_q,
    positions_s,
) -> None:
    """Découpe un exercice en préambule / questions / solutions.

    La solution qui suit une question lui est rattachée ; celle qui n'en suit
    aucune (un « Corrigé » global couvrant tout l'exercice) est conservée dans
    `corrige_non_attribue` plutôt que jetée, puis redécoupée si elle porte
    elle-même des marqueurs de question.
    """
    q_locales = [(d, f, n) for d, f, n in positions_q if debut <= d < fin]
    s_locales = [(d, f) for d, f in positions_s if debut <= d < fin]

    premier = min(
        [d for d, _, _ in q_locales] + [d for d, _ in s_locales] + [fin]
    )
    exercice.preambule = _nettoyer(source[debut:premier])

    # Bornes de tous les segments à l'intérieur de l'exercice, dans l'ordre.
    jalons = sorted(
        [(d, f, "q", n) for d, f, n in q_locales] + [(d, f, "s", None) for d, f in s_locales]
    )
    par_numero: dict[str, Question] = {}
    vus: dict[str, int] = {}
    derniere_question: Question | None = None
    apres_solution = False

    for i, (d, f, genre, numero) in enumerate(jalons):
        suivant = jalons[i + 1][0] if i + 1 < len(jalons) else fin
        contenu = _nettoyer(source[f:suivant])

        if genre == "q" and numero in par_numero and apres_solution:
            # Le numéro a déjà été posé plus haut ET on a franchi un marqueur de
            # corrigé : ce n'est pas une nouvelle question, c'est la section du
            # corrigé qui la traite. Sans cette règle, `2022_InfoU-exercices`
            # comptait 196 questions pour 63 réelles, chaque corrigé rejouant
            # la numérotation de son exercice.
            cible = par_numero[numero]
            cible.solution = (
                contenu if cible.solution is None else f"{cible.solution}\n\n{contenu}"
            )
            derniere_question = cible
            continue

        if genre == "q":
            # l'identité est le couple (exercice, numéro) — la numérotation
            # redémarre à chaque exercice, elle n'est unique que localement.
            # Le compteur doit être par NUMÉRO : indexer sur la taille de la
            # table produisait deux fois le même suffixe à la troisième
            # occurrence, donc deux questions de même identifiant.
            vus[numero] = vus.get(numero, 0) + 1
            suffixe = "" if vus[numero] == 1 else f"bis{vus[numero]}"
            question = Question(
                id=f"{exercice.id}#Q{numero}{suffixe}",
                numero=numero,
                texte=contenu,
                figure_manquante=bool(RE_FIGURE.search(contenu)),
                ligne=source[:d].count("\n") + 1,
            )
            exercice.questions.append(question)
            par_numero.setdefault(numero, question)
            derniere_question = question
        else:
            apres_solution = True
            if derniere_question is not None and derniere_question.solution is None:
                derniere_question.solution = contenu
            elif contenu:
                exercice.corrige_non_attribue += (
                    "\n\n" if exercice.corrige_non_attribue else ""
                ) + contenu

    _redecouper_corrige(exercice)


def _redecouper_corrige(exercice: Exercice) -> None:
    """Un « Corrigé » global porte souvent les numéros de question en interne."""
    if not exercice.corrige_non_attribue or not exercice.questions:
        return
    bloc = exercice.corrige_non_attribue
    marques = _positions_questions(bloc)
    if not marques:
        return
    par_numero = {q.numero: q for q in exercice.questions}
    reste, attribue = [], 0
    tete = bloc[: marques[0][0]].strip()
    if tete:
        reste.append(tete)
    for i, (d, f, numero) in enumerate(marques):
        suivant = marques[i + 1][0] if i + 1 < len(marques) else len(bloc)
        morceau = _nettoyer(bloc[f:suivant])
        question = par_numero.get(numero)
        if question is not None and question.solution is None and morceau:
            question.solution = morceau
            attribue += 1
        elif morceau:
            reste.append(morceau)
    exercice.corrige_non_attribue = "\n\n".join(reste)


def _verifier_conservation(document: Document, source: str) -> None:
    utile = document.caracteres_source - document.caracteres_bruit
    document.ratio_extraction = (
        round(document.caracteres_extraits / utile, 4) if utile else 0.0
    )
    perdu = utile - document.caracteres_extraits
    document.journal.append(
        f"conservation : {document.caracteres_extraits} / {utile} caractères utiles "
        f"(ratio {document.ratio_extraction}) — {perdu} non repris"
    )

    # Le ratio est une mesure de TEXTE, et il est aveugle à l'ATTRIBUTION : du
    # texte rangé dans l'en-tête compte comme conservé alors qu'aucune question
    # ne le porte. Cinq sujets perdaient ainsi 34 questions à ratio inchangé.
    # On compte donc aussi les marqueurs, qui est la seule mesure à l'unité.
    marques = {d for d, _, _ in _positions_questions(source)}
    ecart = len(marques) - len(document.questions)
    if ecart:
        document.journal.append(
            f"ATTRIBUTION : {len(marques)} marqueur(s) de question dans la source, "
            f"{len(document.questions)} question(s) rattachée(s) — écart {ecart:+d}"
        )
    if document.ratio_extraction > 1.0:
        # Impossible pour une mesure de conservation : du texte est compté deux
        # fois. Le signaler plutôt que de le laisser passer pour un arrondi.
        document.journal.append(
            f"ANOMALIE : ratio {document.ratio_extraction} > 1 — "
            f"{-perdu} caractère(s) comptés deux fois"
        )


# --------------------------------------------------------------------------- #


def extraire_corpus(
    chemins: Iterable[Path], filtrer_filiere: bool = False
) -> tuple[list[Document], list[str]]:
    """Extrait plusieurs fichiers, en dédupliquant AVANT tout traitement.

    **La filière est un ATTRIBUT, pas un filtre.** Aucun exercice n'est écarté
    pour sa filière : le programme d'informatique est largement commun aux deux
    voies, et les sujets MP option info sont des épreuves d'informatique des
    ENS, pas du hors-sujet. Conserver l'attribut permet de dire « cette notion
    tombe surtout en MP option info, rarement en MPI » — information que le
    filtrage détruirait, en décidant à la place du candidat. Signaler plutôt
    qu'exclure.

    Appliqué fichier par fichier, le filtre était de surcroît incohérent : il
    écartait du MP là où du MPI coexiste, et le gardait là où il est seul.
    `filtrer_filiere` reste disponible pour une étude ciblée, jamais par défaut.
    """
    empreintes: dict[str, str] = {}
    documents, journal = [], []
    for chemin in chemins:
        document = extraire(chemin, empreintes)
        if document is None:
            journal.append(
                f"{chemin.name} : ÉCARTÉ — doublon de contenu de "
                f"{empreintes[_empreinte(chemin.read_text(encoding='utf-8'))]}"
            )
            continue
        if filtrer_filiere:
            presentes = {e.filiere for e in document.exercices}
            for rang in FILIERES:
                if rang in presentes:
                    meilleure = rang
                    break
            else:
                meilleure = "non_marque"
            gardes = []
            for exercice in document.exercices:
                if exercice.filiere == meilleure:
                    gardes.append(exercice)
                else:
                    journal.append(
                        f"{document.fichier} : exercice « {exercice.titre[:40]} » écarté — "
                        f"filière {exercice.filiere} < {meilleure} retenue pour ce fichier"
                    )
            document.exercices = gardes
            document.filiere = meilleure
        documents.append(document)
        journal.extend(f"{document.fichier} : {ligne}" for ligne in document.journal)
    return documents, journal
