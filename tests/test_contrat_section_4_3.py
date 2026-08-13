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


# --------------------------------------------------------------------------- #
# Publication : le contrôle final rapporte, il ne bloque plus
# --------------------------------------------------------------------------- #
class _ReponseFactice:
    """Ce que `appeler_outil` rend, réduit à ce que `cmd_construire` en lit."""

    def __init__(self, charge):
        self.charge = charge
        self.jetons_entree = self.jetons_sortie = 0
        self.jetons_cache_lus = self.jetons_cache_ecrits = 0
        self.notes = []

    def usage(self):
        return {"modele": "factice", "entree": 0, "cache_lus": 0,
                "cache_ecrits": 0, "sortie": 0, "prompt_total": 0}


class _FournisseurFactice:
    nom = "factice"

    def __init__(self, charge):
        self._charge = charge

    def appeler_outil(self, *_args, **_kwargs):
        return _ReponseFactice(self._charge)


def _construire_avec_defaut(tmp_path, monkeypatch, fabrique_notion, strict):
    """Une construction complète dont UN renvoi ne résout pas : c'est le cas
    réel — le modèle invente une cible, la section `idiomes` sera purgée plus
    tard, et rien de tout cela ne doit empêcher la publication."""
    import argparse

    from etage0 import cli
    from etage0.config import Config

    programme = tmp_path / "programme.md"
    programme.write_text(
        "# 1 Section unique\n\n"
        "| Notions | Commentaires |\n| --- | --- |\n"
        "| Écrire un algorithme glouton | on attend une justification |\n",
        encoding="utf-8",
    )
    sortie = tmp_path / "sortie"
    monkeypatch.setenv("ETAGE0_PROGRAMME", str(programme))
    monkeypatch.setenv("ETAGE0_SORTIE", str(sortie))
    monkeypatch.setenv("ETAGE0_JOURNAL", str(tmp_path / "journal.jsonl"))
    config = Config.depuis_env()

    # L'identifiant d'unité vient de la segmentation réelle : une valeur
    # inventée serait rejetée par le contrat, et le test mesurerait alors le
    # rejet plutôt que la publication.
    from etage0.segmentation import filtrer, grouper_par_section, segmenter

    rapport = filtrer(
        segmenter(programme, config.profil.genres_ecartes),
        config.profil.titres_exclus, config.profil.prefixes_exclus,
    )
    assert rapport.unites, "le programme d'essai doit produire au moins une unité"
    unite = rapport.unites[0]

    notion = fabrique_notion(
        "ecrire_algorithme_glouton",
        exclusions=[{"motif": "à ne pas confondre",
                     "voir_slug": "cible_totalement_inventee_xyz"}],
    )
    charge = {"decisions": [{"unite_id": unite.id, "verdict": "admis_reformule",
                             "raison": "reformulation opératoire",
                             "notions": [notion]}]}

    def _fournisseur(_config):
        return _FournisseurFactice(charge)

    monkeypatch.setattr(cli, "construire_fournisseur", _fournisseur)

    args = argparse.Namespace(dry_run=False, section=None, rejouer=False, strict=strict)
    code = cli.cmd_construire(config, args)
    return code, sortie


def test_un_defaut_d_integrite_ne_bloque_plus_la_publication(
    tmp_path, monkeypatch, fabrique_notion
):
    """Le motif : un référentiel construit intégralement restait non publié pour
    deux renvois d'une section d'annexes, ce qui arrêtait toute la chaîne aval —
    l'étiquetage sortait aussitôt par « absence de référentiel »."""
    import yaml

    code, sortie = _construire_avec_defaut(tmp_path, monkeypatch, fabrique_notion,
                                           strict=False)
    assert code == 0
    assert (sortie / "sections").is_dir(), "le référentiel doit être écrit"
    assert list((sortie / "sections").glob("*.yaml"))

    # Rien n'est masqué : le défaut est recensé dans le manifeste.
    manifeste = yaml.safe_load((sortie / "manifest.yaml").read_text(encoding="utf-8"))
    bloquants = [a for a in manifeste["anomalies"] if a["gravite"] == "bloquant"]
    assert bloquants, manifeste["anomalies"]
    assert any(a["code"] == "renvoi_non_resolu" for a in bloquants)


def test_strict_retablit_l_echec_sur_defaut_d_integrite(
    tmp_path, monkeypatch, fabrique_notion
):
    """Le comportement bloquant reste accessible pour quand la chaîne sera
    complète — purge des annexes comprise."""
    code, _ = _construire_avec_defaut(tmp_path, monkeypatch, fabrique_notion,
                                      strict=True)
    assert code == 2
