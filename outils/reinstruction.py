"""Réinstruit les 5 techniques de preuve sur l'extraction RÉPARÉE.

La première instruction portait sur un JSON qui perdait ~30 % du texte et ne
rattachait presque aucune solution. Deux disjonctions de cas étaient tombées
avec les corrigés non extraits. On rejoue la même règle — au moins deux
fichiers distincts — sur le corpus complet.
"""
import glob, json, os, re, sys
from collections import defaultdict

os.chdir(r"c:\Users\natha\Downloads\analyse sujets")

SONDES = {
    "disjonction_cas": r"disjonction de cas|distinguer? (deux|trois|plusieurs|les) cas|on distingue (deux|trois|plusieurs|les) cas",
    "denombrement": r"\bd[ée]nombr(er|ement|ons)\b|combien (y a-t-il|de)\b",
    "encadrement": r"encadr(er|ement|ons)|double in[ée]galit[ée]",
    "famille_infinie": r"famille infinie|infinit[ée] d.(instances|exemples)|suite infinie d.(instances|exemples)",
    "echange": r"argument d.[ée]change|par [ée]change|en [ée]changeant",
}
# `dénombrable` (countability) n'est PAS `dénombrer` : la sonde initiale
# comptait 4 faux positifs sur 6 et aurait admis la notion à tort.
ANTI = {"denombrement": re.compile(r"d[ée]nombrable", re.I)}


def zones():
    for f in sorted(glob.glob("corpus/*.json")):
        d = json.load(open(f, encoding="utf-8"))
        for e in d["exercices"]:
            yield d["fichier"], f"{e['titre'][:30]} (préambule)", e["preambule"]
            if e["corrige_non_attribue"]:
                yield d["fichier"], f"{e['titre'][:30]} (corrigé)", e["corrige_non_attribue"]
            for q in e["questions"]:
                yield d["fichier"], f"{e['titre'][:26]} Q{q['numero']}", q["texte"]
                if q["solution"]:
                    yield d["fichier"], f"{e['titre'][:26]} Q{q['numero']} [sol]", q["solution"]


ZONES = list(zones())
print(f"{len(ZONES)} zones de texte sur {len(set(z[0] for z in ZONES))} fichiers\n")

for nom, motif in SONDES.items():
    rx = re.compile(motif, re.I)
    par_fichier = defaultdict(list)
    for fichier, origine, texte in ZONES:
        m = rx.search(texte or "")
        if not m:
            continue
        anti = ANTI.get(nom)
        extrait = " ".join(texte[max(0, m.start() - 80): m.end() + 80].split())
        if anti and anti.search(extrait):
            continue
        par_fichier[fichier].append((origine, extrait))
    n = len(par_fichier)
    verdict = "ADMISE" if n >= 2 else "refusée"
    print(f"{'=' * 78}\n{nom}  —  {n} fichier(s) distinct(s)  →  {verdict}")
    for fichier, hits in sorted(par_fichier.items()):
        print(f"  [{fichier}] {len(hits)} zone(s)")
        for origine, extrait in hits[:2]:
            print(f"      {origine}")
            print(f"        …{extrait[:150]}…")
