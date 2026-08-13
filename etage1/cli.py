"""Étage 1 — extraction du corpus.

    etage1 extraire *.md --sortie corpus/          # écrit un JSON par fichier
    etage1 extraire *.md --detail 2024_InfoA.md    # imprime un exercice
    etage1 verifier *.md --attendu tests/attendu.json

`verifier` est la commande qui garde la porte : elle sort en code 2 si un ratio
de conservation passe sous le seuil, parce qu'étiqueter sur une extraction
défectueuse produit des chiffres faux qu'on prendrait pour des défauts du
référentiel.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from .extraction import extraire_corpus

SEUIL_RATIO = 0.95


def _ecrire(*morceaux: str) -> None:
    print(*morceaux, file=sys.stderr, flush=True)


def _tableau(documents) -> None:
    entete = (
        f"{'fichier':<30} {'filière':<10} {'exos':>5} {'quest.':>7} "
        f"{'sol.':>5} {'fig.':>5} {'ratio':>7}"
    )
    _ecrire(entete)
    _ecrire("-" * len(entete))
    for document in documents:
        r = document.resume()
        marque = " " if r["ratio_texte_conserve"] >= SEUIL_RATIO else "✗"
        _ecrire(
            f"{r['fichier']:<30} {r['filiere']:<10} {r['exercices']:>5} "
            f"{r['questions']:>7} {r['solutions_rattachees']:>5} "
            f"{r['figures_manquantes']:>5} {r['ratio_texte_conserve']:>7.4f}{marque}"
        )
    total_q = sum(len(d.questions) for d in documents)
    total_s = sum(1 for d in documents for q in d.questions if q.solution)
    _ecrire("-" * len(entete))
    _ecrire(
        f"{'TOTAL':<30} {'':<10} {sum(len(d.exercices) for d in documents):>5} "
        f"{total_q:>7} {total_s:>5}"
    )


def cmd_extraire(args: argparse.Namespace) -> int:
    chemins = [Path(c) for c in args.fichiers]
    documents, journal = extraire_corpus(chemins, filtrer_filiere=args.filtrer_filiere)

    for ligne in journal:
        if "ÉCARTÉ" in ligne or "écarté" in ligne:
            _ecrire(f"  ! {ligne}")
    _ecrire("")
    _tableau(documents)

    if args.detail:
        cible = next((d for d in documents if d.fichier == args.detail), None)
        if cible is None:
            _ecrire(f"\n{args.detail} introuvable parmi les documents extraits")
        else:
            exercice = cible.exercices[args.exercice] if cible.exercices else None
            if exercice:
                print(f"\n{'=' * 78}\nEXERCICE {exercice.id}  (filière {exercice.filiere})")
                print(f"titre     : {exercice.titre}")
                print(f"préambule : {len(exercice.preambule)} car.")
                print(exercice.preambule[:600])
                for question in exercice.questions:
                    print(f"\n--- {question.id}  (ligne {question.ligne}"
                          f"{', figure manquante' if question.figure_manquante else ''})")
                    print(question.texte[:400])
                    if question.solution:
                        print(f"    [solution rattachée, {len(question.solution)} car.]")
                        print("    " + question.solution[:200].replace("\n", "\n    "))

    if args.sortie:
        racine = Path(args.sortie)
        racine.mkdir(parents=True, exist_ok=True)
        for document in documents:
            (racine / f"{Path(document.fichier).stem}.json").write_text(
                json.dumps(dataclasses.asdict(document), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (racine / "journal.txt").write_text("\n".join(journal), encoding="utf-8")
        _ecrire(f"\nécrit : {racine} ({len(documents)} document(s))")

    sous_seuil = [d for d in documents if d.ratio < SEUIL_RATIO]
    if sous_seuil:
        _ecrire("")
        _ecrire(
            f"⛔ {len(sous_seuil)} fichier(s) sous le seuil de conservation "
            f"{SEUIL_RATIO} — ne pas étiqueter sur cette extraction."
        )
        return 2
    return 0


def cmd_verifier(args: argparse.Namespace) -> int:
    chemins = [Path(c) for c in args.fichiers]
    documents, _ = extraire_corpus(chemins)
    _tableau(documents)

    chemin_attendu = Path(args.attendu)
    obtenu = {d.fichier: d.resume() for d in documents}
    if not chemin_attendu.is_file():
        chemin_attendu.parent.mkdir(parents=True, exist_ok=True)
        chemin_attendu.write_text(
            json.dumps(obtenu, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _ecrire(f"\n{chemin_attendu} créé depuis la mesure courante — À VÉRIFIER À LA MAIN.")
        return 0

    attendu = json.loads(chemin_attendu.read_text(encoding="utf-8"))
    ecarts = []
    for fichier, valeurs in attendu.items():
        if fichier not in obtenu:
            ecarts.append(f"{fichier} : absent de l'extraction")
            continue
        for cle, valeur in valeurs.items():
            if cle.startswith("_"):
                continue
            reel = obtenu[fichier].get(cle)
            if cle == "ratio_texte_conserve":
                if reel < valeur - 1e-6:
                    ecarts.append(f"{fichier}.{cle} : {reel} < {valeur} attendu")
            elif reel != valeur:
                ecarts.append(f"{fichier}.{cle} : {reel} au lieu de {valeur}")
    _ecrire("")
    for ecart in ecarts:
        _ecrire(f"  ✗ {ecart}")
    _ecrire(f"{len(ecarts)} écart(s) avec {chemin_attendu}")
    return 2 if ecarts else 0


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="etage1", description="Extrait exercices et questions depuis les sujets bruts."
    )
    sous = analyseur.add_subparsers(dest="commande", required=True)

    p_ext = sous.add_parser("extraire")
    p_ext.add_argument("fichiers", nargs="+")
    p_ext.add_argument("--sortie", help="dossier de sortie JSON")
    p_ext.add_argument("--detail", help="imprime un exercice de ce fichier")
    p_ext.add_argument("--exercice", type=int, default=0, help="index de l'exercice à détailler")
    p_ext.add_argument(
        "--filtrer-filiere", action="store_true",
        help="ÉCARTE les exercices d'une filière moins prioritaire (étude ciblée ; "
             "par défaut la filière est un attribut, rien n'est exclu)",
    )
    p_ext.set_defaults(fonction=cmd_extraire)

    p_ver = sous.add_parser("verifier")
    p_ver.add_argument("fichiers", nargs="+")
    p_ver.add_argument("--attendu", default="tests/attendu.json")
    p_ver.set_defaults(fonction=cmd_verifier)

    args = analyseur.parse_args(argv)
    return args.fonction(args)


if __name__ == "__main__":
    raise SystemExit(main())
