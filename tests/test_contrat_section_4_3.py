"""Non-régression : §4.3 perdue en entier pour une unité mal étiquetée.

Ce que le bug était
-------------------
Le validateur levait `ErreurContrat` à la première violation. L'appelant
attrapait par SECTION : une exception, et la section entière était abandonnée.
§4.3 comptait six unités ; l'une d'elles portait le verdict `eclate` avec une
seule notion, alors que `eclate` en exige deux. Les six sont parties, et avec
elles le glouton, diviser pour régner, la dichotomie et la programmation
dynamique — absents du référentiel sans autre trace qu'une ligne sur stderr.

Ce que ces tests garantissent
-----------------------------
1. le grain du rejet est l'objet fautif, jamais la section ;
2. `eclate` à une notion unique est une incohérence d'étiquette, donc réparée
   et non rejetée ;
3. toute réparation est rendue à l'appelant, qui la porte dans manifest.yaml ;
4. une règle réparable sans normalisation est refusée à la DÉCLARATION, pour
   que la prochaine règle ajoutée ne puisse pas rééditer le bug.
"""

from __future__ import annotations

import pytest

from etage0 import contrats


def _charge(*decisions):
    return {"decisions": list(decisions)}


def _decision(unite_id, verdict, notions, raison="décision motivée"):
    return {
        "unite_id": unite_id,
        "verdict": verdict,
        "raison": raison,
        "notions": list(notions),
    }


# --------------------------------------------------------------------------- #
# Le cas exact qui a coûté §4.3
# --------------------------------------------------------------------------- #


@pytest.fixture
def section_4_3(fabrique_unite, fabrique_notion):
    """Six unités, dont la deuxième porte le défaut d'origine."""
    unites = [fabrique_unite(i) for i in range(1, 7)]
    charge = _charge(
        _decision("4.3/table/01", "admis", [fabrique_notion("appliquer_strategie_gloutonne")]),
        # ↓ la fautive : `eclate` annoncé, une seule notion produite
        _decision("4.3/table/02", "eclate", [fabrique_notion("majorer_approximation_gloutonne")]),
        _decision(
            "4.3/table/03",
            "eclate",
            [fabrique_notion("diviser_pour_regner"), fabrique_notion("rechercher_par_dichotomie")],
        ),
        _decision(
            "4.3/table/04", "admis", [fabrique_notion("resoudre_par_programmation_dynamique")]
        ),
        _decision("4.3/table/05", "refuse", []),
        _decision("4.3/table/06", "admis", [fabrique_notion("selectionner_strategie")]),
    )
    return charge, unites


def test_une_unite_fautive_n_emporte_pas_la_section(section_4_3, profil):
    charge, unites = section_4_3
    rapport = contrats.valider_decisions(charge, unites, profil)
    assert len(rapport.decisions) == 6, "les six unités doivent survivre"


def test_les_quatre_notions_de_4_3_survivent(section_4_3, profil):
    charge, unites = section_4_3
    rapport = contrats.valider_decisions(charge, unites, profil)
    produites = {n["slug"] for d in rapport.decisions for n in d["notions"]}
    assert {
        "appliquer_strategie_gloutonne",
        "diviser_pour_regner",
        "rechercher_par_dichotomie",
        "resoudre_par_programmation_dynamique",
    } <= produites


def test_eclate_a_une_notion_est_normalise_et_non_rejete(section_4_3, profil):
    charge, unites = section_4_3
    rapport = contrats.valider_decisions(charge, unites, profil)
    verdicts = {d["unite_id"]: d["verdict"] for d in rapport.decisions}
    assert verdicts["4.3/table/02"] == "admis_reformule"
    assert not rapport.rejets


def test_la_reparation_est_rendue_a_l_appelant(section_4_3, profil):
    """Une correction silencieuse est le même défaut qu'une section perdue en
    silence : elle doit remonter pour finir dans manifest.yaml."""
    charge, unites = section_4_3
    rapport = contrats.valider_decisions(charge, unites, profil)
    codes = [c.code for c in rapport.reparations]
    assert codes == ["eclate_notion_unique"]
    constat = rapport.reparations[0]
    assert constat.cible == "4.3/table/02"
    assert constat.severite == contrats.REPARABLE
    assert "admis_reformule" in constat.reparation


# --------------------------------------------------------------------------- #
# Granularité du rejet
# --------------------------------------------------------------------------- #


def test_une_notion_fautive_n_emporte_pas_ses_soeurs(fabrique_unite, fabrique_notion, profil):
    unites = [fabrique_unite(1)]
    charge = _charge(
        _decision(
            "4.3/table/01",
            "eclate",
            [
                fabrique_notion("notion_valide"),
                fabrique_notion("notion_sans_exclusion", exclusions=[]),
            ],
        )
    )
    rapport = contrats.valider_decisions(charge, unites, profil)
    assert [n["slug"] for n in rapport.decisions[0]["notions"]] == ["notion_valide"]
    assert [c.code for c in rapport.rejets] == ["exclusions_absentes"]


def test_le_verdict_est_renormalise_apres_le_rejet_d_une_notion(
    fabrique_unite, fabrique_notion, profil
):
    """Les règles de décision passent APRÈS celles de notion : une unité
    `eclate` réduite à une notion doit sortir cohérente, pas deux fois fautive."""
    unites = [fabrique_unite(1)]
    charge = _charge(
        _decision(
            "4.3/table/01",
            "eclate",
            [
                fabrique_notion("notion_valide"),
                fabrique_notion("notion_trop_courte", definition_operatoire="trop court"),
            ],
        )
    )
    rapport = contrats.valider_decisions(charge, unites, profil)
    assert rapport.decisions[0]["verdict"] == "admis_reformule"
    assert [c.code for c in rapport.rejets] == ["definition_trop_courte"]


def test_une_unite_sans_decision_est_signalee_sans_faire_tomber_les_autres(
    fabrique_unite, fabrique_notion, profil
):
    unites = [fabrique_unite(1), fabrique_unite(2)]
    charge = _charge(_decision("4.3/table/01", "admis", [fabrique_notion("seule_notion")]))
    rapport = contrats.valider_decisions(charge, unites, profil)
    assert len(rapport.decisions) == 1
    assert [(c.code, c.cible) for c in rapport.rejets] == [
        ("unite_sans_decision", "4.3/table/02")
    ]


def test_la_charge_entierement_invalide_leve_encore(fabrique_unite, profil):
    """Seul cas où la section tombe : rien à sauver."""
    unites = [fabrique_unite(1)]
    charge = _charge(_decision("4.3/table/01", "admis", []))
    with pytest.raises(contrats.ErreurContrat, match="aucune décision exploitable"):
        contrats.valider_decisions(charge, unites, profil)


def test_decisions_absent_leve(profil, fabrique_unite):
    with pytest.raises(contrats.ErreurContrat, match="non tabulaire"):
        contrats.valider_decisions({}, [fabrique_unite(1)], profil)


# --------------------------------------------------------------------------- #
# Le registre lui-même
# --------------------------------------------------------------------------- #


def test_une_regle_reparable_sans_normalisation_est_refusee():
    """La garde qui empêche la prochaine règle de rééditer le bug : on ne peut
    pas déclarer réparable ce qu'on ne sait pas réparer."""
    with pytest.raises(ValueError, match="réparable sans normalisation"):
        contrats.Regle("bidon", contrats.REPARABLE, lambda objet, ctx: "violation")


def test_une_regle_fatale_ne_porte_pas_de_normalisation():
    with pytest.raises(ValueError, match="fatale mais porte une normalisation"):
        contrats.Regle(
            "bidon",
            contrats.FATALE,
            lambda objet, ctx: "violation",
            lambda objet, ctx: "réparée",
        )


@pytest.mark.parametrize("regle", contrats.REGLES_NOTION + contrats.REGLES_DECISION)
def test_toute_regle_declare_une_severite_connue(regle):
    assert regle.severite in (contrats.FATALE, contrats.REPARABLE)


def test_les_codes_de_regle_sont_uniques():
    """Les codes finissent dans manifest.yaml : deux règles homonymes y
    rendraient les réparations indistinguables."""
    codes = [r.code for r in contrats.REGLES_NOTION + contrats.REGLES_DECISION]
    assert len(codes) == len(set(codes))
