"""Réécrit l'étalon avec les identifiants réels du référentiel courant.

Substitution textuelle et non passage par yaml : l'étalon est écrit à la main,
avec des scalaires blocs, des mappings en ligne et des notes de provenance
qu'un aller-retour yaml.safe_dump aplatirait. On remplace l'identifiant partout
où il apparaît — y compris dans les `voir` et dans les prose de `perimetre`.
"""
import re, sys, glob, os, shutil
from pathlib import Path

os.chdir(r"c:\Users\natha\Downloads\analyse sujets")

# Correspondances relevées à l'œil sur la sortie de l'appariement par similarité.
# Chaque paire a été contrôlée : même action, même séance de révision.
CORRESPONDANCES = {
    # --- même section ------------------------------------------------------ #
    "preuve.induction_structurelle": "preuve.prouver_par_induction_structurelle",
    "correction.terminaison_variant": "correction.prouver_terminaison_par_variant",
    "correction.invariant": "correction.prouver_correction_partielle_par_invariant",
    "correction.jeu_de_tests": "correction.construire_jeu_tests_couverture",
    "complexite_algo.pire_cas": "complexite_algo.analyser_complexite_pire_cas",
    "complexite_algo.resolution_recurrence": "complexite_algo.resoudre_recurrence_de_cout",
    "complexite_algo.moyenne": "complexite_algo.analyser_complexite_cas_moyen",
    "complexite_algo.amorti": "complexite_algo.analyser_cout_amorti",
    "recursion.ecriture_fonction_recursive": "recursion.ecrire_fonction_recursive",
    "recursion.definition_inductive_type": "recursion.definir_ensemble_inductif_et_type",
    # --- retrouvées, mais rangées ailleurs par le générateur --------------- #
    "complexite_algo.impact_representation": "graphes_repr.choisir_representation_graphe_selon_complexite",
    "recursion.cout_pile": "ressources.analyser_cout_machine_appels_recursifs",
}

APPLIQUER = "--appliquer" in sys.argv
fichiers = sorted(glob.glob("referentiel/v1/sections/*.yaml"))
total = 0
for f in fichiers:
    texte = original = Path(f).read_text(encoding="utf-8")
    for ancien, nouveau in CORRESPONDANCES.items():
        motif = re.compile(r"(?<![\w.])" + re.escape(ancien) + r"(?![\w])")
        texte, n = motif.subn(nouveau, texte)
        if n:
            print(f"  {Path(f).name:<24} {n}x  {ancien}\n{'':26}   -> {nouveau}")
            total += n
    if APPLIQUER and texte != original:
        sauvegarde = Path(sys.argv[sys.argv.index("--sauvegarde") + 1])
        sauvegarde.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, sauvegarde / Path(f).name)
        Path(f).write_text(texte, encoding="utf-8")

print(f"\n{total} occurrence(s)" + (" réécrites" if APPLIQUER else " — simulation"))

# Vérifie qu'aucun ancien identifiant ne subsiste, y compris dans les renvois.
if APPLIQUER:
    restant = []
    for f in fichiers:
        t = Path(f).read_text(encoding="utf-8")
        for ancien in CORRESPONDANCES:
            if re.search(r"(?<![\w.])" + re.escape(ancien) + r"(?![\w])", t):
                restant.append((Path(f).name, ancien))
    print("anciens identifiants subsistants :", restant or "aucun")
