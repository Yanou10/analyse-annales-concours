"""Étage 1 — non-régression des trois défauts mesurés de l'extraction.

Les défauts corrigés, chacun avec son test :
  - `solution_text` vide sur 4 fichiers sur 5 alors que les sources portent des
    blocs « Solution : » ;
  - environ 30 % du texte perdu entre le `.md` et le JSON — perte qui avait
    fait conclure à tort qu'une technique de preuve n'était attestée qu'une
    fois, ses deux autres attestations étant dans des corrigés non extraits ;
  - `2024_InfoF` traité comme un fichier distinct alors qu'il est identique
    octet pour octet à `2024_InfoC`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from etage1.cli import SEUIL_RATIO
from etage1.extraction import _positions_questions, extraire, extraire_corpus

RACINE = Path(__file__).resolve().parents[1]
SOURCES = [
    "2024_InfoA.md",
    "2024_InfoC.md",
    "2024_InfoF.md",
    "2022_InfoU-exercices.md",
    "2022_InfoLCR-rapport.md",
    "2024_Info-rapport.md",
    "2024_TPAlgo-MPI-rapport.md",
]


def _chemins():
    chemins = [RACINE / nom for nom in SOURCES]
    manquants = [c.name for c in chemins if not c.is_file()]
    if manquants:
        pytest.skip(f"sources absentes : {manquants}")
    return chemins


@pytest.fixture(scope="module")
def corpus():
    documents, journal = extraire_corpus(_chemins())
    return documents, journal


@pytest.fixture(scope="module")
def attendu():
    chemin = RACINE / "tests" / "attendu.json"
    if not chemin.is_file():
        pytest.skip("tests/attendu.json absent — le générer avec `etage1 verifier`")
    return json.loads(chemin.read_text(encoding="utf-8"))


# --- conservation du texte ------------------------------------------------- #


def test_aucun_fichier_sous_le_seuil_de_conservation(corpus):
    documents, _ = corpus
    sous = {d.fichier: d.ratio for d in documents if d.ratio < SEUIL_RATIO}
    assert not sous, f"ratios sous {SEUIL_RATIO} : {sous}"


def test_le_ratio_ne_regresse_pas(corpus, attendu):
    documents, _ = corpus
    for document in documents:
        reference = attendu.get(document.fichier)
        if reference:
            assert document.ratio >= reference["ratio_texte_conserve"] - 1e-6, document.fichier


# --- déduplication --------------------------------------------------------- #


def test_infof_est_ecarte_comme_doublon(corpus):
    """S'il comptait, toute notion attestée dans InfoC le serait « deux fois »
    et la règle des deux fichiers distincts se vérifierait d'elle-même."""
    documents, journal = corpus
    assert "2024_InfoF.md" not in {d.fichier for d in documents}
    assert any("2024_InfoF.md" in l and "doublon" in l for l in journal)


def test_la_deduplication_precede_le_traitement(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    contenu = "# Exercice\n\n**Question 1.** Montrer que 1 = 1.\n"
    a.write_text(contenu, encoding="utf-8")
    b.write_text(contenu, encoding="utf-8")
    documents, _ = extraire_corpus([a, b])
    assert len(documents) == 1


# --- segmentation par exercice --------------------------------------------- #


def test_infoa_a_bien_ses_22_questions(corpus):
    """Le seul comptage vérifié à la main. S'il bouge, l'extraction a changé."""
    documents, _ = corpus
    infoa = next(d for d in documents if d.fichier == "2024_InfoA.md")
    assert len(infoa.questions) == 22
    assert len(infoa.exercices) == 3
    assert [e.titre.strip("*") for e in infoa.exercices][0].startswith("Partie I")


def test_l_identifiant_est_le_couple_exercice_numero(corpus):
    """La numérotation redémarre à chaque exercice : le numéro seul ne
    distingue pas deux questions, le couple si."""
    documents, _ = corpus
    for document in documents:
        identifiants = [q.id for q in document.questions]
        assert len(identifiants) == len(set(identifiants)), document.fichier
        for exercice in document.exercices:
            for question in exercice.questions:
                assert question.id.startswith(exercice.id + "#")


def test_les_series_de_numerotation_ne_se_percutent_pas(corpus):
    """`2024_TPAlgo` fait courir « Question N » et « Question à développer
    pendant l'oral N » en parallèle, chacune repartant de 1."""
    documents, _ = corpus
    tp = next(d for d in documents if d.fichier == "2024_TPAlgo-MPI-rapport.md")
    series = {q.numero.split(".")[0] for q in tp.questions if "." in q.numero}
    assert series, "aucune série qualifiée détectée"
    assert len(tp.questions) > 34, "les questions d'oral manquent"


def test_la_segmentation_ne_repose_pas_sur_question_n(corpus):
    """Chaque exercice vient d'un titre markdown, pas d'un marqueur de question."""
    documents, _ = corpus
    for document in documents:
        for exercice in document.exercices:
            assert not exercice.titre.lower().startswith("question"), exercice.id


# --- solutions ------------------------------------------------------------- #


def test_les_solutions_sont_rattachees(corpus):
    """Zéro solution rattachée sur ces deux fichiers était le défaut d'origine."""
    documents, _ = corpus
    par_fichier = {d.fichier: d for d in documents}
    for nom in ("2024_Info-rapport.md", "2022_InfoU-exercices.md"):
        rattachees = sum(1 for q in par_fichier[nom].questions if q.solution)
        assert rattachees > 10, f"{nom} : {rattachees} solution(s) rattachée(s)"


def test_une_solution_suit_sa_question(tmp_path):
    source = tmp_path / "s.md"
    source.write_text(
        "# Exercice A\n\n"
        "**Question 1.** Montrer que P.\n\n"
        "**Solution :** Par récurrence sur n.\n\n"
        "**Question 2.** Montrer que Q.\n\n"
        "**Solution :** Par l'absurde.\n",
        encoding="utf-8",
    )
    document = extraire(source)
    q1, q2 = document.questions
    assert "récurrence" in q1.solution
    assert "absurde" in q2.solution


def test_un_corrige_global_est_redecoupe_par_numero(tmp_path):
    """`2022_InfoU-exercices` place un seul « ## Corrigé » en fin d'exercice,
    qui rejoue la numérotation. Sans redécoupage, il compterait pour des
    questions supplémentaires."""
    source = tmp_path / "c.md"
    source.write_text(
        "# Exercice B\n\n"
        "**Question 1.** Montrer que P.\n\n"
        "**Question 2.** Montrer que Q.\n\n"
        "## Corrigé\n\n"
        "**Question 1.** On distingue deux cas.\n\n"
        "**Question 2.** Par symétrie.\n",
        encoding="utf-8",
    )
    document = extraire(source)
    assert len(document.questions) == 2, [q.id for q in document.questions]
    assert "deux cas" in document.questions[0].solution
    assert "symétrie" in document.questions[1].solution


# --- filière --------------------------------------------------------------- #


def test_la_filiere_est_lue_dans_le_bon_contexte(corpus):
    """« les candidats aux … concours MPI et Informatique » ne fait pas d'un
    rapport « Banque MP inter-ENS » un sujet MPI."""
    documents, _ = corpus
    attendues = {
        "2024_InfoA.md": "mpi",
        "2024_InfoC.md": "mpi",
        "2022_InfoU-exercices.md": "mp_info",
        "2022_InfoLCR-rapport.md": "mp_info",
        "2024_Info-rapport.md": "mpi",
        "2024_TPAlgo-MPI-rapport.md": "mpi",
    }
    obtenues = {d.fichier: d.filiere for d in documents}
    assert obtenues == attendues


def test_aucun_exercice_n_est_ecarte_pour_sa_filiere(corpus):
    """Signaler plutôt qu'exclure : la filière est un attribut du corpus.

    Le filtrage détruirait l'information « cette notion tombe surtout en MP
    option info » — exactement ce qu'un candidat veut savoir — et, appliqué
    fichier par fichier, il écartait du MP là où du MPI coexiste tout en le
    gardant là où il est seul.
    """
    documents, journal = corpus
    assert not any("écarté — filière" in l for l in journal)
    filieres = {e.filiere for d in documents for e in d.exercices}
    assert filieres == {"mpi", "mp_info"}, filieres


def test_le_filtrage_par_filiere_reste_disponible_mais_explicite():
    documents, journal = extraire_corpus(
        [RACINE / "2024_Info-rapport.md"], filtrer_filiere=True
    )
    assert any("écarté — filière" in l for l in journal)


# --- figures --------------------------------------------------------------- #


def test_une_question_renvoyant_a_une_figure_est_marquee(tmp_path):
    source = tmp_path / "f.md"
    source.write_text(
        "# Exercice C\n\n"
        "**Question 1.** Voir la figure 2 et conclure.\n\n"
        "**Question 2.** Montrer que P sans support graphique.\n",
        encoding="utf-8",
    )
    document = extraire(source)
    assert document.questions[0].figure_manquante is True
    assert document.questions[1].figure_manquante is False


# --- marqueurs ------------------------------------------------------------- #


@pytest.mark.parametrize(
    "ligne,numero",
    [
        ("**Question 12.**", "12"),
        ("#### Question 0 (Préliminaires).", "0"),
        ("**Question I.4.** Montrer que", "I.4"),
        ("Question 3. Donner un exemple", "3"),
    ],
)
def test_formes_de_marqueur_reconnues(ligne, numero):
    trouve = _positions_questions(ligne + "\n")
    assert trouve, ligne
    assert trouve[0][2].split(".", 1)[-1] == numero.split(".", 1)[-1]


# --- groupes sans question ------------------------------------------------- #


def test_aucun_exercice_livre_n_est_vide(corpus):
    """Un groupe sans question n'est pas un exercice. L'unité d'étiquetage
    étant l'exercice, en livrer un vide, c'est payer un appel pour rien —
    « Organisation de l'épreuve » de 2024_TPAlgo pèse 32 388 caractères."""
    documents, _ = corpus
    vides = [e.id for d in documents for e in d.exercices if not e.questions]
    assert not vides, vides


def test_le_bloc_de_tete_rejoint_l_entete(corpus):
    """`2024_InfoC` ouvre sur un titre en ligne 1 : son en-tête d'épreuve
    n'avait nulle part où aller et devenait un exercice à zéro question."""
    documents, _ = corpus
    infoc = next(d for d in documents if d.fichier == "2024_InfoC.md")
    assert "ECOLES NORMALES SUPERIEURES" in infoc.entete
    assert len(infoc.exercices) == 6, [e.titre for e in infoc.exercices]


def test_le_materiel_introductif_rejoint_l_exercice_suivant(tmp_path):
    source = tmp_path / "m.md"
    source.write_text(
        "# Sujet A\n\n**Question 1.** Montrer que P.\n\n"
        "# ATTENTION\n\nConsignes du second sujet.\n\n"
        "# Sujet B\n\n**Question 1.** Montrer que Q.\n",
        encoding="utf-8",
    )
    document = extraire(source)
    assert len(document.exercices) == 2
    assert "Consignes du second sujet" in document.exercices[1].preambule


def test_l_absorption_ne_perd_aucun_caractere(corpus, attendu):
    documents, _ = corpus
    for document in documents:
        reference = attendu.get(document.fichier)
        if reference:
            assert document.ratio >= reference["ratio_texte_conserve"] - 1e-6


# --- propagation de filière ------------------------------------------------ #


def test_un_en_tete_d_annexe_propage_sa_filiere(tmp_path):
    source = tmp_path / "a.md"
    source.write_text(
        "# Banques MP et MPI inter-ENS\n\n"
        "## Annexe : sujets proposés pour la filière MP\n\n"
        "## Sujet MP un\n\n**Question 1.** Montrer que P.\n\n"
        "## Annexe : sujets proposés pour la filière MPI\n\n"
        "## Sujet MPI un\n\n**Question 1.** Montrer que Q.\n",
        encoding="utf-8",
    )
    document = extraire(source)
    par_titre = {e.titre: e.filiere for e in document.exercices}
    assert par_titre["Sujet MP un"] == "mp_info"
    assert par_titre["Sujet MPI un"] == "mpi"


def test_la_propagation_ne_remonte_pas(tmp_path):
    """Un exercice situé AVANT le premier marqueur garde la filière du
    fichier : la propagation est un héritage vers l'aval, pas une teinture."""
    source = tmp_path / "b.md"
    source.write_text(
        "# Banque MPI inter-ENS\n\n"
        "## Sujet initial\n\n**Question 1.** Montrer que P.\n\n"
        "## Annexe : sujets proposés pour la filière MP\n\n"
        "## Sujet annexe\n\n**Question 1.** Montrer que Q.\n",
        encoding="utf-8",
    )
    document = extraire(source)
    par_titre = {e.titre: e.filiere for e in document.exercices}
    assert par_titre["Sujet initial"] == "mpi"
    assert par_titre["Sujet annexe"] == "mp_info"


def test_la_propagation_est_journalisee(corpus):
    """Douze exercices basculent sur 2024_Info-rapport : un changement de cette
    ampleur doit se lire, pas se déduire."""
    documents, journal = corpus
    assert any("propagation de filière" in l for l in journal)
    assert any("mpi -> mp_info" in l for l in journal)


# --------------------------------------------------------------------------- #
# Deux défauts mesurés le 2026-08-12, à l'ouverture du corpus complet.
# --------------------------------------------------------------------------- #


def test_une_partie_en_chiffres_arabes_decoupe_comme_une_partie_romaine(tmp_path):
    """Le niveau de titre ne suit pas toujours la structure du document.

    Quatre sujets `InfoF` numérotent leurs parties en chiffres et titrent à des
    niveaux markdown incohérents. `2020_InfoF` mettait `# Partie II` en niveau
    1 quand ses voisines étaient en niveau 2 : ses sept questions étaient
    absorbées par la Partie I, et le ratio de conservation passait à 1,0021 —
    au-dessus de 1, donc du double comptage.
    """
    source = tmp_path / "arabe.md"
    source.write_text(
        "## Partie 1\n\nDes préliminaires.\n\n"
        "**Question 1.1** Montrer que P.\n\n**Question 1.2** Montrer que Q.\n\n"
        "# Partie 2\n\nUne autre matière.\n\n"
        "**Question 2.1** Montrer que R.\n\n**Question 2.2** Montrer que S.\n",
        encoding="utf-8",
    )
    document = extraire(source)
    assert len(document.exercices) == 2, [e.titre for e in document.exercices]
    for exercice in document.exercices:
        prefixes = {q.numero.split(".")[0] for q in exercice.questions}
        assert len(prefixes) == 1, (exercice.titre, prefixes)


def test_une_question_avant_le_premier_titre_n_est_pas_perdue(tmp_path):
    """Une question placée avant le premier titre d'exercice tombait dans
    l'en-tête, d'où rien ne la relit — 34 questions de cinq sujets.

    Le ratio n'en disait rien : l'en-tête compte dans les caractères extraits,
    donc le texte était conservé et seule son ATTRIBUTION était perdue. C'est
    pourquoi le garde-fou compte les marqueurs, pas les caractères.
    """
    source = tmp_path / "tete.md"
    source.write_text(
        "# Épreuve\n\nPréliminaires.\n\n"
        "**Question 1.** Montrer que P.\n\n**Question 2.** Montrer que Q.\n\n"
        "## Exercice A\n\n**Question 3.** Montrer que R.\n",
        encoding="utf-8",
    )
    document = extraire(source)
    numeros = {q.numero for q in document.questions}
    assert numeros == {"1", "2", "3"}, numeros
    assert not any("ATTRIBUTION" in ligne for ligne in document.journal), document.journal


def test_le_ratio_ne_depasse_jamais_un_sans_le_dire(corpus):
    """Un ratio de conservation supérieur à 1 est structurellement impossible :
    c'est du texte compté deux fois. Le signaler vaut mieux que le lire comme
    un arrondi favorable."""
    documents, _ = corpus
    for document in documents:
        if document.ratio > 1.0:
            assert any("ANOMALIE" in ligne for ligne in document.journal), document.fichier
