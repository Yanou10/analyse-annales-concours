"""Segmentation déterministe du programme officiel en unités candidates.

Aucun appel LLM ici. La sortie est auditable ligne à ligne : chaque unité porte
sa plage de lignes source, de sorte qu'une erreur de reconstruction se voit.

Deux propriétés du corpus dictent l'implémentation :

1.  L'unité de décision est la LIGNE LOGIQUE de tableau, pas la ligne physique.
    Une entrée s'étale sur plusieurs lignes markdown, et une nouvelle entrée
    commence quand la cellule « Notions » démarre par une majuscule ET que la
    cellule précédente se terminait par une ponctuation forte.

2.  Les colonnes « Notions » et « Commentaires » doivent voyager ENSEMBLE.
    L'action à admettre se trouve très souvent dans le commentaire alors que la
    colonne Notions n'est qu'une liste de termes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

RE_SPAN = re.compile(r"<span[^>]*>|</span>")
RE_TITRE = re.compile(r"^(?P<niveau>#{1,6})\s+(?P<titre>.*?)\s*$")
RE_NUMERO = re.compile(r"^(?P<num>\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)\s+(?P<reste>.+)$")
RE_SEMESTRE = re.compile(r"\bS(?:1|2|3-4)\b")
RE_MISE_EN_OEUVRE = re.compile(r"mise\s+en\s+(?:œ|oe)uvre", re.IGNORECASE)
RE_SEPARATEUR = re.compile(r"^\|[\s:|-]+\|$")
RE_PUCE = re.compile(r"^\s*[-*•]\s+(?P<texte>.+)$")
RE_IMAGE = re.compile(r"!\[\]\([^)]*\)")


def _nettoyer(texte: str) -> str:
    texte = RE_SPAN.sub("", texte)
    texte = RE_IMAGE.sub("", texte)
    texte = texte.replace("<br>", " ")
    texte = texte.replace("**", "").replace("*", "")
    texte = re.sub(r"[ \t]+", " ", texte)
    return texte.strip()


@dataclass(frozen=True)
class Section:
    numero: str | None
    titre: str
    niveau: int
    ligne: int
    chemin: tuple[str, ...]

    @property
    def id(self) -> str:
        return self.numero or self.titre.lower().replace(" ", "-")[:40]


@dataclass(frozen=True)
class Unite:
    """Une unité soumise au critère d'admission."""

    id: str
    section: Section
    genre: str  # table | mise_en_oeuvre | annexe | prose
    notions: str  # colonne gauche (vide hors tableau)
    commentaires: str  # colonne droite (vide hors tableau)
    texte: str  # contenu pour les genres non tabulaires
    ligne_debut: int
    ligne_fin: int
    semestre: str | None

    def rendu(self) -> str:
        """Représentation envoyée au modèle. Explicite sur la provenance."""
        entete = f"[{self.id}] ({self.genre}"
        if self.semestre:
            entete += f", {self.semestre}"
        entete += f", lignes {self.ligne_debut}-{self.ligne_fin})"
        if self.genre == "table":
            return (
                f"{entete}\n"
                f"  Notions      : {self.notions or '(vide)'}\n"
                f"  Commentaires : {self.commentaires or '(vide)'}"
            )
        return f"{entete}\n  {self.texte}"


@dataclass
class Rapport:
    """Trace d'audit de la segmentation."""

    unites: list[Unite] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    ecartees: list[tuple[str, str, int]] = field(default_factory=list)  # (id, motif, ligne)

    def ecarter(self, identifiant: str, motif: str, ligne: int) -> None:
        self.ecartees.append((identifiant, motif, ligne))


def _semestre(texte: str) -> str | None:
    trouves = RE_SEMESTRE.findall(texte)
    if not trouves:
        return None
    # RE_SEMESTRE ne capture pas le groupe complet : on relit par finditer.
    marques = [m.group(0) for m in RE_SEMESTRE.finditer(texte)]
    return marques[-1] if marques else None


def _analyser_titre(
    ligne: str,
    numero_ligne: int,
    pile: list[Section],
    registre: dict[str, "Section"],
) -> Section:
    m = RE_TITRE.match(ligne)
    assert m is not None
    niveau = len(m.group("niveau"))
    titre = _nettoyer(m.group("titre"))
    numero = None
    mn = RE_NUMERO.match(titre)
    if mn:
        numero = mn.group("num")
        titre = mn.group("reste")
    titre = RE_SEMESTRE.sub("", titre)
    # Le retrait des marqueurs de semestre laisse « ( ) » quand ils étaient
    # entre parenthèses : « Bases de données (S2) » -> « Bases de données () ».
    titre = re.sub(r"\(\s*\)", "", titre)
    titre = re.sub(r"\s+", " ", titre).strip(" .)(")

    # Les niveaux de titre sont INCOHÉRENTS dans ce markdown extrait de PDF
    # (« # 4 », « # 4.3 », « ### 4.5 » cohabitent). Reconstruire le chemin
    # depuis le niveau donne des parents faux ; la numérotation, elle, est
    # fiable. On ne retombe sur la pile que pour les titres non numérotés.
    if numero and "." in numero:
        parent = registre.get(numero.rsplit(".", 1)[0])
        chemin = (parent.chemin if parent else ()) + (titre,)
    elif numero:
        chemin = (titre,)
    else:
        chemin = tuple(s.titre for s in pile if s.niveau < niveau) + (titre,)

    return Section(
        numero=numero, titre=titre, niveau=niveau, ligne=numero_ligne, chemin=chemin
    )


def _cellules(ligne: str) -> list[str]:
    brut = ligne.strip()
    if brut.startswith("|"):
        brut = brut[1:]
    if brut.endswith("|"):
        brut = brut[:-1]
    return [_nettoyer(c) for c in brut.split("|")]


def _ouvre_cellule(cellule: str, precedente: str) -> bool:
    """Vrai si `cellule` semble ouvrir une nouvelle entrée dans sa colonne."""
    if not cellule or not cellule[0].isupper():
        return False
    if not precedente:
        return True
    # « … solution exacte. S2 » : le marqueur de semestre suit la ponctuation
    # finale et masquerait la fin d'entrée si on ne le retirait pas.
    fin = RE_SEMESTRE.sub("", precedente).rstrip()
    return fin.endswith((".", ":", ";", "!", "?"))


def _commence_entree(
    gauche: str, precedente_gauche: str, droite: str, precedente_droite: str
) -> bool:
    """Vrai si la ligne physique ouvre une nouvelle ligne LOGIQUE de tableau.

    Les deux colonnes doivent être d'accord. Sur la seule colonne gauche,
    §3.4 se découpe en trois entrées (« Graphe orienté… », « Sommet… »,
    « Degré… ») alors que la colonne droite y déroule une phrase unique :
    c'est une seule entrée. Symétriquement, §4.3 fusionne trois entrées si
    l'on ignore que la colonne droite, elle, repart bien à la majuscule.
    """
    if not _ouvre_cellule(gauche, precedente_gauche):
        return False
    if not droite:
        return True
    return _ouvre_cellule(droite, precedente_droite)


def _fusionner(fragments: list[str]) -> str:
    """Recolle les fragments d'une cellule étalée sur plusieurs lignes physiques.

    Limite connue et assumée : le corpus coupe parfois AU MILIEU d'un mot
    (« Paradigme im » + « pératif »). On recolle avec une espace plutôt que de
    deviner, car une heuristique de recollement sans lexique produit autant
    d'erreurs qu'elle en corrige. Le modèle lit sans peine à travers l'artefact ;
    `etage0 segmenter --detail` permet de le vérifier à l'œil.
    """
    return " ".join(f for f in (x.strip() for x in fragments) if f)


class _TableauEnCours:
    def __init__(self) -> None:
        self.entrees: list[tuple[list[str], list[str], int, int]] = []
        self._gauche: list[str] = []
        self._droite: list[str] = []
        self._debut: int | None = None
        self._fin: int | None = None

    def ajouter(self, gauche: str, droite: str, ligne: int) -> None:
        prec_gauche = self._gauche[-1] if self._gauche else ""
        prec_droite = self._droite[-1] if self._droite else ""
        if self._gauche and _commence_entree(gauche, prec_gauche, droite, prec_droite):
            self.cloturer()
        if self._debut is None:
            self._debut = ligne
        self._fin = ligne
        if gauche:
            self._gauche.append(gauche)
        if droite:
            self._droite.append(droite)

    def cloturer(self) -> None:
        if self._gauche or self._droite:
            self.entrees.append(
                (
                    list(self._gauche),
                    list(self._droite),
                    self._debut or 0,
                    self._fin or 0,
                )
            )
        self._gauche, self._droite = [], []
        self._debut, self._fin = None, None


def segmenter(chemin: Path, genres_ecartes: set[str] | None = None) -> Rapport:
    genres_ecartes = genres_ecartes or set()
    lignes = chemin.read_text(encoding="utf-8").splitlines()
    rapport = Rapport()

    pile: list[Section] = []
    registre: dict[str, Section] = {}
    courante: Section | None = None
    genre_courant = "prose"
    dans_annexe = False
    tableau: _TableauEnCours | None = None
    compteurs: dict[str, int] = {}
    tampon_prose: list[str] = []
    debut_prose = 0

    def id_unite(section: Section, genre: str) -> str:
        cle = f"{section.id}/{genre}"
        compteurs[cle] = compteurs.get(cle, 0) + 1
        return f"{cle}/{compteurs[cle]:02d}"

    def vider_tableau() -> None:
        nonlocal tableau
        if tableau is None or courante is None:
            tableau = None
            return
        tableau.cloturer()
        for gauche, droite, debut, fin in tableau.entrees:
            notions = _fusionner(gauche)
            commentaires = _fusionner(droite)
            if not notions and not commentaires:
                continue
            unite = Unite(
                id=id_unite(courante, "table"),
                section=courante,
                genre="table",
                notions=notions,
                commentaires=commentaires,
                texte="",
                ligne_debut=debut,
                ligne_fin=fin,
                semestre=_semestre(f"{notions} {commentaires}"),
            )
            rapport.unites.append(unite)
        tableau = None

    def vider_prose() -> None:
        nonlocal tampon_prose, debut_prose
        if not tampon_prose or courante is None:
            tampon_prose = []
            return
        texte = _fusionner(tampon_prose)
        tampon_prose = []
        if len(texte) < 40:  # titres orphelins, légendes de figure
            return
        genre = genre_courant
        unite = Unite(
            id=id_unite(courante, genre),
            section=courante,
            genre=genre,
            notions="",
            commentaires="",
            texte=texte,
            ligne_debut=debut_prose,
            ligne_fin=debut_prose + len(texte.splitlines()),
            semestre=_semestre(texte),
        )
        if genre in genres_ecartes:
            rapport.ecarter(unite.id, f"genre écarté : {genre}", unite.ligne_debut)
            return
        rapport.unites.append(unite)

    for index, ligne_brute in enumerate(lignes, start=1):
        ligne = ligne_brute.rstrip()

        if RE_TITRE.match(ligne):
            vider_tableau()
            vider_prose()
            section = _analyser_titre(ligne, index, pile, registre)
            if section.numero:
                registre[section.numero] = section
            pile = [s for s in pile if s.niveau < section.niveau] + [section]
            if RE_MISE_EN_OEUVRE.search(section.titre):
                genre_courant = "mise_en_oeuvre"
                # Le titre « Mise en œuvre » n'ouvre pas une section : on garde
                # la section porteuse comme contexte.
                pile.pop()
            else:
                # `dans_annexe` est RÉMANENT : les puces d'annexe vivent sous des
                # sous-titres non numérotés (« Traits généraux », « Divers »).
                # Sans rémanence elles retombent en `prose` et se retrouvent
                # agglutinées en un seul pavé, ce qui les rend inexploitables.
                if section.numero:
                    dans_annexe = section.numero.split(".")[0].isalpha()
                genre_courant = "annexe" if dans_annexe else "prose"
                courante = section
                rapport.sections.append(section)
            continue

        if courante is None:
            continue

        if ligne.startswith("|"):
            vider_prose()
            if RE_SEPARATEUR.match(ligne):
                continue
            cellules = _cellules(ligne)
            if len(cellules) < 2:
                continue
            gauche, droite = cellules[0], cellules[1]
            if gauche.lower().startswith("notions") and droite.lower().startswith(
                "commentaires"
            ):
                continue  # ligne d'en-tête
            if tableau is None:
                tableau = _TableauEnCours()
            tableau.ajouter(gauche, droite, index)
            continue

        vider_tableau()

        if not ligne.strip():
            vider_prose()
            continue

        m_puce = RE_PUCE.match(ligne)
        if m_puce and genre_courant == "annexe":
            vider_prose()
            texte = _nettoyer(m_puce.group("texte"))
            if len(texte) >= 20:
                unite = Unite(
                    id=id_unite(courante, "annexe"),
                    section=courante,
                    genre="annexe",
                    notions="",
                    commentaires="",
                    texte=texte,
                    ligne_debut=index,
                    ligne_fin=index,
                    semestre=None,
                )
                if "annexe" in genres_ecartes:
                    rapport.ecarter(unite.id, "genre écarté : annexe", index)
                else:
                    rapport.unites.append(unite)
            continue

        if not tampon_prose:
            debut_prose = index
        tampon_prose.append(_nettoyer(ligne))

    vider_tableau()
    vider_prose()
    return rapport


def filtrer(rapport: Rapport, titres_exclus: list[str], prefixes_exclus: list[str]) -> Rapport:
    """Applique les exclusions déterministes du profil, en les journalisant."""
    titres = {t.lower() for t in titres_exclus}
    gardees: list[Unite] = []
    for unite in rapport.unites:
        titre = unite.section.titre.lower()
        numero = unite.section.numero or ""
        if any(t in titre for t in titres):
            rapport.ecarter(unite.id, f"titre exclu : {unite.section.titre}", unite.ligne_debut)
            continue
        if any(numero == p or numero.startswith(p + ".") for p in prefixes_exclus):
            rapport.ecarter(unite.id, f"section exclue : {numero}", unite.ligne_debut)
            continue
        gardees.append(unite)
    rapport.unites = gardees
    return rapport


def grouper_par_section(unites: list[Unite]) -> dict[str, list[Unite]]:
    """Une section = un appel LLM. Garde l'ordre d'apparition."""
    groupes: dict[str, list[Unite]] = {}
    for unite in unites:
        groupes.setdefault(unite.section.id, []).append(unite)
    return groupes
