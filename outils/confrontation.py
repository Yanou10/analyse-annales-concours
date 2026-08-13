"""Harnais de confrontation : retrouve les attestations, ne juge pas.

Le jugement se fait à la lecture des extraits. Ce script ne fait que ramener
les passages à lire, avec leur provenance, pour qu'aucune affirmation du
rapport ne repose sur un simple comptage de mots-clés.
"""
import json, re, sys
from collections import defaultdict

# InfoF est identique à InfoC (34/34 questions et solutions) : l'inclure
# ferait passer toute attestation d'InfoC pour une double attestation.
FICHIERS = [
    ("InfoA", "2024_InfoA.json"),
    ("InfoC", "2024_InfoC.json"),
    ("InfoU-ex", "2022_InfoU-exercices.json"),
    ("LCR-rap", "2022_InfoLCR-rapport.json"),
    ("Info-rap", "2024_Info-rapport.json"),
    ("TPAlgo", "2024_TPAlgo-MPI-rapport.json"),
]

SONDES = {
    # --- techniques de preuve ------------------------------------------- #
    "preuve.recurrence_numerique": r"par r[ée]currence|r[ée]currence sur",
    "preuve.absurde": r"par l.absurde|absurde",
    "preuve.contre_exemple_unique": r"contre-?exemple",
    "preuve.famille_infinie_contre_exemples": r"famille infinie|infinit[ée] d.(instances|exemples)",
    "preuve.disjonction_cas": r"disjonction de cas|distinguer? (deux|trois|plusieurs|les) cas|selon que",
    "preuve.denombrement": r"d[ée]nombr|combien de|cardinalit[ée]",
    "preuve.tiroirs": r"tiroirs|pigeonhole",
    "preuve.encadrement_double": r"encadr(er|ement)|double in[ée]galit[ée]",
    "preuve.echange": r"argument d.[ée]change|par [ée]change",
    "preuve.double_implication": r"si et seulement si|double implication|r[ée]ciproquement",
    "preuve.induction_structurelle": r"induction structurelle|par induction",
    # --- les cinq trous nommés ------------------------------------------- #
    "TROU complexite_algo.espace": r"complexit[ée] (en )?(espace|spatiale|m[ée]moire)|espace m[ée]moire|occupation m[ée]moire|en m[ée]moire",
    "TROU complexite_algo.borne_inferieure": r"borne inf[ée]rieure|minorer|minoration",
    "TROU recursion.accumulateur_auxiliaire": r"accumulateur|r[ée]cursi[fv]e? terminale|fonction auxiliaire",
    "TROU correction.lecture_de_code": r"que (fait|calcule|renvoie|retourne) (la |cette |le |ce )?(fonction|programme|code|algorithme)|d[ée]crire ce que|sp[ée]cification de",
    "TROU correction.preconditions_preservees": r"pr[ée]condition|invariant de (la )?structure|est pr[ée]serv",
}


def charger():
    corpus = []
    for etiquette, chemin in FICHIERS:
        for q in json.load(open(chemin, encoding="utf-8")):
            corpus.append(
                {
                    "fichier": etiquette,
                    "sujet": q.get("subject") or "",
                    "label": q.get("question_label") or "",
                    "texte": (q.get("question_text") or ""),
                }
            )
    return corpus


def sonder(corpus, cible=None, contexte=90, maxi=6):
    for nom, motif in SONDES.items():
        if cible and cible not in nom:
            continue
        rx = re.compile(motif, re.I)
        par_fichier = defaultdict(list)
        for q in corpus:
            m = rx.search(q["texte"])
            if m:
                d, f = max(0, m.start() - contexte), m.end() + contexte
                par_fichier[q["fichier"]].append(
                    (q["label"], q["sujet"][:40], " ".join(q["texte"][d:f].split()))
                )
        total = sum(len(v) for v in par_fichier.values())
        print(f"\n{'=' * 78}\n{nom}\n  {total} question(s) · {len(par_fichier)} fichier(s) : "
              f"{', '.join(f'{k}={len(v)}' for k, v in sorted(par_fichier.items()))}")
        if cible:
            for fichier, hits in sorted(par_fichier.items()):
                for label, sujet, extrait in hits[:maxi]:
                    print(f"    [{fichier}] {label} — {sujet}")
                    print(f"        …{extrait}…")


if __name__ == "__main__":
    corpus = charger()
    print(f"{len(corpus)} questions sur {len(FICHIERS)} fichiers distincts")
    for etiquette, _ in FICHIERS:
        print(f"  {etiquette:<10} {sum(1 for q in corpus if q['fichier'] == etiquette)}")
    sonder(corpus, cible=sys.argv[1] if len(sys.argv) > 1 else None)
