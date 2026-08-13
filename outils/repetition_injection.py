"""Répète `etage0 injecter --section 4.3` sur une COPIE, sans appel réseau.

Amorce le journal avec une réponse synthétique portant exactement les défauts
qui ont fait perdre la section : une unité `eclate` à une notion unique, et une
notion irrécupérable. Vérifie que le reste passe.
"""
import json, os, shutil, subprocess, sys
from pathlib import Path

RACINE = Path(r"c:\Users\natha\Downloads\analyse sujets")
SCRATCH = Path(__file__).parent
os.chdir(RACINE)
sys.path.insert(0, str(RACINE))

from etage0 import contrats
from etage0.config import Profil
from etage0.journal import empreinte
from etage0.segmentation import filtrer, grouper_par_section, segmenter

sortie = SCRATCH / "test-genere"
if sortie.exists():
    shutil.rmtree(sortie)
shutil.copytree(RACINE / "referentiel" / "genere", sortie)
journal = SCRATCH / "test-journal.jsonl"
journal.unlink(missing_ok=True)

profil = Profil.charger(RACINE / "profils" / "informatique-mpi.yaml")
rapport = segmenter(RACINE / "spe777_annexe_1373646.md", profil.genres_ecartes)
rapport = filtrer(rapport, profil.titres_exclus, profil.prefixes_exclus)
unites = grouper_par_section(rapport.unites)["4.3"]

outil = contrats.schema_notions(profil)
message = contrats.message_section(unites)
signature = empreinte(
    profil.version_prompt, profil.critere_admission,
    json.dumps(outil, sort_keys=True, ensure_ascii=False), "claude-opus-5", "anthropic",
)
cle = empreinte(signature, "notions", "4.3", message)


def notion(slug, libelle, definition, voir=None, **kw):
    base = dict(
        slug=slug, libelle=libelle, definition_operatoire=definition,
        declencheurs=["Proposer un algorithme qui …", "Justifier que la stratégie est optimale"],
        exclusions=[{"motif": "il s'agit d'explorer tout l'espace des solutions", "voir_slug": voir}],
        langages_plausibles=["theorique"], origine_cellule="notions", section_cible="strategies",
    )
    base.update(kw)
    return base


charge = {"decisions": [
    {"unite_id": "4.3/table/01", "verdict": "admis", "raison": "action évaluable",
     "notions": [notion("appliquer_strategie_gloutonne",
                        "Concevoir un algorithme glouton et prouver qu'il rend une solution exacte",
                        "La question demande de construire une solution par choix localement optimal et de justifier son optimalité globale.",
                        voir="explorer_exhaustivement_espace_solutions")]},
    # LA fautive : eclate avec une seule notion -> doit être normalisée, pas rejetée
    {"unite_id": "4.3/table/02", "verdict": "eclate", "raison": "une seule action en sort",
     "notions": [notion("majorer_facteur_approximation_glouton",
                        "Majorer le facteur d'approximation d'un algorithme glouton",
                        "La question demande de borner l'écart entre la solution gloutonne et l'optimum, sur une instance ou en général.")]},
    {"unite_id": "4.3/table/03", "verdict": "eclate", "raison": "deux actions distinctes",
     "notions": [
         notion("resoudre_par_diviser_pour_regner",
                "Concevoir un algorithme par diviser pour régner et en établir le coût",
                "La question demande de découper l'instance, de résoudre les parties puis de recombiner, et d'en déduire une récurrence de coût."),
         notion("rechercher_par_dichotomie",
                "Rechercher par dichotomie, y compris hors d'un tableau trié",
                "La question demande d'exploiter une monotonie pour diviser par deux l'espace de recherche à chaque étape."),
     ]},
    {"unite_id": "4.3/prose/01", "verdict": "admis_reformule", "raison": "action reformulée",
     "notions": [notion("resoudre_par_programmation_dynamique",
                        "Résoudre un problème par programmation dynamique et reconstruire la solution",
                        "La question demande d'identifier une sous-structure optimale, de calculer de bas en haut ou par mémoïsation, puis de reconstruire la solution.")]},
    {"unite_id": "4.3/prose/02", "verdict": "refuse", "raison": "commentaire d'exemples, aucune action propre",
     "notions": []},
    {"unite_id": "4.3/mise_en_oeuvre/01", "verdict": "admis", "raison": "action de sélection",
     "notions": [notion("selectionner_strategie_algorithmique",
                        "Sélectionner la stratégie algorithmique pertinente pour un problème donné",
                        "La question laisse le choix de la méthode et demande de justifier laquelle s'applique et pourquoi les autres non.")]},
]}

journal.write_text(
    json.dumps({"cle": cle, "etiquette": "notions/4.3", "charge": charge,
                "meta": {"modele": "synthétique", "unites": [u.id for u in unites]}},
               ensure_ascii=False) + "\n",
    encoding="utf-8",
)

env = {**os.environ, "ETAGE0_RACINE": ".", "ETAGE0_PROGRAMME": "spe777_annexe_1373646.md",
       "ETAGE0_SORTIE": str(sortie), "ETAGE0_JOURNAL": str(journal),
       "ETAGE0_ETALON": "referentiel/v1/sections", "PYTHONIOENCODING": "utf-8"}
code = subprocess.call(
    [sys.executable, "-m", "etage0.cli", "injecter", "--section", "4.3"], env=env
)
print(f"\n--- code de sortie : {code} ---")

# --- vérifications -------------------------------------------------------- #
import yaml
strategies = yaml.safe_load((sortie / "sections" / "10-strategies.yaml").read_text(encoding="utf-8"))
slugs = {n["slug"] for n in strategies["notions"]}
attendues = {"appliquer_strategie_gloutonne", "resoudre_par_diviser_pour_regner",
             "rechercher_par_dichotomie", "resoudre_par_programmation_dynamique"}
manquantes = attendues - slugs
print("notions 4.3 attendues présentes :", "OUI" if not manquantes else f"NON {manquantes}")
print("total 10-strategies :", len(strategies["notions"]), "(15 avant)")

manifeste = yaml.safe_load((sortie / "manifest.yaml").read_text(encoding="utf-8"))
print("notions_total manifeste :", manifeste["notions_total"])
print("réparations tracées :", json.dumps(manifeste.get("reparations"), ensure_ascii=False))
print("dernier changelog :", manifeste["changelog"][-1]["operations"])

# le référentiel d'origine n'a pas bougé
avant = yaml.safe_load((RACINE / "referentiel/genere/sections/10-strategies.yaml").read_text(encoding="utf-8"))
print("referentiel/genere intact :", "OUI" if len(avant["notions"]) == 15 else "NON")
