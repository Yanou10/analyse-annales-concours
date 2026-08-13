"""Sondes élargies : les motifs étroits ont produit des faux positifs."""
import sys
sys.path.insert(0, r"C:\Users\natha\AppData\Local\Temp\claude\c--Users-natha-Downloads-analyse-sujets\bc93137a-78b4-4f77-aa95-a780c3355daf\scratchpad")
import os
os.chdir(r"c:\Users\natha\Downloads\analyse sujets")
import confrontation2 as c

c.SONDES.clear()
c.SONDES.update({
    "borne_inf": (
        r"\\Omega|Ω\s*\(|tout algorithme.{0,90}(n[ée]cessite|au moins|ne peut)"
        r"|ne peut pas faire mieux|optimal(e|it[ée]) de (la|cette) borne|born[ée] inf[ée]rieurement"
        r"|nombre minimal d.(op[ée]rations|comparaisons)"
    ),
    "lecture_code": (
        r"que (fait|calcule|renvoie|retourne)|d[ée]crire (bri[èe]vement )?(ce que|l.effet|le r[ôo]le)"
        r"|interpr[ée]ter (la|le|ce)|quel est le r[ôo]le|expliquer (bri[èe]vement )?(ce que|le fonctionnement)"
    ),
    "accumulateur": (
        r"accumulateur|r[ée]cursi[fv]e? terminale|fonction interne|param[èe]tre suppl[ée]mentaire"
        r"|fonction auxiliaire"
    ),
    "preconditions": (
        r"pr[ée]condition|invariant de (la )?structure|est pr[ée]serv|pr[ée]serve l.invariant"
        r"|maintient l.invariant|reste (un |une )?(AVL|arbre binaire de recherche|tas)"
    ),
})
c.sonder(sys.argv[1], maxi=int(sys.argv[2]) if len(sys.argv) > 2 else 12)
