"""Migre referentiel/genere/sections vers les renvois typés (voir / voir_type / voir_brut).

Le texte d'origine du renvoi (`voir_slug`) a été perdu à l'écriture : les renvois
morts avaient été écrits `voir: null`, indiscernables des renvois légitimement
nuls. On le récupère depuis le journal, qui garde les réponses brutes du modèle.
"""
import json, glob, os, sys, shutil
from collections import defaultdict
from pathlib import Path

os.chdir(r"c:\Users\natha\Downloads\analyse sujets")
sys.path.insert(0, ".")
import yaml
from etage0.config import Profil
from etage0.referentiel import TYPE_NOTION, TYPE_SECTION

APPLIQUER = "--appliquer" in sys.argv

profil = Profil.charger(Path("profils/informatique-mpi.yaml"))
sections = set(profil.ids_sections_cibles)

# slug -> {motif: voir_slug} d'après le journal
journal = defaultdict(dict)
for line in open(".etage0/journal.jsonl", encoding="utf-8"):
    d = json.loads(line)
    if not d["etiquette"].startswith("notions/"):
        continue
    for dec in d["charge"].get("decisions") or []:
        for n in dec.get("notions") or []:
            for ex in n.get("exclusions") or []:
                journal[n["slug"]][ex.get("motif")] = ex.get("voir_slug")

fichiers = sorted(glob.glob("referentiel/genere/sections/*.yaml"))
docs = {}
slugs, ids = set(), set()
for f in fichiers:
    docs[f] = yaml.safe_load(open(f, encoding="utf-8"))
    for n in docs[f].get("notions") or []:
        slugs.add(n["slug"])
        ids.add(n["id"])

stats = defaultdict(int)
detail = []
for f, doc in docs.items():
    for n in doc.get("notions") or []:
        nouvelles = []
        for ex in n.get("exclusions") or []:
            motif = ex.get("motif")
            # priorité au journal ; à défaut, on repart de la valeur écrite
            if motif in journal.get(n["slug"], {}):
                cible = journal[n["slug"]][motif]
            else:
                cible = ex.get("voir")
                if cible:
                    cible = cible.split(".", 1)[-1]
                stats["hors_journal"] += 1

            resolue = {"motif": motif, "voir": None, "voir_type": None}
            if not cible:
                stats["nul"] += 1
            elif cible in slugs:
                resolue["voir"] = next(
                    x["id"] for d in docs.values() for x in (d.get("notions") or [])
                    if x["slug"] == cible
                )
                resolue["voir_type"] = TYPE_NOTION
                stats["notion"] += 1
            elif cible in ids:
                resolue["voir"], resolue["voir_type"] = cible, TYPE_NOTION
                stats["notion"] += 1
            elif cible in sections:
                resolue["voir"], resolue["voir_type"] = cible, TYPE_SECTION
                stats["section"] += 1
                detail.append(("SECTION", n["id"], cible))
            else:
                resolue["voir_brut"] = cible
                stats["mort"] += 1
                detail.append(("MORT", n["id"], cible))
            nouvelles.append(resolue)
        n["exclusions"] = nouvelles

print("répartition des renvois :")
for k, v in sorted(stats.items()):
    print(f"  {k:<14} {v:>4}")
print("\nà l'œil :")
for genre, source, cible in detail:
    print(f"  [{genre}] {source}  ->  {cible!r}")

if APPLIQUER:
    sauvegarde = Path(sys.argv[sys.argv.index("--sauvegarde") + 1])
    sauvegarde.mkdir(parents=True, exist_ok=True)
    for f, doc in docs.items():
        shutil.copy2(f, sauvegarde / Path(f).name)
        Path(f).write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
    print(f"\n{len(docs)} fichier(s) réécrits (sauvegardes dans {sauvegarde})")
else:
    print("\n(simulation — relancer avec --appliquer)")
