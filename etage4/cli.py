"""Étage 4 — les ventilations.

    etage4 tout passe-complete/
    etage4 fichier passe-complete/
    etage4 zero passe-complete/ --sections-vides
    etage4 croisement passe-complete/ --champ langage --n 15
    etage4 dispersion mesure-dA/ mesure-dB/

Aucun appel, aucune écriture dans la matière : l'étage 4 lit un `etiquettes.json`
déjà produit et rend des tableaux. Toute sortie s'ouvre par le bloc de protocole
— un chiffre sans son protocole n'est pas comparable à un autre chiffre.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

from . import mesures, tableau
from .mesures import INTERVALLE_COUVERTURE_PT, SEUIL_INSTABILITE

PROTOCOLE_PAR_DEFAUT = Path("config/mesure.yaml")
REFERENTIEL_PAR_DEFAUT = Path("referentiel/genere/sections")

if hasattr(sys.stdout, "reconfigure"):  # les tableaux contiennent des accents
    sys.stdout.reconfigure(encoding="utf-8")


# --------------------------------------------------------------------------- #
# chargement
# --------------------------------------------------------------------------- #
def _resoudre(chemin: str) -> Path:
    """Accepte indifféremment un dossier de passe ou le JSON lui-même."""
    p = Path(chemin)
    if p.is_dir():
        p = p / "etiquettes.json"
    if not p.is_file():
        raise SystemExit(f"Sortie d'étiquetage introuvable : {p}")
    return p


def charger_passe(chemins: list[str]) -> tuple[list[dict], str]:
    resultats, condensat = [], hashlib.sha256()
    for chemin in chemins:
        p = _resoudre(chemin)
        octets = p.read_bytes()
        condensat.update(octets)
        resultats.extend(json.loads(octets.decode("utf-8")))
    return resultats, condensat.hexdigest()[:16]


def charger_notions(dossier: Path) -> list[dict]:
    if not dossier.is_dir():
        raise SystemExit(f"Référentiel introuvable : {dossier}")
    notions = []
    for fichier in sorted(dossier.glob("*.yaml")):
        donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
        section = (donnees.get("section") or {}).get("id")
        for notion in donnees.get("notions") or []:
            notions.append({**notion, "section_id": section})
    return notions


# --------------------------------------------------------------------------- #
# en-tête de protocole — obligatoire sur toute sortie
# --------------------------------------------------------------------------- #
def entete(protocole: dict, empreinte_passe: str, sources: list[str], notions: int) -> None:
    modele = protocole.get("modele") or {}
    etiquetage = protocole.get("etiquetage") or {}
    prefiltrage = etiquetage.get("pre_filtrage") or {}
    print("=" * 79)
    print(
        f"PROTOCOLE {protocole.get('version_protocole', '?')} "
        f"du {protocole.get('date', '?')}  ·  config/mesure.yaml"
    )
    print("=" * 79)
    print(
        f"  modèle      {modele.get('id')} · réflexion={modele.get('reflexion')} · "
        f"effort={modele.get('effort')} · max_tokens={modele.get('max_tokens')} · "
        f"température={modele.get('temperature')}"
    )
    print(
        f"  étiquetage  unité={etiquetage.get('unite_de_travail')} · "
        f"sections {prefiltrage.get('sections_min')}–{prefiltrage.get('sections_max')} "
        f"(troncature={prefiltrage.get('troncature')}) · "
        f"multi-étiquetage={etiquetage.get('multi_etiquetage')}"
    )
    print(f"  référentiel {notions} notions · sources {', '.join(sources)}")
    print(f"  empreinte   {empreinte_passe}  (sha256 des étiquettes lues)")
    for reserve in protocole.get("reserves") or []:
        print(f"  ⚠ {' '.join(reserve.split())}")
    print("=" * 79)
    print()


def charger_protocole(chemin: Path) -> dict:
    if not chemin.is_file():
        raise SystemExit(
            f"Protocole de mesure introuvable : {chemin}. "
            "Aucune mesure ne se publie sans son protocole."
        )
    return yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}


# --------------------------------------------------------------------------- #
# rendus
# --------------------------------------------------------------------------- #
def _ligne_couverture(agregat: mesures.Agregat) -> str:
    """Jamais un chiffre seul : l'intervalle EST la mesure."""
    return (
        f"couverture (statut ok) : {agregat.couverture:.1f} % "
        f"± {INTERVALLE_COUVERTURE_PT:.1f} pt — intervalle, pas une cible ; "
        f"lecture comparative uniquement"
    )


def rendre_distribution(agregat: mesures.Agregat, notions: list[dict], n: int = 10) -> None:
    print(
        f"{agregat.questions} questions · {len(agregat.exercices)} exercices · "
        f"{agregat.etiquettes} étiquettes"
    )
    print(f"moyenne d'étiquettes par question : {agregat.moyenne:.2f}")
    print(_ligne_couverture(agregat))
    print()
    print("statuts :")
    for statut, compte in agregat.statuts.most_common():
        print(f"  {str(statut):<20} {compte:>5}  {100 * compte / agregat.questions:>5.1f} %")
    for raison, compte in agregat.raisons_hors.most_common():
        print(f"    dont {str(raison):<15} {compte:>5}")
    print(
        f"  {'aucune notion':<20} {agregat.sans_notion:>5}  "
        f"{100 * agregat.sans_notion / agregat.questions:>5.1f} %"
        "   (déterministe : remplace l'ancien statut `absent_du_programme`)"
    )
    if agregat.figures_manquantes:
        print(f"  {'figure manquante':<20} {agregat.figures_manquantes:>5}   (signalé à l'extraction)")
    print()
    print(f"notions distinctes utilisées : {agregat.notions_distinctes} / {len(notions)}")
    rendre_top(agregat, n)


def rendre_top(agregat: mesures.Agregat, n: int) -> None:
    print()
    print(f"top {n} — part DES QUESTIONS et part DES OCCURRENCES")
    print("(les deux, toujours : à moyenne 1,1 étiquette/question elles diffèrent peu ;")
    print(f" à 2,0 elles racontent deux choses. Moyenne ici : {agregat.moyenne:.2f})")
    print()
    print(f"{'notion':<58}{'q':>5}{'% q':>7}{'occ':>6}{'% occ':>7}")
    print("-" * 83)
    for notion_id, compte in agregat.par_notion_questions.most_common(n):
        print(
            f"{notion_id[:58]:<58}{compte:>5}{agregat.part_questions(notion_id):>7.1f}"
            f"{agregat.par_notion_occurrences[notion_id]:>6}"
            f"{agregat.part_occurrences(notion_id):>7.1f}"
        )
    print("-" * 83)
    print(f"cumul top {n} : {agregat.cumul_occurrences(n):.1f} % des occurrences")


def rendre_croisement_simple(questions: list[dict], ligne: str, colonne: str) -> None:
    """Table de contingence entre deux champs de question."""
    from collections import Counter, defaultdict

    table: dict[str, Counter] = defaultdict(Counter)
    for question in questions:
        table[str(question.get(ligne))][str(question.get(colonne))] += 1
    valeurs = sorted({v for c in table.values() for v in c})
    print()
    print(f"croisement {ligne} × {colonne} (en questions)")
    print()
    print(f"{ligne:<12}" + "".join(f"{v[:12]:>14}" for v in valeurs) + f"{'total':>8}")
    print("-" * (12 + 14 * len(valeurs) + 8))
    for cle in sorted(table):
        compte = table[cle]
        print(f"{cle:<12}" + "".join(f"{compte.get(v, 0):>14}" for v in valeurs)
              + f"{sum(compte.values()):>8}")


def rendre_ventilation(titre: str, paquets: dict, colonne: str = "clé", tri=None) -> None:
    print(f"ventilation par {titre}")
    print()
    print(f"{colonne:<40}{'ex':>4}{'q':>6}{'étiq':>7}{'moy':>7}{'ok %':>7}{'0 not.':>8}{'notions':>9}")
    print("-" * 88)
    for cle, agregat in sorted(paquets.items(), key=tri or (lambda kv: -kv[1].questions)):
        print(
            f"{str(cle)[:40]:<40}{len(agregat.exercices):>4}{agregat.questions:>6}"
            f"{agregat.etiquettes:>7}{agregat.moyenne:>7.2f}{agregat.couverture:>7.1f}"
            f"{agregat.sans_notion:>8}{agregat.notions_distinctes:>9}"
        )
    print("-" * 88)
    print(
        f"la colonne « ok % » porte un intervalle de ± {INTERVALLE_COUVERTURE_PT:.1f} pt : "
        "n'y lire que des écarts francs."
    )


def rendre_sections(agregat: mesures.Agregat, notions: list[dict]) -> None:
    print("ventilation par section du référentiel")
    print()
    print(f"{'section':<28}{'notions util.':>14}{'/ total':>9}{'occ':>7}{'% occ':>8}")
    print("-" * 68)
    for section, utilisees, total, occurrences, part in mesures.par_section(agregat, notions):
        marque = "  ← muette" if utilisees == 0 else ""
        print(f"{section[:28]:<28}{utilisees:>14}{total:>9}{occurrences:>7}{part:>8.1f}{marque}")
    print("-" * 68)


def rendre_zero(agregat: mesures.Agregat, notions: list[dict], detail: bool) -> None:
    muettes = mesures.notions_a_zero(agregat, notions)
    total_par_section: dict[str, int] = {}
    for notion in notions:
        section = notion.get("section_id") or mesures.section_de(notion["id"])
        total_par_section[section] = total_par_section.get(section, 0) + 1

    compte = sum(len(v) for v in muettes.values())
    print(f"{compte} notion(s) sur {len(notions)} n'ont jamais été posées.")
    print()
    entieres = [s for s, v in muettes.items() if len(v) == total_par_section[s]]
    print(f"{'section':<28}{'à zéro':>8}{'/ total':>9}")
    print("-" * 45)
    for section, liste in sorted(muettes.items(), key=lambda kv: -len(kv[1])):
        pleine = " ← section entière" if section in entieres else ""
        print(f"{section[:28]:<28}{len(liste):>8}{total_par_section[section]:>9}{pleine}")
    print("-" * 45)
    if entieres:
        print()
        print(
            f"{len(entieres)} section(s) intégralement muette(s) : {', '.join(sorted(entieres))}. "
            "Une section entière à zéro n'est pas une notion isolée à zéro : c'est "
            "soit une matière absente du corpus, soit une condensation du référentiel."
        )
    if detail:
        print()
        for section, liste in sorted(muettes.items()):
            print(f"— {section} ({len(liste)}/{total_par_section[section]})")
            for notion in sorted(liste, key=lambda n: n["id"]):
                print(f"    {notion['id']}")


def rendre_croisement(questions: list[dict], agregat: mesures.Agregat, champ: str, n: int) -> None:
    tetes = [i for i, _ in agregat.par_notion_questions.most_common(n)]
    croisement = mesures.croiser(questions, champ, tetes)
    valeurs = sorted({v for c in croisement.values() for v in c})
    print(f"croisement notion × {champ} — top {n} notions")
    print()
    print(f"{'notion':<52}" + "".join(f"{str(v)[:9]:>10}" for v in valeurs) + f"{'total':>8}")
    print("-" * (52 + 10 * len(valeurs) + 8))
    for notion_id in tetes:
        compte = croisement[notion_id]
        print(
            f"{notion_id[:52]:<52}"
            + "".join(f"{compte.get(v, 0):>10}" for v in valeurs)
            + f"{sum(compte.values()):>8}"
        )


def rendre_comparaison(agregat_a, agregat_b, notions, noms, detail: bool) -> None:
    diff = mesures.comparer_couverture(agregat_a, agregat_b, notions)
    a, b = noms
    print(f"A = {a}   ·   B = {b}")
    print()
    print(f"{'':<28}{'A':>12}{'B':>12}{'Δ':>12}")
    print("-" * 64)
    for libelle, va, vb, gabarit in (
        ("questions", agregat_a.questions, agregat_b.questions, "{:.0f}"),
        ("étiquettes", agregat_a.etiquettes, agregat_b.etiquettes, "{:.0f}"),
        ("moyenne étiq./question", agregat_a.moyenne, agregat_b.moyenne, "{:.2f}"),
        ("notions utilisées", agregat_a.notions_distinctes, agregat_b.notions_distinctes, "{:.0f}"),
        ("couverture ok %", agregat_a.couverture, agregat_b.couverture, "{:.1f}"),
        ("cumul top 10 (occ. %)", agregat_a.cumul_occurrences(10), agregat_b.cumul_occurrences(10), "{:.1f}"),
    ):
        print(f"{libelle:<28}{gabarit.format(va):>12}{gabarit.format(vb):>12}"
              f"{gabarit.format(vb - va):>12}")
    print("-" * 64)
    print(
        f"la couverture porte ± {INTERVALLE_COUVERTURE_PT:.1f} pt de chaque côté : "
        "un écart sous 21 points n'est pas lisible."
    )

    print()
    print(f"{len(diff['sorties_du_zero'])} notion(s) SORTENT du zéro en B "
          f"— l'échantillon A était trop petit pour elles")
    par_section: dict[str, list[str]] = {}
    for notion_id in diff["sorties_du_zero"]:
        par_section.setdefault(diff["notions"][notion_id], []).append(notion_id)
    for section, liste in sorted(par_section.items(), key=lambda kv: -len(kv[1])):
        print(f"  {section:<24}{len(liste):>4}")
        if detail:
            for notion_id in liste:
                print(f"      {notion_id}  ({agregat_b.par_notion_questions[notion_id]} q)")

    if diff["retombees_a_zero"]:
        print()
        print(
            f"⚠ {len(diff['retombees_a_zero'])} notion(s) posée(s) en A ne le sont plus en B. "
            "Sur un corpus ÉLARGI c'est contre-intuitif : à regarder de près."
        )
        for notion_id in diff["retombees_a_zero"]:
            print(f"      {notion_id}")

    print()
    print(f"{len(diff['muettes_dans_les_deux'])} notion(s) restent muettes dans les deux passes.")
    if diff["sections_muettes_dans_les_deux"]:
        print(
            "  sections entièrement muettes des deux côtés : "
            + ", ".join(diff["sections_muettes_dans_les_deux"])
        )
        print(
            "  → une section muette sur 6 fichiers PUIS sur 39 ne s'explique plus par "
            "la taille de l'échantillon. C'est le référentiel ou le corpus qui est en cause, "
            "et le partage entre les deux se fait à la lecture des sujets, pas ici."
        )
    if diff["sections_reveillees"]:
        print(f"  sections réveillées par B : {', '.join(diff['sections_reveillees'])}")

    print()
    print("part des occurrences par section")
    print()
    print(f"{'section':<24}{'A util.':>9}{'A %':>8}{'B util.':>9}{'B %':>8}{'Δ pt':>8}")
    print("-" * 66)
    ta = {s: (u, p) for s, u, _, _, p in mesures.par_section(agregat_a, notions)}
    for section, utilisees, _, _, part in mesures.par_section(agregat_b, notions):
        ua, pa = ta.get(section, (0, 0.0))
        print(f"{section[:24]:<24}{ua:>9}{pa:>8.1f}{utilisees:>9}{part:>8.1f}{part - pa:>+8.1f}")


def rendre_dispersion(lignes: list[tuple], total: int) -> None:
    print(f"{len(lignes)} exercice(s) comparés · {total} point(s) d'écart au total")
    print()
    print(f"{'exercice':<46}{'q':>4}{'A':>5}{'B':>5}{'écart/q':>9}{'recouvr.':>10}")
    print("-" * 79)
    for par_q, _, questions, na, nb, jaccard, exercice in lignes:
        marque = " ←" if par_q >= SEUIL_INSTABILITE else ""
        print(
            f"{exercice.split('/')[-1][:46]:<46}{questions:>4}{na:>5}{nb:>5}"
            f"{par_q:>9.2f}{100 * jaccard:>9.0f}%{marque}"
        )
    instables = [l for l in lignes if l[0] >= SEUIL_INSTABILITE]
    print()
    print(
        f"{len(instables)} exercice(s) à ≥ {SEUIL_INSTABILITE} étiquette d'écart par "
        "question — à instruire en priorité, le référentiel y est à sa limite :"
    )
    for ligne in instables:
        print(f"  · {ligne[6]}")
    print()
    print(f"{sum(1 for l in lignes if l[1] <= 2)}/{len(lignes)} exercices varient de ≤ 2 étiquettes")
    if lignes:
        print(f"les 5 plus instables portent {sum(l[1] for l in lignes[:5])} des {total} points d'écart")
    couverture = [l for l in lignes if l[2]]
    if couverture:
        ecart_moyen = sum(l[0] for l in couverture) / len(couverture)
        print(f"écart moyen : {ecart_moyen:.2f} étiquette par question")


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="etage4", description="Ventilations sur une passe d'étiquetage. N'appelle rien."
    )
    analyseur.add_argument("--protocole", default=str(PROTOCOLE_PAR_DEFAUT))
    analyseur.add_argument("--referentiel", default=str(REFERENTIEL_PAR_DEFAUT))
    analyseur.add_argument("--sans-entete", action="store_true",
                           help="pour composer avec d'autres outils ; à ne pas utiliser pour publier")
    sous = analyseur.add_subparsers(dest="commande", required=True)

    for nom, aide in [
        ("distribution", "distribution globale : statuts, moyenne, couverture, top"),
        ("fichier", "ventilation par fichier de sujet"),
        ("section", "ventilation par section du référentiel"),
        ("filiere", "ventilation par filière (attribut conservé, jamais un filtre)"),
        ("annee", "ventilation par année de session"),
        ("genre", "ventilation par genre de document (recueil, rapport, épreuve pratique)"),
        ("langage", "ventilation par langage déduit de la consigne"),
        ("exercice", "ventilation par exercice"),
        ("zero", "notions jamais posées, par section"),
        ("top", "classement des notions"),
        ("croisement", "notion × un champ de question"),
        ("tout", "toutes les ventilations, dans l'ordre de lecture"),
    ]:
        p = sous.add_parser(nom, help=aide)
        p.add_argument("passe", nargs="+", help="dossier(s) de passe ou etiquettes.json")
        if nom in ("top", "distribution", "croisement", "tout"):
            p.add_argument("--n", type=int, default=10 if nom != "top" else 20)
        if nom in ("croisement", "tout"):
            p.add_argument("--champ", default="langage",
                           help="champ de question à croiser : langage, filiere, statut")
        if nom in ("zero", "tout"):
            p.add_argument("--sections-vides", action="store_true",
                           help="liste aussi chaque notion muette")

    d = sous.add_parser("dispersion", help="instabilité par exercice entre deux passes")
    d.add_argument("passes", nargs=2, metavar=("PASSE_A", "PASSE_B"))

    b = sous.add_parser(
        "dashboard",
        help="tableau de bord HTML autonome : un fichier, aucune dépendance, ouvrable hors ligne",
    )
    b.add_argument("passe", nargs="+", help="dossier(s) de passe ou etiquettes.json")
    b.add_argument("--sortie", default="tableau-de-bord.html")
    b.add_argument("--titre", default="Annales d'informatique")

    c = sous.add_parser(
        "comparer",
        help="ce qu'un corpus élargi change à la couverture : notions sorties du zéro, "
             "sections réveillées, parts par section",
    )
    c.add_argument("passes", nargs=2, metavar=("PASSE_A", "PASSE_B"))
    c.add_argument("--detail", action="store_true", help="nomme chaque notion")

    args = analyseur.parse_args(argv)
    protocole = charger_protocole(Path(args.protocole))
    notions = charger_notions(Path(args.referentiel))

    if args.commande == "dashboard":
        resultats, empreinte_passe = charger_passe(args.passe)
        data, agregat, stats = tableau.construire(resultats, notions)
        moteur = (Path(__file__).parent / "moteur.html").read_text(encoding="utf-8")
        sous = (
            f"{len(data['records'])} étiquettes sur {len(data['annees'])} années, "
            f"{len(data['epreuves'])} épreuves et {len(data['sections'])} sections, "
            f"projetées sur les {len(data['notions_officielles'])} notions du référentiel : "
            f"{len(data['notions_officielles']) - len(data['jamais_tombes'])} déjà tombées, "
            f"{len(data['jamais_tombes'])} jamais. "
            "Filtre par année, type, épreuve, langage ou section ; trie la carte de chaleur."
        )
        modele = (protocole.get("modele") or {}).get("id")
        pied = (
            "Produit par <span class=\"mono\">etage4 dashboard</span> — aucun appel de modèle, "
            "aucune dépendance externe, ouvrable hors ligne. "
            f"Protocole {protocole.get('version_protocole')} · {modele} · "
            f"empreinte {empreinte_passe} · sources : {', '.join(args.passe)}."
        )
        bloc_data = "<script>\nconst DATA = " + tableau.serialiser(data) + ";\n</script>"
        page = (
            moteur
            .replace("<script>__DATA_PLACEHOLDER__</script>", bloc_data)
            .replace("__PIED_PLACEHOLDER__", pied)
        )
        page = re.sub(r"(<h1>).*?(</h1>)", lambda m: m.group(1) + args.titre + m.group(2),
                      page, count=1, flags=re.DOTALL)
        page = re.sub(r'(<p class="sub">).*?(</p>)', lambda m: m.group(1) + sous + m.group(2),
                      page, count=1, flags=re.DOTALL)

        destination = Path(args.sortie)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(page, encoding="utf-8")
        print(f"écrit : {destination}  ({destination.stat().st_size / 1024:.0f} Ko)")
        print(f"  exercices lus        : {len(resultats)}")
        print(f"  questions            : {stats['questions']}")
        print(f"  questions sans tag   : {stats['questions_sans_etiquette']}")
        print(f"  étiquettes (records) : {stats['etiquettes']}")
        print(f"  référentiel          : {len(notions)} notions "
              f"({len(data['jamais_tombes'])} jamais attribuées)")
        print(f"  couverture           : {agregat.couverture:.1f} % "
              f"± {INTERVALLE_COUVERTURE_PT} pt")
        return 0

    if args.commande == "comparer":
        a, empreinte_a = charger_passe([args.passes[0]])
        b, empreinte_b = charger_passe([args.passes[1]])
        if not args.sans_entete:
            entete(protocole, f"{empreinte_a}/{empreinte_b}", list(args.passes), len(notions))
        agregat_a = mesures.agreger(mesures.aplatir(a))
        agregat_b = mesures.agreger(mesures.aplatir(b))
        rendre_comparaison(agregat_a, agregat_b, notions, args.passes, args.detail)
        return 0

    if args.commande == "dispersion":
        a, empreinte_a = charger_passe([args.passes[0]])
        b, empreinte_b = charger_passe([args.passes[1]])
        if not args.sans_entete:
            entete(protocole, f"{empreinte_a}/{empreinte_b}", list(args.passes), len(notions))
        lignes, total = mesures.dispersion(a, b)
        if not lignes:
            print("aucun exercice commun aux deux passes")
            return 2
        rendre_dispersion(lignes, total)
        return 0

    resultats, empreinte_passe = charger_passe(args.passe)
    questions = mesures.aplatir(resultats)
    if not questions:
        print("aucune question étiquetée")
        return 2
    agregat = mesures.agreger(questions)
    if not args.sans_entete:
        entete(protocole, empreinte_passe, list(args.passe), len(notions))

    n = getattr(args, "n", 10)
    if args.commande == "distribution":
        rendre_distribution(agregat, notions, n)
    elif args.commande == "top":
        rendre_top(agregat, n)
    elif args.commande == "fichier":
        rendre_ventilation("fichier", mesures.ventiler(questions, lambda q: q["fichier"]), "fichier")
    elif args.commande == "filiere":
        rendre_ventilation("filière", mesures.ventiler(questions, lambda q: q["filiere"]), "filière")
    elif args.commande == "genre":
        rendre_ventilation("genre", mesures.ventiler(questions, lambda q: q["genre"]), "genre")
    elif args.commande == "annee":
        rendre_ventilation("année", mesures.ventiler(questions, lambda q: q["annee"]), "année",
                           tri=lambda kv: kv[0])
        rendre_croisement_simple(questions, "annee", "filiere")
    elif args.commande == "langage":
        rendre_ventilation("langage", mesures.ventiler(questions, lambda q: q["langage"]), "langage")
    elif args.commande == "exercice":
        rendre_ventilation("exercice", mesures.ventiler(questions, lambda q: q["exercice_id"]), "exercice")
    elif args.commande == "section":
        rendre_sections(agregat, notions)
    elif args.commande == "zero":
        rendre_zero(agregat, notions, args.sections_vides)
    elif args.commande == "croisement":
        rendre_croisement(questions, agregat, args.champ, n)
    elif args.commande == "tout":
        blocs = [
            ("DISTRIBUTION GLOBALE", lambda: rendre_distribution(agregat, notions, n)),
            ("PAR FICHIER", lambda: rendre_ventilation(
                "fichier", mesures.ventiler(questions, lambda q: q["fichier"]), "fichier")),
            ("PAR SECTION", lambda: rendre_sections(agregat, notions)),
            ("PAR FILIÈRE", lambda: rendre_ventilation(
                "filière", mesures.ventiler(questions, lambda q: q["filiere"]), "filière")),
            ("PAR ANNÉE", lambda: (
                rendre_ventilation("année", mesures.ventiler(questions, lambda q: q["annee"]),
                                   "année", tri=lambda kv: kv[0]),
                rendre_croisement_simple(questions, "annee", "filiere"))),
            ("PAR LANGAGE", lambda: rendre_ventilation(
                "langage", mesures.ventiler(questions, lambda q: q["langage"]), "langage")),
            ("NOTIONS À ZÉRO", lambda: rendre_zero(agregat, notions, args.sections_vides)),
            ("TOP 20", lambda: rendre_top(agregat, 20)),
            (f"CROISEMENT NOTION × {args.champ.upper()}",
             lambda: rendre_croisement(questions, agregat, args.champ, n)),
        ]
        for titre, rendu in blocs:
            print()
            print("─" * 79)
            print(titre)
            print("─" * 79)
            rendu()
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
