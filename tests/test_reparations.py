"""Chaque règle réparable normalise, et rend compte de ce qu'elle a fait."""

from __future__ import annotations

import pytest

from etage0 import contrats


def _valider(profil, unite, notion=None, **decision):
    charge = {
        "decisions": [
            {
                "unite_id": unite.id,
                "verdict": decision.get("verdict", "admis"),
                "raison": decision.get("raison", "décision motivée"),
                "notions": [notion] if notion else decision.get("notions", []),
            }
        ]
    }
    return contrats.valider_decisions(charge, [unite], profil)


def _valider_avec_temoin(profil, fabrique_unite, fabrique_notion, notion):
    """Soumet la notion fautive AVEC une unité saine.

    Sans témoin, rejeter l'unique notion ne laisse aucune décision debout et la
    charge entière est déclarée à refaire — comportement voulu, mais qui masque
    ce que le test veut observer : le rejet d'un seul objet.
    """
    unites = [fabrique_unite(1), fabrique_unite(2)]
    charge = {
        "decisions": [
            {
                "unite_id": unites[0].id,
                "verdict": "admis",
                "raison": "décision motivée",
                "notions": [fabrique_notion("notion_temoin")],
            },
            {
                "unite_id": unites[1].id,
                "verdict": "admis",
                "raison": "décision motivée",
                "notions": [notion],
            },
        ]
    }
    return contrats.valider_decisions(charge, unites, profil)


def test_slug_accentue_est_normalise(profil, fabrique_unite, fabrique_notion):
    rapport = _valider(
        profil, fabrique_unite(1), fabrique_notion("Trier_Par_Fusion_Éclaté")
    )
    assert rapport.decisions[0]["notions"][0]["slug"] == "trier_par_fusion_eclate"
    assert [c.code for c in rapport.reparations] == ["slug_non_normalise"]


def test_slug_sans_caractere_exploitable_est_rejete(profil, fabrique_unite, fabrique_notion):
    rapport = _valider_avec_temoin(
        profil, fabrique_unite, fabrique_notion, fabrique_notion("---")
    )
    assert "slug_irrecuperable" in [c.code for c in rapport.rejets]
    assert [n["slug"] for d in rapport.decisions for n in d["notions"]] == ["notion_temoin"]


def test_declencheurs_surnumeraires_sont_tronques(profil, fabrique_unite, fabrique_notion):
    notion = fabrique_notion("notion", declencheurs=[f"consigne {i}" for i in range(9)])
    rapport = _valider(profil, fabrique_unite(1), notion)
    assert len(rapport.decisions[0]["notions"][0]["declencheurs"]) == contrats.MAX_DECLENCHEURS
    assert [c.code for c in rapport.reparations] == ["declencheurs_trop_nombreux"]


def test_langage_hors_profil_est_retire_et_non_rejete(profil, fabrique_unite, fabrique_notion):
    """Le champ est déclaré « INDICATION seulement » et ne sert jamais de valeur
    par défaut à l'étiquetage : le purger ne fait perdre aucune décision."""
    notion = fabrique_notion("notion", langages_plausibles=["theorique", "brainfuck"])
    rapport = _valider(profil, fabrique_unite(1), notion)
    assert rapport.decisions[0]["notions"][0]["langages_plausibles"] == ["theorique"]
    assert [c.code for c in rapport.reparations] == ["langages_hors_profil"]


def test_section_cible_inconnue_est_rejetee(profil, fabrique_unite, fabrique_notion):
    """Fatale et non réparable : une notion rangée dans une section inexistante
    ne serait écrite dans aucun fichier — elle disparaîtrait en silence."""
    notion = fabrique_notion("notion", section_cible="section_qui_n_existe_pas")
    rapport = _valider_avec_temoin(profil, fabrique_unite, fabrique_notion, notion)
    assert "section_cible_inconnue" in [c.code for c in rapport.rejets]


def test_raison_vide_est_marquee_comme_absente(profil, fabrique_unite, fabrique_notion):
    rapport = _valider(
        profil, fabrique_unite(1), fabrique_notion("notion"), raison="   "
    )
    assert "absente" in rapport.decisions[0]["raison"]
    assert [c.code for c in rapport.reparations] == ["raison_vide"]


def test_admis_a_plusieurs_notions_devient_eclate(profil, fabrique_unite, fabrique_notion):
    """Cas symétrique de `eclate` à une notion : même famille d'incohérence."""
    charge = {
        "decisions": [
            {
                "unite_id": "4.3/table/01",
                "verdict": "admis",
                "raison": "motivée",
                "notions": [fabrique_notion("une"), fabrique_notion("deux")],
            }
        ]
    }
    rapport = contrats.valider_decisions(charge, [fabrique_unite(1)], profil)
    assert rapport.decisions[0]["verdict"] == "eclate"
    assert [c.code for c in rapport.reparations] == ["admis_notions_multiples"]


def test_refuse_avec_notions_est_rejete(profil, fabrique_unite, fabrique_notion):
    """Contradiction de fond et non d'étiquette : on ne devine pas laquelle des
    deux affirmations du modèle est la bonne."""
    charge = {
        "decisions": [
            {
                "unite_id": "4.3/table/01",
                "verdict": "refuse",
                "raison": "motivée",
                "notions": [fabrique_notion("une")],
            }
        ]
    }
    with pytest.raises(contrats.ErreurContrat):
        contrats.valider_decisions(charge, [fabrique_unite(1)], profil)


def test_unite_inventee_est_ecartee(profil, fabrique_unite, fabrique_notion):
    charge = {
        "decisions": [
            {
                "unite_id": "4.3/table/01",
                "verdict": "admis",
                "raison": "motivée",
                "notions": [fabrique_notion("vraie")],
            },
            {
                "unite_id": "9.9/inventee/01",
                "verdict": "admis",
                "raison": "motivée",
                "notions": [fabrique_notion("fausse")],
            },
        ]
    }
    rapport = contrats.valider_decisions(charge, [fabrique_unite(1)], profil)
    assert len(rapport.decisions) == 1
    assert [c.code for c in rapport.rejets] == ["unite_inventee"]


def test_chaque_constat_est_lisible(profil, fabrique_unite, fabrique_notion):
    """`rendu()` sert l'affichage CLI et manifest.yaml : jamais de champ vide."""
    rapport = _valider(profil, fabrique_unite(1), fabrique_notion("Slug_Accentué_É"))
    constat = rapport.reparations[0]
    rendu = constat.rendu()
    assert constat.cible in rendu and "→" in rendu
