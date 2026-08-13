"""Étage 4 — le tableau de bord ne doit pas pouvoir dire autre chose que la CLI.

Le moteur vient de `build_dashboard.py` (v1) et n'est pas retouché. Ce qui est
vérifié ici, c'est la jonction : ce que le constructeur lui donne.

Le test le plus utile est le dernier : il exécute réellement le moteur sur un
DOM minimal. Un gabarit HTML ne casse pas à l'import, il casse à l'ouverture.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from etage4 import mesures, tableau
from etage4.cli import charger_notions, charger_passe

RACINE = Path(__file__).resolve().parents[1]
PASSE = RACINE / "passe-39"
REFERENTIEL = RACINE / "referentiel" / "genere" / "sections"
MOTEUR = RACINE / "etage4" / "moteur.html"


def test_le_moteur_est_une_ressource_du_paquet():
    """Sans lui, `etage4 dashboard` s'installe et échoue à l'exécution."""
    assert MOTEUR.is_file(), "etage4/moteur.html manquant"
    contenu = MOTEUR.read_text(encoding="utf-8")
    for marqueur in ("__DATA_PLACEHOLDER__", "__PIED_PLACEHOLDER__"):
        assert marqueur in contenu, marqueur
    assert "const DATA" not in contenu, "le gabarit ne doit pas embarquer de données"


@pytest.fixture(scope="module")
def page():
    for chemin in (PASSE / "etiquettes.json", REFERENTIEL, MOTEUR):
        if not chemin.exists():
            pytest.skip(f"absent : {chemin}")
    resultats, _ = charger_passe([str(PASSE)])
    notions = charger_notions(REFERENTIEL)
    data, agregat, stats = tableau.construire(resultats, notions)
    bloc = "<script>\nconst DATA = " + tableau.serialiser(data) + ";\n</script>"
    html = (
        MOTEUR.read_text(encoding="utf-8")
        .replace("<script>__DATA_PLACEHOLDER__</script>", bloc)
        .replace("__PIED_PLACEHOLDER__", "test")
    )
    return html, data, agregat, stats, notions


def test_les_totaux_affiches_sont_ceux_de_la_cli(page):
    """La source est `mesures.agreger`, celle que sert `etage4 distribution`."""
    html, data, agregat, stats, notions = page
    resultats, _ = charger_passe([str(PASSE)])
    attendu = mesures.agreger(mesures.aplatir(resultats))

    assert agregat.questions == attendu.questions
    assert agregat.etiquettes == attendu.etiquettes
    assert agregat.notions_distinctes == attendu.notions_distinctes

    # Les `records` du moteur comptent des OCCURRENCES, pas des questions :
    # c'est la seule grandeur que la page affiche, et elle doit coller.
    assert len(data["records"]) == attendu.etiquettes == stats["etiquettes"]


def test_le_referentiel_sert_de_curriculum(page):
    """La v1 projetait sur un fichier figé à 124 notions et annonçait « 5 jamais
    tombées ». Le référentiel courant en compte 182, dont 63 jamais posées."""
    _, data, agregat, _, notions = page
    assert len(data["notions_officielles"]) == len(notions)
    assert len(data["jamais_tombes"]) == len(notions) - agregat.notions_distinctes
    # Chaque notion jamais posée doit rester filtrable : sans `type`, elle
    # disparaîtrait des vues Algorithmique / Théorie.
    for notion in data["jamais_tombes"]:
        assert data["notion_type"].get(notion), notion
        assert data["notion_section"].get(notion), notion


def test_la_page_est_autonome(page):
    """Aucun CDN, aucune webfont : elle doit s'ouvrir hors ligne d'un double-clic."""
    html, _, _, _, _ = page
    for interdit in ("http://", "https://", "@import", "fonts.googleapis", "<link"):
        assert interdit not in html, interdit


def test_le_moteur_s_execute(page):
    """Le seul contrôle qui prouve que la page rend. Sauté si node est absent."""
    if shutil.which("node") is None:
        pytest.skip("node absent")
    html, _, agregat, _, _ = page
    scripts = "\n".join(re.findall(r"<script>([\s\S]*?)</script>", html))
    harnais = """
    const noeuds=new Map();
    const faire=id=>{const n={id,innerHTML:'',textContent:'',className:'',value:'',
      _a:{},dataset:{},style:{},children:[],
      classList:{add(){},remove(){},toggle(){},contains:()=>false},
      setAttribute(k,v){this._a[k]=v},getAttribute(k){return this._a[k]??null},
      appendChild(c){this.children.push(c);return c},
      querySelectorAll:()=>[],querySelector:()=>null,closest:()=>null,
      addEventListener(){},getBoundingClientRect:()=>({top:0,left:0,width:0,height:0})};
      noeuds.set(id,n);return n;};
    globalThis.document={documentElement:faire(':root'),body:faire('body'),
      getElementById:id=>noeuds.get(id)||faire(id),createElement:()=>faire('x'),
      querySelectorAll:()=>[],querySelector:()=>null,addEventListener(){}};
    globalThis.getComputedStyle=()=>({getPropertyValue:()=>'#888'});
    globalThis.matchMedia=()=>({matches:false,addEventListener(){}});
    globalThis.window=globalThis;
    """
    sonde = """
    const hm=noeuds.get('heatmap').innerHTML;
    if(hm.length < 1000) throw new Error('carte de chaleur vide');
    for (const id of ['ranking','langchart','typechart','sectionchart'])
      if(!noeuds.get(id).innerHTML.length) throw new Error('vue vide : '+id);
    for (const id of ['anneeSel','epreuveSel','langSel','sectionSel','typeSel'])
      if(!noeuds.get(id).children.length) throw new Error('filtre vide : '+id);
    console.log('LIGNES='+(hm.match(/<tr/g)||[]).length);
    console.log(noeuds.get('rankTotal').textContent);
    """
    with tempfile.TemporaryDirectory() as dossier:
        chemin = Path(dossier) / "verif.mjs"
        chemin.write_text(harnais + "\n" + scripts + "\n" + sonde, encoding="utf-8")
        acheve = subprocess.run(["node", str(chemin)], capture_output=True,
                                text=True, timeout=120)
    assert acheve.returncode == 0, acheve.stderr[-1500:]
    # Le moteur affiche lui-même ses totaux : ils doivent coller à l'agrégat.
    assert f"total {agregat.etiquettes}" in acheve.stdout, acheve.stdout
    assert f"{len(charger_notions(REFERENTIEL))} notions" in acheve.stdout, acheve.stdout
