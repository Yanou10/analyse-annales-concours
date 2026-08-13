"""Renvois typés, et passe finale sur le référentiel complet.

Le défaut d'origine : quatre `voir` pointaient vers des identifiants
inexistants, et un cinquième désignait une SECTION (`complexite_algo`) là où le
schéma n'admettait que des notions. Vérifier au moment de l'appel ne suffit
pas — un renvoi peut viser une notion d'une section pas encore générée, ou
purgée après coup.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from etage0 import referentiel as ref

RACINE = Path(__file__).resolve().parents[1]


def _notion(identifiant, exclusions):
    section, slug = identifiant.split(".", 1)
    return {
        "id": identifiant,
        "slug": slug,
        "section_id": section,
        "libelle": f"Faire {slug}",
        "exclusions": exclusions,
    }


SECTIONS = {"preuve", "complexite_algo", "recursion", "strategies"}


def test_un_renvoi_vers_une_notion_existante_ne_dit_rien():
    notions = [
        _notion("preuve.une", [{"motif": "m", "voir": "preuve.deux", "voir_type": "notion"}]),
        _notion("preuve.deux", []),
    ]
    assert ref.verifier_renvois(notions, SECTIONS) == []


def test_un_renvoi_mort_est_bloquant():
    notions = [
        _notion("preuve.une", [{"motif": "m", "voir": "preuve.fantome", "voir_type": "notion"}])
    ]
    (anomalie,) = ref.verifier_renvois(notions, SECTIONS)
    assert anomalie.gravite == "bloquant"
    assert "preuve.fantome" in anomalie.message


def test_un_renvoi_non_resolu_conserve_sa_cible_d_origine():
    """`voir_brut` est ce qui rend une faute de frappe rattrapable : sans lui,
    un renvoi mort s'écrivait `voir: null`, indiscernable d'un renvoi nul."""
    notions = [
        _notion(
            "preuve.une",
            [{"motif": "m", "voir": None, "voir_type": None, "voir_brut": "fichier_sequelle"}],
        )
    ]
    (anomalie,) = ref.verifier_renvois(notions, SECTIONS)
    assert anomalie.gravite == "bloquant"
    assert "fichier_sequelle" in anomalie.message


def test_un_renvoi_nul_legitime_ne_dit_rien():
    """Aucune notion ne couvre le cas : c'est une réponse valide du modèle."""
    notions = [_notion("preuve.une", [{"motif": "m", "voir": None, "voir_type": None}])]
    assert ref.verifier_renvois(notions, SECTIONS) == []


def test_un_renvoi_vers_une_section_existante_est_un_avertissement():
    """Ni mort ni pleinement satisfaisant : plus grossier qu'une notion, mais
    il résout. C'est la distinction que le schéma ne portait pas."""
    notions = [
        _notion(
            "preuve.une", [{"motif": "m", "voir": "complexite_algo", "voir_type": "section"}]
        )
    ]
    (anomalie,) = ref.verifier_renvois(notions, SECTIONS)
    assert anomalie.gravite == "avertissement"
    assert "section" in anomalie.message


def test_un_renvoi_vers_une_section_hors_profil_est_un_avertissement():
    """Pointer une section absente du PROFIL est un défaut de portée, pas
    d'intégrité : la section existe au programme, elle n'est simplement pas une
    cible. Le classer bloquant faisait échouer une construction brute complète
    — 44/44 sections, un artefact payé 3 $ — pour un motif que l'arbitrage des
    renvois résorbe."""
    notions = [
        _notion("preuve.une", [{"motif": "m", "voir": "section_morte", "voir_type": "section"}])
    ]
    (anomalie,) = ref.verifier_renvois(notions, SECTIONS)
    assert anomalie.gravite == ref.ATTENDU
    assert anomalie.code == "renvoi_mort_section"
    assert anomalie.code in ref.RESORBE_PAR


def test_un_renvoi_mort_vers_une_notion_reste_bloquant():
    """La contrepartie : une notion citée qui n'existe pas rend le référentiel
    inutilisable. C'est de l'intégrité, et ça ne se résorbe pas plus tard."""
    notions = [
        _notion("preuve.une", [{"motif": "m", "voir": "preuve.fantome", "voir_type": "notion"}])
    ]
    (anomalie,) = ref.verifier_renvois(notions, SECTIONS)
    assert anomalie.gravite == ref.FATAL
    assert anomalie.code == "renvoi_mort_notion"


def test_toute_regle_du_controle_final_a_une_severite_declaree():
    """Le défaut qu'on corrige ici est d'avoir des sévérités écrites au site
    d'appel. Une règle sans entrée dans la table est FATALE par défaut — mieux
    vaut bloquer sur une règle oubliée que la laisser passer en silence — mais
    elle ne doit pas exister."""
    assert set(ref.RESORBE_PAR) <= set(ref.SEVERITE_CONTROLE)
    for code, gravite in ref.SEVERITE_CONTROLE.items():
        assert gravite in (ref.FATAL, ref.ATTENDU), (code, gravite)
    # Ce que la table classe attendu ne doit jamais être un défaut d'intégrité.
    for code in ("renvoi_non_resolu", "renvoi_mort_notion", "renvoi_sans_type",
                 "identifiant_double", "section_perdue"):
        assert ref.SEVERITE_CONTROLE[code] == ref.FATAL, code
    for code in ("notions_au_dessus_cible", "section_au_dessus_seuil",
                 "renvoi_vers_section", "renvoi_mort_section"):
        assert ref.SEVERITE_CONTROLE[code] == ref.ATTENDU, code


def test_un_renvoi_sans_type_est_bloquant():
    """Sans `voir_type`, on ne sait pas dans quel espace de noms vérifier :
    c'est exactement l'ambiguïté qui faisait passer une section pour une notion
    morte."""
    notions = [_notion("preuve.une", [{"motif": "m", "voir": "complexite_algo"}])]
    (anomalie,) = ref.verifier_renvois(notions, SECTIONS)
    assert anomalie.gravite == "bloquant"
    assert "voir_type" in anomalie.message


def test_une_notion_qui_s_exclut_elle_meme_est_signalee():
    notions = [
        _notion("preuve.une", [{"motif": "m", "voir": "preuve.une", "voir_type": "notion"}])
    ]
    anomalies = ref.verifier_renvois(notions, SECTIONS)
    assert any("s'exclut elle-même" in a.message for a in anomalies)


def test_la_passe_voit_les_renvois_entre_sections(tmp_path):
    """Le cas que la vérification dans l'appel ne pouvait pas couvrir : la cible
    est dans une autre section, générée ou injectée séparément."""
    dossier = tmp_path / "sections"
    dossier.mkdir()
    (dossier / "01-preuve.yaml").write_text(
        yaml.safe_dump(
            {
                "section": {"id": "preuve"},
                "notions": [
                    _notion(
                        "preuve.une",
                        [{"motif": "m", "voir": "strategies.autre", "voir_type": "notion"}],
                    )
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    # cible absente : la passe doit voir le trou
    assert ref.verifier_renvois(ref.charger_notions(dossier), SECTIONS)

    (dossier / "10-strategies.yaml").write_text(
        yaml.safe_dump(
            {"section": {"id": "strategies"}, "notions": [_notion("strategies.autre", [])]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    # cible présente dans un AUTRE fichier : plus rien à signaler
    assert ref.verifier_renvois(ref.charger_notions(dossier), SECTIONS) == []


def test_le_referentiel_livre_n_a_aucun_renvoi_mort(profil):
    """Test de l'ARTEFACT et non du code : le référentiel publié doit résoudre.

    C'est ce test-là qui aurait attrapé les renvois morts sans qu'on ait à
    relancer une génération — la vérification faite au moment de l'appel ne
    voyait pas les cibles purgées après coup.
    """
    dossier = RACINE / "referentiel" / "genere" / "sections"
    if not dossier.is_dir():
        pytest.skip("aucun référentiel généré")
    anomalies = ref.verifier_renvois(
        ref.charger_notions(dossier), set(profil.ids_sections_cibles)
    )
    morts = [a for a in anomalies if a.gravite == "bloquant"]
    assert not morts, "renvois morts :\n" + "\n".join(a.message for a in morts)
