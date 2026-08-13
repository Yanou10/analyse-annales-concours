"""Reproduit l'échec de §4.3 et vérifie la nouvelle granularité de rejet."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
import os
os.chdir(r"c:\Users\natha\Downloads\analyse sujets")
sys.path.insert(0, r"c:\Users\natha\Downloads\analyse sujets")

from etage0 import contrats
from etage0.config import Profil
from etage0.segmentation import Section, Unite

profil = Profil.charger(Path("profils/informatique-mpi.yaml"))
section = Section(numero="4.3", titre="Décomposition", niveau=1, ligne=336, chemin=("4", "4.3"))


def unite(n):
    return Unite(
        id=f"4.3/table/{n:02d}", section=section, genre="table",
        notions="x", commentaires="y", texte="", ligne_debut=1, ligne_fin=2, semestre="S2",
    )


def notion(slug, **kw):
    base = dict(
        slug=slug, libelle=f"Faire {slug}",
        definition_operatoire="Une question qui demande explicitement de faire la chose décrite ici.",
        declencheurs=["fais ceci", "fais cela"],
        exclusions=[{"motif": "autre chose", "voir_slug": None}],
        langages_plausibles=[], origine_cellule="notions", section_cible="strategies",
    )
    base.update(kw)
    return base


unites = [unite(i) for i in range(1, 7)]
charge = {"decisions": [
    {"unite_id": "4.3/table/01", "verdict": "admis", "raison": "ok",
     "notions": [notion("appliquer_strategie_gloutonne")]},
    {"unite_id": "4.3/table/02", "verdict": "eclate", "raison": "ok",
     "notions": [notion("majorer_approximation_gloutonne")]},          # <- LA fautive
    {"unite_id": "4.3/table/03", "verdict": "eclate", "raison": "ok",
     "notions": [notion("diviser_pour_regner"), notion("rechercher_par_dichotomie")]},
    {"unite_id": "4.3/table/04", "verdict": "admis", "raison": "",     # raison vide -> réparable
     "notions": [notion("resoudre_par_programmation_dynamique")]},
    {"unite_id": "4.3/table/05", "verdict": "admis", "raison": "ok",
     "notions": [notion("Slug_Avec_Accents_Éclaté")]},                 # slug -> réparable
    {"unite_id": "4.3/table/06", "verdict": "admis", "raison": "ok",
     "notions": [notion("notion_sans_exclusions", exclusions=[])]},    # fatale -> rejet notion
]}

rapport = contrats.valider_decisions(charge, unites, profil)
print("décisions retenues :", len(rapport.decisions), "/ 6")
for d in rapport.decisions:
    print(f"  {d['unite_id']:<16} {d['verdict']:<16} {[n['slug'] for n in d['notions']]}")
print("\nréparations :")
for c in rapport.reparations:
    print(f"  [{c.code}] {c.rendu()}")
print("\nrejets :")
for c in rapport.rejets:
    print(f"  [{c.code}] {c.rendu()}")

# --- assertions ---------------------------------------------------------- #
ids = {d["unite_id"] for d in rapport.decisions}
assert len(rapport.decisions) == 5, rapport.decisions
assert "4.3/table/02" in ids, "l'unité fautive doit être conservée, normalisée"
v = {d["unite_id"]: d["verdict"] for d in rapport.decisions}
assert v["4.3/table/02"] == "admis_reformule", v
assert v["4.3/table/04"] == "admis"
assert {c.code for c in rapport.reparations} == {
    "eclate_notion_unique", "raison_vide", "slug_non_normalise"}, rapport.reparations
assert [c.code for c in rapport.rejets] == ["exclusions_absentes", "verdict_sans_notion"], rapport.rejets
# les 4 notions attendues de §4.3 survivent
survivants = {n["slug"] for d in rapport.decisions for n in d["notions"]}
for attendu in ("appliquer_strategie_gloutonne", "diviser_pour_regner",
                "rechercher_par_dichotomie", "resoudre_par_programmation_dynamique"):
    assert attendu in survivants, attendu
print("\nOK — une unité fautive n'en emporte plus cinq valides.")

# --- la charge entièrement invalide lève toujours ------------------------- #
try:
    contrats.valider_decisions(
        {"decisions": [{"unite_id": "4.3/table/01", "verdict": "admis", "raison": "x", "notions": []}]},
        unites, profil)
except contrats.ErreurContrat as err:
    print("OK — charge invalide → ErreurContrat :", str(err)[:90])
else:
    raise AssertionError("aurait dû lever")

# --- une règle réparable sans normalisation est refusée à la déclaration --- #
try:
    contrats.Regle("x", contrats.REPARABLE, lambda o, c: "boum")
except ValueError as err:
    print("OK — règle mal déclarée refusée :", err)
else:
    raise AssertionError("aurait dû lever")
