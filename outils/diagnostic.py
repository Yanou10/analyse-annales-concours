"""Trois diagnostics : cibles mortes, faux positif d'appariement, non appariés de l'étalon."""
import glob, json, os, sys
from pathlib import Path

os.chdir(r"c:\Users\natha\Downloads\analyse sujets")
sys.path.insert(0, ".")
import yaml
from etage0 import referentiel as ref

notions = ref.charger_notions(Path("referentiel/genere/sections"))
index = {n["id"]: n for n in notions}

print("=" * 78)
print("A. LES DEUX CIBLES MORTES : existent-elles ailleurs, sous un autre nom ?")
print("=" * 78)
for cible in ["definir_type_donnees_pour_modeliser", "definir_types_mutuellement_recursifs"]:
    print(f"\ncible morte : {cible!r}")
    scores = sorted(
        (
            (ref._similarite(n["libelle"], n["id"], cible.replace("_", " "), cible), n["id"], n["libelle"])
            for n in notions
        ),
        reverse=True,
    )[:4]
    for s, i, lib in scores:
        print(f"   {s:.2f}  {i}")
        print(f"         {lib}")

# la cible existait-elle dans le journal (donc purgée) ?
print("\n" + "-" * 78)
print("présence dans le journal (les 213 notions brutes, avant purge) :")
journal = {}
for line in open(".etage0/journal.jsonl", encoding="utf-8"):
    d = json.loads(line)
    if not d["etiquette"].startswith("notions/"):
        continue
    for dec in d["charge"].get("decisions") or []:
        for n in dec.get("notions") or []:
            journal[n["slug"]] = (d["etiquette"], n.get("section_cible"), n["libelle"])
for cible in ["definir_type_donnees_pour_modeliser", "definir_types_mutuellement_recursifs"]:
    e = journal.get(cible)
    print(f"  {cible:<40} {'PRÉSENTE ' + str(e[:2]) if e else 'ABSENTE du journal aussi'}")
    if e:
        print(f"      libellé : {e[2]}")

print("\n" + "=" * 78)
print("B. LE FAUX POSITIF À 0,65 — détail des deux notions")
print("=" * 78)
etalon = {}
for f in sorted(glob.glob("referentiel/v1/sections/*.yaml")):
    d = yaml.safe_load(open(f, encoding="utf-8"))
    for n in d.get("notions") or []:
        etalon[n["id"]] = (d["section"]["id"], n)
sec, n = etalon["preuve.double_implication"]
print(f"ÉTALON  {n['id']}  (section {sec})")
print(f"  libellé    : {n['libelle']}")
print(f"  définition : {' '.join(n['definition_operatoire'].split())[:300]}")
o = index["graphes_algo.resoudre_2sat_par_implications"]
print(f"\nRÉFÉRENTIEL  {o['id']}")
print(f"  libellé    : {o['libelle']}")
print(f"  définition : {' '.join(o['definition_operatoire'].split())[:300]}")

print("\n" + "=" * 78)
print("C. LES NON APPARIÉS DE L'ÉTALON, avec leur plus proche voisin")
print("=" * 78)
mesure = ref.comparer_etalon(ref.Referentiel(notions=notions), Path("referentiel/v1/sections"))
manquants = [i for d in mesure["detail"].values() for i in d["manquants"]]
for identifiant in manquants:
    sec, n = etalon[identifiant]
    meilleurs = sorted(
        (
            (ref._similarite(n["libelle"], n["id"], o["libelle"], o["id"]), o["id"], o["libelle"])
            for o in notions
        ),
        reverse=True,
    )[:2]
    print(f"\n{identifiant}   (section {sec})")
    print(f"   étalon : {n['libelle']}")
    for s, i, lib in meilleurs:
        print(f"   {s:.2f}  {i}")
        print(f"          {lib}")
