"""Confrontation v2 : cherche dans le JSON (question + corrigé + préambule)
ET dans le .md brut, pour ne pas dépendre de la qualité de l'extraction.

Ne juge rien : ramène les passages à lire, avec leur provenance.
"""
import json, re, sys
from collections import defaultdict

FICHIERS = [
    ("InfoA", "2024_InfoA"),
    ("InfoC", "2024_InfoC"),
    ("InfoU-ex", "2022_InfoU-exercices"),
    ("LCR-rap", "2022_InfoLCR-rapport"),
    ("Info-rap", "2024_Info-rapport"),
    ("TPAlgo", "2024_TPAlgo-MPI-rapport"),
]
# 2024_InfoF est identique à 2024_InfoC (34/34 questions et corrigés) : exclu.

SONDES = {
    "recurrence_numerique": r"par r[ée]currence|r[ée]currence sur|r[ée]currence forte",
    "absurde": r"par l.absurde",
    "contre_exemple": r"contre-?exemple",
    "famille_infinie": r"famille infinie|infinit[ée] d.(instances|exemples)|pour tout .{0,15}il existe un graphe",
    "disjonction_cas": r"disjonction de cas|distinguer? (deux|trois|plusieurs|les) cas",
    "denombrement": r"d[ée]nombr|combien de|cardinalit[ée] de",
    "tiroirs": r"tiroirs|pigeonhole",
    "encadrement": r"encadr(er|ement)|double in[ée]galit[ée]",
    "echange": r"argument d.[ée]change|par [ée]change",
    "double_implication": r"si et seulement si|double implication|r[ée]ciproquement",
    "induction_structurelle": r"induction structurelle|induction sur (la structure|le terme|l.arbre)",
    "TROU_espace": r"complexit[ée] (en )?(espace|spatiale|m[ée]moire)|espace m[ée]moire|occupation m[ée]moire|co[ûu]t en m[ée]moire|en m[ée]moire",
    "TROU_borne_inf": r"borne inf[ée]rieure|minorer|minoration|au moins .{0,40}(op[ée]rations|comparaisons|appels)",
    "TROU_accumulateur": r"accumulateur|r[ée]cursi[fv]e? terminale|fonction auxiliaire",
    "TROU_lecture_code": r"que (fait|calcule|renvoie|retourne) (la |cette |le |ce )?(fonction|programme|code|algorithme)|d[ée]crire ce que|sp[ée]cification de|expliquer ce que",
    "TROU_preconditions": r"pr[ée]condition|invariant de (la )?structure|est pr[ée]serv|pr[ée]serve l.invariant",
}


def zones_json(etiquette, base):
    """(origine, texte) — le préambule n'est compté qu'une fois par sujet."""
    vus = set()
    for q in json.load(open(base + ".json", encoding="utf-8")):
        label = q.get("question_label") or "?"
        sujet = (q.get("subject") or "")[:44]
        for champ in ("question_text", "solution_text"):
            if (q.get(champ) or "").strip():
                yield (f"{etiquette} {label} [{champ[:4]}] {sujet}", q[champ])
        cle = (sujet, len(q.get("subject_context") or ""))
        if cle not in vus and (q.get("subject_context") or "").strip():
            vus.add(cle)
            yield (f"{etiquette} (préambule) {sujet}", q["subject_context"])


def sonder(cible=None, contexte=110, maxi=40):
    for nom, motif in SONDES.items():
        if cible and cible not in nom:
            continue
        rx = re.compile(motif, re.I)
        par_fichier = defaultdict(list)
        md_seul = defaultdict(int)
        for etiquette, base in FICHIERS:
            for origine, texte in zones_json(etiquette, base):
                for m in rx.finditer(texte):
                    d, f = max(0, m.start() - contexte), m.end() + contexte
                    par_fichier[etiquette].append((origine, " ".join(texte[d:f].split())))
                    break  # une occurrence par zone suffit à attester
            brut = open(base + ".md", encoding="utf-8").read()
            md_seul[etiquette] = len(rx.findall(brut))
        total = sum(len(v) for v in par_fichier.values())
        print(f"\n{'=' * 78}")
        print(f"{nom}   —   {total} zone(s) · {len(par_fichier)} fichier(s) distinct(s)")
        print(f"  json : {', '.join(f'{k}={len(v)}' for k, v in sorted(par_fichier.items())) or '—'}")
        print(f"  md   : {', '.join(f'{k}={v}' for k, v in sorted(md_seul.items()) if v)or '—'}")
        if cible:
            for fichier in sorted(par_fichier):
                for origine, extrait in par_fichier[fichier][:maxi]:
                    print(f"    · {origine}")
                    print(f"        …{extrait}…")


if __name__ == "__main__":
    sonder(sys.argv[1] if len(sys.argv) > 1 else None)

SONDES.clear()
SONDES.update({
    "LARGE_borne_inf": r"\Omega|Ω\s*\(|tout algorithme.{0,90}(n[ée]cessite|au moins|ne peut)|ne peut pas faire mieux|optimal(e|it[ée]) de (la|cette) borne|born[ée] inf[ée]rieurement",
    "LARGE_lecture_code": r"que (fait|calcule|renvoie|retourne)|d[ée]crire (bri[èe]vement )?(ce que|l.effet|le r[ôo]le)|interpr[ée]ter (la|le|ce)|quel est le r[ôo]le|expliquer (bri[èe]vement )?(ce que|le fonctionnement)",
    "LARGE_accumulateur": r"accumulateur|r[ée]cursi[fv]e? terminale|en temps constant amorti|fonction interne|param[èe]tre suppl[ée]mentaire",
})
