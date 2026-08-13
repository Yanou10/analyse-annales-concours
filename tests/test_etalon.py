"""Appariement en deux temps contre l'étalon écrit à la main.

Le défaut d'origine : la comparaison se faisait sur les identifiants exacts, et
rendait 0,0 parce que l'étalon disait `induction_structurelle` là où le
générateur produit `prouver_par_induction_structurelle`. C'était le test qui
était cassé, pas le référentiel.
"""

from __future__ import annotations

import yaml

from etage0 import referentiel as ref


def _notion(identifiant, libelle):
    section, slug = identifiant.split(".", 1)
    return {
        "id": identifiant,
        "slug": slug,
        "section_id": section,
        "libelle": libelle,
        "exclusions": [],
    }


def _ecrire_etalon(tmp_path, section, notions):
    dossier = tmp_path / "etalon"
    dossier.mkdir(exist_ok=True)
    (dossier / f"{section}.yaml").write_text(
        yaml.safe_dump(
            {
                "section": {"id": section},
                "notions": [{"id": i, "libelle": lib} for i, lib in notions],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return dossier


def test_identifiant_exact_compte_dans_le_premier_temps(tmp_path):
    dossier = _ecrire_etalon(tmp_path, "preuve", [("preuve.une", "Faire la chose")])
    referentiel = ref.Referentiel(notions=[_notion("preuve.une", "Faire la chose")])
    mesure = ref.comparer_etalon(referentiel, dossier)
    assert mesure["rappel_exact"] == 1.0
    assert mesure["appariements_par_similarite"] == []


def test_le_cas_qui_rendait_zero(tmp_path):
    """Le vocabulaire diffère, l'action est la même : le second temps rattrape."""
    dossier = _ecrire_etalon(
        tmp_path, "preuve", [("preuve.induction_structurelle", "Mener une preuve par induction structurelle")]
    )
    referentiel = ref.Referentiel(
        notions=[
            _notion(
                "preuve.prouver_par_induction_structurelle",
                "Démontrer une propriété par induction structurelle",
            )
        ]
    )
    mesure = ref.comparer_etalon(referentiel, dossier)
    assert mesure["rappel_exact"] == 0.0
    assert mesure["rappel_avec_similarite"] == 1.0
    (paire,) = mesure["appariements_par_similarite"]
    assert paire["obtenu"] == "preuve.prouver_par_induction_structurelle"
    assert paire["meme_section"] is True


def test_les_paires_appariees_sont_rendues_pour_controle(tmp_path):
    """Elles ne sont pas des succès démontrés : elles doivent être lisibles,
    libellés des deux côtés, sans avoir à rouvrir les fichiers."""
    dossier = _ecrire_etalon(
        tmp_path, "preuve", [("preuve.induction_structurelle", "Mener une preuve par induction structurelle")]
    )
    referentiel = ref.Referentiel(
        notions=[
            _notion(
                "preuve.prouver_par_induction_structurelle",
                "Démontrer une propriété par induction structurelle",
            )
        ]
    )
    (paire,) = ref.comparer_etalon(referentiel, dossier)["appariements_par_similarite"]
    assert set(paire) >= {
        "etalon", "obtenu", "score", "libelle_etalon", "libelle_obtenu", "meme_section"
    }
    assert all(paire[c] for c in ("libelle_etalon", "libelle_obtenu"))


def test_deux_actions_distinctes_ne_s_apparient_pas(tmp_path):
    """Le faux positif qui a fait monter le seuil de 0,62 à 0,70 : ces deux
    libellés ne partagent que la sous-chaîne « implication »."""
    dossier = _ecrire_etalon(
        tmp_path, "preuve", [("preuve.double_implication", "Prouver une équivalence par double implication")]
    )
    referentiel = ref.Referentiel(
        notions=[
            _notion(
                "graphes_algo.resoudre_2sat_par_implications",
                "Résoudre une instance 2-SAT par le graphe d'implications",
            )
        ]
    )
    mesure = ref.comparer_etalon(referentiel, dossier)
    assert mesure["appariements_par_similarite"] == []
    assert mesure["detail"]["preuve"]["manquants"] == ["preuve.double_implication"]


def test_un_slug_court_inclus_dans_un_autre_ne_gagne_pas_par_defaut(tmp_path):
    """Le recouvrement rapporté au plus court saturait à 1,0 dès inclusion :
    `induction_structurelle` appariait aussi bien
    `parcourir_formule_par_induction_structurelle` que la bonne notion."""
    dossier = _ecrire_etalon(
        tmp_path, "preuve", [("preuve.induction_structurelle", "Mener une preuve par induction structurelle")]
    )
    referentiel = ref.Referentiel(
        notions=[
            _notion(
                "logique.parcourir_formule_par_induction_structurelle",
                "Traiter une formule par induction sur sa structure syntaxique",
            ),
            _notion(
                "preuve.prouver_par_induction_structurelle",
                "Démontrer une propriété par induction structurelle",
            ),
        ]
    )
    (paire,) = ref.comparer_etalon(referentiel, dossier)["appariements_par_similarite"]
    assert paire["obtenu"] == "preuve.prouver_par_induction_structurelle"


def test_l_appariement_est_un_a_un(tmp_path):
    """Deux notions de l'étalon ne peuvent pas se réclamer de la même notion
    obtenue : le rappel s'en trouverait gonflé."""
    dossier = _ecrire_etalon(
        tmp_path,
        "preuve",
        [
            ("preuve.induction_structurelle", "Mener une preuve par induction structurelle"),
            ("preuve.induction_structurelle_bis", "Mener une preuve par induction structurelle"),
        ],
    )
    referentiel = ref.Referentiel(
        notions=[
            _notion(
                "preuve.prouver_par_induction_structurelle",
                "Démontrer une propriété par induction structurelle",
            )
        ]
    )
    mesure = ref.comparer_etalon(referentiel, dossier)
    assert len(mesure["appariements_par_similarite"]) == 1


def test_une_notion_rangee_ailleurs_est_signalee(tmp_path):
    dossier = _ecrire_etalon(
        tmp_path, "recursion", [("recursion.cout_pile", "Analyser le coût machine de la récursion")]
    )
    referentiel = ref.Referentiel(
        notions=[_notion("ressources.cout_pile", "Analyser le coût machine de la récursion")]
    )
    mesure = ref.comparer_etalon(referentiel, dossier)
    (paire,) = mesure["appariements_par_similarite"]
    assert paire["meme_section"] is False
    assert mesure["apparies_hors_section"] == ["recursion.cout_pile"]


def test_le_seuil_est_reglable(tmp_path):
    dossier = _ecrire_etalon(
        tmp_path, "preuve", [("preuve.double_implication", "Prouver une équivalence par double implication")]
    )
    referentiel = ref.Referentiel(
        notions=[
            _notion(
                "graphes_algo.resoudre_2sat_par_implications",
                "Résoudre une instance 2-SAT par le graphe d'implications",
            )
        ]
    )
    lache = ref.comparer_etalon(referentiel, dossier, seuil=0.5)
    assert lache["appariements_par_similarite"], "un seuil bas doit ré-apparier"
    assert lache["seuil_similarite"] == 0.5
