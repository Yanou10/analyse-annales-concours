"""Service HTTP — ce qui doit rester vrai quel que soit l'orchestrateur.

Les tests portent sur la JONCTION, pas sur les étages : les commandes
construites, le refus des chemins hors volume, le fait que la clé ne transite
jamais par HTTP, et la persistance de l'état des tâches.

Une seule tâche est réellement exécutée de bout en bout — une commande
déterministe et gratuite — parce qu'une chaîne de montage qui n'a jamais lancé
un sous-processus ne prouve rien.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    travail = tmp_path_factory.mktemp("travail")
    os.environ["SERVICE_TRAVAIL"] = str(travail)
    os.environ["SERVICE_RACINE_CODE"] = str(RACINE)
    os.environ.setdefault("ETAGE0_PROGRAMME", str(RACINE / "spe777_annexe_1373646.md"))
    os.environ.setdefault("ETAGE0_MODELE", "claude-sonnet-5")
    os.environ.setdefault("ETAGE0_REFLEXION", "0")
    for module in [m for m in list(__import__("sys").modules) if m.startswith("service")]:
        del __import__("sys").modules[module]
    from service.main import application

    with TestClient(application) as essai:
        yield essai, travail


# --------------------------------------------------------------------------- #
def test_sante_rend_empreinte_et_signature(client):
    essai, _ = client
    reponse = essai.get("/sante")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["etat"] == "ok"
    assert corps["referentiel"]["notions"] > 0
    assert len(corps["referentiel"]["empreinte"]) == 16
    assert corps["protocole"]["signature"], corps["protocole"]
    assert isinstance(corps["cle_anthropic_presente"], bool)


def test_sante_ne_divulgue_jamais_la_cle(client):
    """La clé ne doit exister nulle part dans la réponse, seulement sa présence."""
    essai, _ = client
    os.environ["ANTHROPIC_API_KEY"] = "sk-secret-a-ne-pas-divulguer"
    try:
        corps = essai.get("/sante").text
        assert "sk-secret-a-ne-pas-divulguer" not in corps
        assert json.loads(corps)["cle_anthropic_presente"] is True
    finally:
        del os.environ["ANTHROPIC_API_KEY"]


@pytest.mark.parametrize("chemin", ["../etc/passwd", "/etc/passwd", "corpus/../../secret"])
def test_les_chemins_hors_du_volume_sont_refuses(client, chemin):
    essai, _ = client
    reponse = essai.post("/mesurer", json={"sous_commande": "distribution", "passes": [chemin]})
    assert reponse.status_code == 400
    assert "travail" in reponse.json()["detail"]


def test_une_sous_commande_inconnue_est_refusee_tout_de_suite(client):
    """Plutôt qu'une tâche mise en file qui échouera à l'exécution."""
    essai, travail = client
    (travail / "p").mkdir(exist_ok=True)
    (travail / "p" / "etiquettes.json").write_text("[]", encoding="utf-8")
    reponse = essai.post("/mesurer", json={"sous_commande": "ventilation", "passes": ["p"]})
    assert reponse.status_code == 400
    assert "distribution" in reponse.json()["detail"]


def test_dispersion_exige_deux_passes(client):
    essai, travail = client
    reponse = essai.post("/mesurer", json={"sous_commande": "dispersion", "passes": ["p"]})
    assert reponse.status_code == 400
    assert "deux passes" in reponse.json()["detail"]


def test_etiqueter_refuse_sans_cle(client):
    """503 immédiat : accepter la tâche ferait échouer un travail mis en file."""
    essai, travail = client
    (travail / "corpus").mkdir(exist_ok=True)
    (travail / "corpus" / "x.json").write_text("[]", encoding="utf-8")
    ancienne = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        reponse = essai.post("/etiqueter", json={
            "corpus": ["corpus/x.json"], "sortie": "sortie",
        })
        assert reponse.status_code == 503
        assert "ANTHROPIC_API_KEY" in reponse.json()["detail"]
    finally:
        if ancienne:
            os.environ["ANTHROPIC_API_KEY"] = ancienne


def test_les_options_globales_precedent_la_sous_commande(client):
    """`--modele` (étage 3) et `--referentiel` (étage 4) sont GLOBAUX : placés
    après la sous-commande, l'analyse des arguments échoue."""
    essai, travail = client
    (travail / "p2").mkdir(exist_ok=True)
    (travail / "p2" / "etiquettes.json").write_text("[]", encoding="utf-8")
    (travail / "ref").mkdir(exist_ok=True)
    corps = essai.post("/mesurer", json={
        "sous_commande": "top", "passes": ["p2"], "referentiel": "ref",
        "sans_entete": True, "n": 25,
    }).json()
    commande = corps["commande"]
    # `python -m etage4.cli …` : le service n'appelle pas le script de console,
    # qui n'existe que si le PATH du processus contient le dossier des scripts.
    assert commande[1:3] == ["-m", "etage4.cli"]
    assert commande.index("--referentiel") < commande.index("top")
    assert commande.index("--sans-entete") < commande.index("top")
    assert commande[-2:] == ["--n", "25"]

    os.environ["ANTHROPIC_API_KEY"] = "factice"
    try:
        corps = essai.post("/etiqueter", json={
            "corpus": ["corpus/x.json"], "sortie": "s", "modele": "claude-sonnet-5",
            "batch": True, "tranche_lot": 10,
        }).json()
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
    commande = corps["commande"]
    assert commande[1:5] == ["-m", "etage3.cli", "--modele", "claude-sonnet-5"]
    assert commande.index("--modele") < commande.index("etiqueter")
    assert "--batch" in commande and "--tranche-lot" in commande


def test_etiqueter_est_marque_lourd(client):
    """Une seule tâche lourde à la fois : c'est ce drapeau qui l'oriente vers la
    file à exécutant unique, et qui évite de payer deux fois les mêmes appels."""
    essai, travail = client
    os.environ["ANTHROPIC_API_KEY"] = "factice"
    try:
        lourde = essai.post("/etiqueter", json={
            "corpus": ["corpus/x.json"], "sortie": "s2",
        }).json()
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
    assert lourde["lourde"] is True
    legere = essai.post("/mesurer", json={
        "sous_commande": "distribution", "passes": ["p2"]}).json()
    assert legere["lourde"] is False


def test_une_tache_va_au_bout_et_survit_au_redemarrage(client):
    """Exécution réelle d'une commande gratuite, puis relecture de l'état
    depuis le disque comme le ferait un service qui redémarre."""
    essai, travail = client
    source = RACINE / "2024_InfoA.md"
    if not source.is_file():
        pytest.skip("2024_InfoA.md absent")
    (travail / "sujets").mkdir(exist_ok=True)
    (travail / "sujets" / "2024_InfoA.md").write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8")

    lance = essai.post("/extraire", json={
        "fichiers": ["sujets/2024_InfoA.md"], "sortie": "corpus-test",
    }).json()
    identifiant = lance["tache"]

    for _ in range(120):
        etat = essai.get(f"/taches/{identifiant}").json()
        if etat["etat"] in ("fini", "echec"):
            break
        time.sleep(0.5)
    assert etat["etat"] == "fini", etat.get("stderr", "")[-800:]
    assert etat["code_retour"] == 0
    assert (travail / "corpus-test" / "2024_InfoA.json").is_file()
    assert "22" in etat["stderr"], etat["stderr"][-400:]  # 22 questions attendues

    # L'état est sur disque, pas seulement en mémoire.
    fichier = travail / "taches" / f"{identifiant}.json"
    assert fichier.is_file()
    persiste = json.loads(fichier.read_text(encoding="utf-8"))
    assert persiste["etat"] == "fini" and persiste["code_retour"] == 0

    from service.taches import Registre

    relu = Registre(travail / "taches").lire(identifiant)
    assert relu is not None and relu.etat == "fini"


def test_la_liste_des_taches_est_antichronologique(client):
    essai, _ = client
    corps = essai.get("/taches?limite=10").json()
    assert corps["taches"], corps
    dates = [t["cree"] for t in corps["taches"]]
    assert dates == sorted(dates, reverse=True)
    assert essai.get("/taches/inexistante").status_code == 404
