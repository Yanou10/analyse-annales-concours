"""Récupère les `voir_slug` d'origine depuis le journal et mesure leur résolution."""
import json, sys, glob, os
from collections import defaultdict
os.chdir(r"c:\Users\natha\Downloads\analyse sujets")
sys.path.insert(0, ".")
import yaml
from etage0.config import Profil
from pathlib import Path

profil = Profil.charger(Path("profils/informatique-mpi.yaml"))
sections = set(profil.ids_sections_cibles)

# --- ce que le modèle avait dit ------------------------------------------- #
# slug -> liste de (motif, voir_slug)
journal_par_slug = defaultdict(list)
for line in open(".etage0/journal.jsonl", encoding="utf-8"):
    d = json.loads(line)
    if not d["etiquette"].startswith("notions/"):
        continue
    for dec in d["charge"].get("decisions") or []:
        for n in dec.get("notions") or []:
            for ex in n.get("exclusions") or []:
                journal_par_slug[n["slug"]].append((ex.get("motif"), ex.get("voir_slug")))

# --- ce qui est sur disque ------------------------------------------------ #
disque = {}
for f in sorted(glob.glob("referentiel/genere/sections/*.yaml")):
    d = yaml.safe_load(open(f, encoding="utf-8"))
    for n in d.get("notions") or []:
        disque[n["slug"]] = n
ids_disque = {n["id"] for n in disque.values()}
slugs_disque = set(disque)

print(f"notions disque : {len(disque)} · notions journal : {len(journal_par_slug)}")
print(f"slugs disque absents du journal : {sorted(slugs_disque - set(journal_par_slug))[:10]}")

# --- résolution des voir_slug --------------------------------------------- #
morts, vers_section, ok, nuls = [], [], 0, 0
for slug, n in disque.items():
    for motif, cible in journal_par_slug.get(slug, []):
        if not cible:
            nuls += 1
        elif cible in slugs_disque:
            ok += 1
        elif cible in ids_disque:
            ok += 1
        elif cible in sections:
            vers_section.append((n["id"], cible, motif))
        else:
            morts.append((n["id"], cible, motif))

print(f"\nrenvois résolus vers une notion : {ok}")
print(f"renvois nuls (aucune notion ne couvre) : {nuls}")
print(f"renvois vers une SECTION : {len(vers_section)}")
for i, c, m in vers_section:
    print(f"  {i}\n      -> {c!r}  ({m[:70]})")
print(f"\nrenvois MORTS : {len(morts)}")
for i, c, m in morts:
    print(f"  {i}\n      -> {c!r}  ({m[:70]})")
