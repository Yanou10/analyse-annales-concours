"""Annule l'injection de §4.3 pour la rejouer avec l'écriture des refus."""
import os, yaml
from pathlib import Path

os.chdir(r"c:\Users\natha\Downloads\analyse sujets")
IDS = {
    "strategies.concevoir_glouton_exact",
    "strategies.analyser_glouton_approximation",
    "strategies.concevoir_diviser_pour_regner",
    "strategies.rechercher_par_dichotomie",
    "strategies.appliquer_rencontre_au_milieu",
    "strategies.concevoir_algorithme_programmation_dynamique",
    "strategies.implementer_dp_ascendante_ou_memoisation",
    "strategies.reconstruire_solution_optimale",
}

f = Path("referentiel/genere/sections/10-strategies.yaml")
d = yaml.safe_load(f.read_text(encoding="utf-8"))
avant = len(d["notions"])
d["notions"] = [n for n in d["notions"] if n["id"] not in IDS]
f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
print(f"10-strategies : {avant} -> {len(d['notions'])}")

m = Path("referentiel/genere/manifest.yaml")
man = yaml.safe_load(m.read_text(encoding="utf-8"))
man["changelog"] = [
    c for c in man["changelog"]
    if not any("régénérée seule et injectée" in o for o in c["operations"])
]
man["unites_rejetees"] = [
    r for r in man.get("unites_rejetees") or [] if r.get("section") != "4.3"
]
for e in man["sections"]:
    e["notions"] = len(
        yaml.safe_load((Path("referentiel/genere") / e["fichier"]).read_text(encoding="utf-8")).get("notions") or []
    )
man["notions_total"] = sum(e["notions"] for e in man["sections"])
m.write_text(yaml.safe_dump(man, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
print("manifeste notions_total :", man["notions_total"], "· changelog :", len(man["changelog"]), "entrée(s)")
