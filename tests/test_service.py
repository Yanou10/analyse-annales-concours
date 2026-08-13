"""Service HTTP — la jonction, pas les étages.

MinIO est remplacé par un stockage en mémoire adossé au disque : les tests
portent sur ce que le service DÉCIDE — les commandes construites, les refus,
la signature, le nettoyage — pas sur le client MinIO.

Une tâche est réellement exécutée de bout en bout, avec une commande
déterministe et gratuite : une chaîne de montage qui n'a jamais lancé de
sous-processus ne prouve rien.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
EMPREINTE = "a1b2c3d4e5f60718"


class StockageFactice:
    """Un seau = un dossier. Assez fidèle pour ce qu'on vérifie ici."""

    def __init__(self, racine: Path) -> None:
        self.racine = racine
        self.client = self

    def _chemin(self, seau: str, cle: str) -> Path:
        return self.racine / seau / cle

    def etat(self):
        return {"joignable": True, "url": "factice", "seaux": {}}

    def assurer_seaux(self) -> None:
        for seau in ("programmes", "corpus", "sorties"):
            (self.racine / seau).mkdir(parents=True, exist_ok=True)

    def lister(self, seau: str, prefixe: str = "", recursif: bool = True):
        base = self.racine / seau
        if not base.is_dir():
            return
        for chemin in sorted(base.rglob("*")):
            if chemin.is_file():
                cle = chemin.relative_to(base).as_posix()
                if cle.startswith(prefixe):
                    yield type("O", (), {"cle": cle, "taille": chemin.stat().st_size,
                                         "modifie": None})()

    def existe(self, seau: str, cle: str) -> bool:
        return self._chemin(seau, cle).is_file()

    def descendre(self, seau: str, cle: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self._chemin(seau, cle), destination)
        return destination

    def descendre_prefixe(self, seau: str, prefixe: str, dossier: Path):
        dossier.mkdir(parents=True, exist_ok=True)
        sortis = []
        for objet in self.lister(seau, prefixe):
            relatif = objet.cle[len(prefixe):].lstrip("/")
            if not relatif:
                continue
            cible = dossier / relatif
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self._chemin(seau, objet.cle), cible)
            sortis.append(cible)
        return sortis

    def monter(self, chemin: Path, seau: str, cle: str) -> str:
        cible = self._chemin(seau, cle)
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(chemin, cible)
        return cle

    def monter_dossier(self, dossier: Path, seau: str, prefixe: str):
        montes = []
        for chemin in sorted(Path(dossier).rglob("*")):
            if chemin.is_file():
                relatif = chemin.relative_to(dossier).as_posix()
                montes.append(self.monter(chemin, seau, f"{prefixe.rstrip('/')}/{relatif}"))
        return montes

    def monter_json(self, donnees, seau: str, cle: str) -> str:
        cible = self._chemin(seau, cle)
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
        return cle

    def get_object(self, seau: str, cle: str):
        contenu = self._chemin(seau, cle).read_bytes()
        flux = io.BytesIO(contenu)
        flux.close_ = flux.close
        flux.close = lambda: None
        flux.release_conn = lambda: None
        return flux


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    travail = tmp_path_factory.mktemp("travail")
    seaux = tmp_path_factory.mktemp("seaux")
    os.environ["SERVICE_TRAVAIL"] = str(travail)
    os.environ["SERVICE_RACINE_CODE"] = str(RACINE)
    os.environ.setdefault("ETAGE0_PROGRAMME", str(RACINE / "spe777_annexe_1373646.md"))
    os.environ.setdefault("ETAGE0_MODELE", "claude-sonnet-5")
    os.environ.setdefault("ETAGE0_REFLEXION", "0")
    for module in [m for m in list(sys.modules) if m.startswith("service")]:
        del sys.modules[module]

    from service import main as service_main

    factice = StockageFactice(seaux)
    factice.assurer_seaux()
    service_main.stockage = factice
    from service import stockage as module_stockage

    module_stockage.stockage = factice

    with TestClient(service_main.application) as essai:
        yield essai, factice, travail, seaux


def _poser_referentiel(factice: StockageFactice, empreinte: str = EMPREINTE) -> None:
    source = RACINE / "referentiel" / "genere" / "sections"
    if not source.is_dir():
        pytest.skip("référentiel local absent")
    for fichier in sorted(source.glob("*.yaml"))[:3]:
        factice.monter(fichier, "sorties",
                       f"referentiels/{empreinte}/sections/{fichier.name}")


# --------------------------------------------------------------------------- #
def test_une_instance_neuve_est_saine_sans_referentiel(client):
    """`referentiel_absent` est l'état d'une instance neuve, pas une panne."""
    essai, _, _, _ = client
    corps = essai.get("/sante").json()
    assert corps["etat"] == "referentiel_absent"
    assert corps["referentiels"]["disponibles"] == []
    assert "remede" in corps["referentiels"]
    assert corps["protocole"]["signature"], corps["protocole"]


def test_sante_ne_divulgue_jamais_la_cle(client):
    essai, _, _, _ = client
    os.environ["ANTHROPIC_API_KEY"] = "sk-secret-a-ne-pas-divulguer"
    try:
        texte = essai.get("/sante").text
        assert "sk-secret-a-ne-pas-divulguer" not in texte
        assert json.loads(texte)["cle_anthropic_presente"] is True
    finally:
        del os.environ["ANTHROPIC_API_KEY"]


def test_les_endpoints_dependants_refusent_en_409(client):
    """Refuser avant la mise en file, pas échouer à mi-parcours."""
    essai, _, _, _ = client
    for chemin, corps in (
        ("/confronter", {"lot": "l", "referentiel": EMPREINTE}),
        ("/etiqueter", {"lot": "l", "referentiel": EMPREINTE, "passe": "p"}),
        ("/mesurer", {"sous_commande": "distribution", "passes": ["p"],
                      "referentiel": EMPREINTE}),
    ):
        reponse = essai.post(chemin, json=corps)
        assert reponse.status_code == 409, chemin
        detail = reponse.json()["detail"]
        assert detail["erreur"] == "referentiel_absent"
        assert "remede" in detail


@pytest.mark.parametrize("cle", ["../secret", "/etc/passwd", "a/../../b", "..\\x"])
def test_les_cles_qui_remontent_l_arborescence_sont_refusees(client, cle):
    essai, _, _, _ = client
    reponse = essai.post("/extraire", json={"sujets": [cle], "lot": "l"})
    assert reponse.status_code == 400


@pytest.mark.parametrize("empreinte", ["", "trop-court", "ZZZZZZZZZZZZZZZZ", "../../x"])
def test_les_empreintes_mal_formees_sont_refusees(client, empreinte):
    essai, _, _, _ = client
    reponse = essai.post("/mesurer", json={
        "sous_commande": "distribution", "passes": ["p"], "referentiel": empreinte})
    assert reponse.status_code == 400
    assert "empreinte" in reponse.json()["detail"]


def test_l_empreinte_du_referentiel_entre_dans_la_signature(client):
    """Deux référentiels différents ne doivent PAS partager leurs clés de journal.

    La signature de l'étage 3 ne couvre pas le contenu des notions ; c'est la
    graine qui porte l'empreinte, et c'est le seul levier disponible sans
    modifier l'étage.
    """
    from service.main import signature_protocole

    sans = signature_protocole()["signature"]
    a = signature_protocole("a" * 16)["signature"]
    b = signature_protocole("b" * 16)["signature"]
    assert len({sans, a, b}) == 3, (sans, a, b)
    assert signature_protocole("a" * 16)["signature"] == a  # déterministe


def test_le_journal_est_segmente_par_signature(client):
    from service import config as configuration

    a = configuration.journal_de("1111111111111111")
    b = configuration.journal_de("2222222222222222")
    assert a != b
    assert a.parent == b.parent == configuration.JOURNAUX


def test_construire_refuse_un_programme_absent(client):
    essai, _, _, _ = client
    os.environ["ANTHROPIC_API_KEY"] = "factice"
    try:
        reponse = essai.post("/construire", json={"programme": "inexistant.md"})
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
    assert reponse.status_code == 404
    assert "programmes" in reponse.json()["detail"]


def test_construire_est_lourd_et_exige_la_cle(client):
    essai, factice, _, _ = client
    programme = RACINE / "spe777_annexe_1373646.md"
    if not programme.is_file():
        pytest.skip("programme officiel absent")
    (factice.racine / "programmes").mkdir(parents=True, exist_ok=True)
    # Un vrai programme : depuis le garde-fou d'entrée, un fichier d'une ligne
    # est refusé en 422 avant même d'atteindre la file.
    shutil.copy(programme, factice.racine / "programmes" / "p.md")
    ancienne = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        assert essai.post("/construire", json={"programme": "p.md"}).status_code == 503
    finally:
        if ancienne:
            os.environ["ANTHROPIC_API_KEY"] = ancienne
    # en dry-run, aucune clé n'est requise
    corps = essai.post("/construire", json={"programme": "p.md", "dry_run": True}).json()
    assert corps["lourde"] is True


def test_une_tache_va_au_bout_puis_reverse_dans_le_seau(client):
    """Extraction réelle : sous-processus lancé, sorties remontées, espace nettoyé."""
    essai, factice, travail, seaux = client
    source = RACINE / "2024_InfoA.md"
    if not source.is_file():
        pytest.skip("2024_InfoA.md absent")
    (factice.racine / "corpus").mkdir(parents=True, exist_ok=True)
    shutil.copy(source, factice.racine / "corpus" / "2024_InfoA.md")

    lance = essai.post("/extraire", json={
        "sujets": ["2024_InfoA.md"], "lot": "essai"}).json()
    identifiant = lance["tache"]
    for _ in range(160):
        etat = essai.get(f"/taches/{identifiant}").json()
        if etat["etat"] in ("fini", "echec"):
            break
        time.sleep(0.5)

    assert etat["etat"] == "fini", etat.get("stderr", "")[-900:]
    assert etat["resultat"]["documents"] == 1
    assert (seaux / "sorties" / "corpus" / "essai" / "2024_InfoA.json").is_file()

    # L'espace de travail a disparu, quoi qu'il arrive.
    from service import config as configuration

    assert not (configuration.ESPACES / identifiant).exists()
    assert list(configuration.ESPACES.iterdir()) == []


def test_le_referentiel_pose_rend_l_instance_saine(client):
    essai, factice, _, _ = client
    _poser_referentiel(factice)
    corps = essai.get("/sante").json()
    assert corps["etat"] == "ok"
    assert EMPREINTE in corps["referentiels"]["disponibles"]

    liste = essai.get("/referentiels").json()
    assert liste["total"] >= 1
    entree = next(r for r in liste["referentiels"] if r["empreinte"] == EMPREINTE)
    # La signature annoncée est celle qui sera utilisée à l'étiquetage.
    from service.main import signature_protocole

    assert entree["signature_etiquetage"] == signature_protocole(EMPREINTE)["signature"]


def test_confronter_exige_des_sondes(client):
    """Le référentiel est là, les sondes non : 409 distinct, pas un échec plus tard."""
    essai, factice, _, _ = client
    _poser_referentiel(factice)
    reponse = essai.post("/confronter", json={"lot": "essai", "referentiel": EMPREINTE})
    assert reponse.status_code == 409
    assert reponse.json()["detail"]["erreur"] == "sondes_absentes"


def test_etiqueter_passe_la_graine_et_le_journal_segmente(client):
    """La commande construite est le contrat : elle doit porter --graine."""
    essai, factice, travail, _ = client
    _poser_referentiel(factice)
    factice.monter_json([], "sorties", "corpus/essai/x.json")
    os.environ["ANTHROPIC_API_KEY"] = "factice"
    try:
        lance = essai.post("/etiqueter", json={
            "lot": "essai", "referentiel": EMPREINTE, "passe": "p1",
            "batch": True, "tranche_lot": 10, "dry_run": True,
        }).json()
    finally:
        del os.environ["ANTHROPIC_API_KEY"]

    from service.main import signature_protocole

    assert lance["signature"] == signature_protocole(EMPREINTE)["signature"]
    for _ in range(60):
        etat = essai.get(f"/taches/{lance['tache']}").json()
        if etat["commande"]:
            break
        time.sleep(0.3)
    commande = etat["commande"]
    assert commande[1:3] == ["-m", "etage3.cli"]
    assert "--graine" in commande
    assert commande[commande.index("--graine") + 1] == EMPREINTE
    assert "--batch" in commande


def test_la_liste_des_taches_est_antichronologique(client):
    essai, _, _, _ = client
    corps = essai.get("/taches?limite=10").json()
    assert corps["taches"]
    dates = [t["cree"] for t in corps["taches"]]
    assert dates == sorted(dates, reverse=True)
    assert essai.get("/taches/inexistante").status_code == 404


# --------------------------------------------------------------------------- #
# POST /importer
# --------------------------------------------------------------------------- #
def test_importer_refuse_sans_database_url(client):
    """503 immédiat plutôt qu'une tâche mise en file qui échouera."""
    essai, _, _, _ = client
    ancienne = os.environ.pop("DATABASE_URL", None)
    try:
        reponse = essai.post("/importer", json={"verifier_seulement": True})
        assert reponse.status_code == 503
        assert "DATABASE_URL" in reponse.json()["detail"]
    finally:
        if ancienne:
            os.environ["DATABASE_URL"] = ancienne


def test_importer_n_accepte_jamais_une_url_dans_le_corps(client):
    """Une URL Postgres porte un mot de passe : elle ne doit pas transiter par
    HTTP, où elle finirait dans les journaux de l'orchestrateur."""
    from service.main import Import

    assert "url" not in Import.model_fields
    assert "mot_de_passe" not in Import.model_fields
    # Un champ inconnu est ignoré par pydantic, pas transmis à la commande.
    essai, _, _, _ = client
    os.environ["DATABASE_URL"] = "postgresql://factice/annales"
    try:
        corps = essai.post("/importer", json={
            "verifier_seulement": True,
            "url": "postgresql://intrus:secret@ailleurs/base",
        }).json()
        for _ in range(60):
            etat = essai.get(f"/taches/{corps['tache']}").json()
            if etat["commande"]:
                break
            time.sleep(0.2)
        assert "intrus" not in json.dumps(etat["commande"])
        assert "--url" not in etat["commande"]
    finally:
        del os.environ["DATABASE_URL"]


def test_importer_en_verification_ne_descend_rien(client):
    """Le contrôle de schéma n'a besoin ni de passe, ni de référentiel."""
    essai, _, _, _ = client
    os.environ["DATABASE_URL"] = "postgresql://factice/annales"
    try:
        corps = essai.post("/importer", json={"verifier_seulement": True}).json()
        assert corps["mode"] == "verification"
        for _ in range(60):
            etat = essai.get(f"/taches/{corps['tache']}").json()
            if etat["commande"]:
                break
            time.sleep(0.2)
        assert etat["commande"][1:3] == ["-m", "service.base"]
        assert "--verifier-seulement" in etat["commande"]
    finally:
        del os.environ["DATABASE_URL"]


def test_importer_exige_une_passe_et_son_referentiel(client):
    essai, factice, _, _ = client
    _poser_referentiel(factice)
    os.environ["DATABASE_URL"] = "postgresql://factice/annales"
    try:
        # sans passe
        r = essai.post("/importer", json={"referentiel": EMPREINTE})
        assert r.status_code == 400 and "passe" in r.json()["detail"]
        # passe sans sa carte passe.json
        r = essai.post("/importer", json={"passe": "fantome", "referentiel": EMPREINTE})
        assert r.status_code == 409
        assert r.json()["detail"]["erreur"] == "passe_incomplete"
    finally:
        del os.environ["DATABASE_URL"]


# --------------------------------------------------------------------------- #
# GET /objets
# --------------------------------------------------------------------------- #
def test_objets_liste_un_seau_connu(client):
    essai, factice, _, _ = client
    (factice.racine / "corpus").mkdir(parents=True, exist_ok=True)
    (factice.racine / "corpus" / "2019_InfoA.md").write_text("x", encoding="utf-8")
    corps = essai.get("/objets", params={"seau": "corpus"}).json()
    assert corps["seau"] == "corpus"
    assert any(o["cle"].endswith(".md") for o in corps["objets"])
    assert corps["tronque"] is False


def test_objets_refuse_un_seau_inconnu(client):
    """Un seau libre laisserait lire n'importe quoi de l'instance MinIO."""
    essai, _, _, _ = client
    reponse = essai.get("/objets", params={"seau": "secrets"})
    assert reponse.status_code == 400
    assert "programmes" in reponse.json()["detail"]


def test_objets_refuse_un_prefixe_qui_remonte(client):
    essai, _, _, _ = client
    reponse = essai.get("/objets", params={"seau": "corpus", "prefixe": "../../etc"})
    assert reponse.status_code == 400


# --------------------------------------------------------------------------- #
# garde-fou d'entrée de /construire
# --------------------------------------------------------------------------- #
def test_un_sujet_d_annales_est_refuse_en_422_avant_tout_appel(client):
    """Le motif : un sujet déposé par erreur dans `programmes` a consommé des
    appels Opus pour produire 32 notions inexploitables. La segmentation est
    déterministe et gratuite — elle doit trancher AVANT le premier appel."""
    essai, factice, _, _ = client
    sujet = RACINE / "2024_InfoA.md"
    if not sujet.is_file():
        pytest.skip("2024_InfoA.md absent")
    (factice.racine / "programmes").mkdir(parents=True, exist_ok=True)
    shutil.copy(sujet, factice.racine / "programmes" / "annales.md")
    os.environ["ANTHROPIC_API_KEY"] = "factice"
    try:
        reponse = essai.post("/construire", json={"programme": "annales.md"})
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
    assert reponse.status_code == 422
    detail = reponse.json()["detail"]
    assert detail["erreur"] == "pas_un_programme"
    assert detail["sections_trouvees"] < detail["minimum_exige"]
    assert "corpus" in detail["remede"]
    # Aucune tâche n'a été créée POUR CE DOCUMENT : le refus précède la mise en
    # file, donc aucun appel payant n'a pu partir.
    taches = essai.get("/taches?limite=200").json()["taches"]
    assert not any((t.get("contexte") or {}).get("programme") == "annales.md"
                   for t in taches)


def test_un_vrai_programme_passe_le_garde_fou(client):
    essai, factice, _, _ = client
    programme = RACINE / "spe777_annexe_1373646.md"
    if not programme.is_file():
        pytest.skip("programme officiel absent")
    shutil.copy(programme, factice.racine / "programmes" / "officiel.md")
    os.environ["ANTHROPIC_API_KEY"] = "factice"
    try:
        reponse = essai.post("/construire", json={"programme": "officiel.md",
                                                  "dry_run": True})
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
    assert reponse.status_code == 200, reponse.json()


def test_un_gros_rapport_de_jury_est_refuse_malgre_son_nombre_de_sections(client):
    """Quatre rapports d'annales dépassent le seuil de 22 sections (26, 36, 51,
    53). Le compte seul les laisserait passer : c'est la FORME qui les sépare —
    un programme numérote ses sections, un rapport les titre."""
    essai, factice, _, _ = client
    rapport = RACINE / "2022_InfoLCR-rapport.md"
    if not rapport.is_file():
        pytest.skip("2022_InfoLCR-rapport.md absent")
    (factice.racine / "programmes").mkdir(parents=True, exist_ok=True)
    shutil.copy(rapport, factice.racine / "programmes" / "gros-rapport.md")
    os.environ["ANTHROPIC_API_KEY"] = "factice"
    try:
        reponse = essai.post("/construire", json={"programme": "gros-rapport.md"})
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
    assert reponse.status_code == 422
    detail = reponse.json()["detail"]
    assert detail["sections_trouvees"] >= detail["minimum_exige"], "le compte, lui, passe"
    assert detail["part_numerotee"] < detail["part_numerotee_exigee"]
