"""Chargement des JSON de la chaîne dans Postgres. Idempotent et rejouable.

    annales-import --corpus /travail/corpus --referentiel referentiel/genere/sections \
                   --etiquettes /travail/passe-39 --passe passe-39 \
                   --protocole config/mesure.yaml

Rien n'est recalculé ici : l'import RECOPIE ce que les étages ont produit. Une
transformation au chargement finirait par faire dire à la base autre chose qu'à
`etage4 distribution`, sans que rien ne le signale.

Trois choix suivent le schéma, et chacun sert la reprise :

- `documents.empreinte` étant UNIQUE, un ré-import du même document **met à
  jour** au lieu d'échouer. La contrainte reste le garde-fou de déduplication ;
  elle ne devient pas un obstacle à rejouer.
- les étiquettes portent `(question_id, notion_id, passe)` : réimporter une
  passe la remplace, réimporter une AUTRE passe s'ajoute à côté.
- tout passe dans UNE transaction. Un import interrompu ne laisse pas la base à
  moitié chargée — on relance, point.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

#: Colonnes attendues par table. Vérifiées AVANT toute écriture : un import qui
#: échoue à la 1 800ᵉ ligne sur une colonne absente est une perte de temps.
ATTENDU: dict[str, tuple[str, ...]] = {
    "documents": ("id", "fichier", "empreinte", "filiere", "niveau_exercice",
                  "caracteres_source", "caracteres_bruit", "ratio_extraction"),
    "exercices": ("id", "document_id", "titre", "niveau", "filiere", "preambule",
                  "corrige_non_attribue", "ligne", "rang"),
    "questions": ("id", "exercice_id", "numero", "texte", "solution",
                  "figure_manquante", "ligne"),
    "notions": ("id", "section_id", "libelle", "definition"),
    "passes": ("id", "signature", "source", "protocole"),
    "etiquettes": ("question_id", "notion_id", "passe", "justification", "statut", "langage"),
}

CLES = {
    "documents": ("empreinte",),
    "exercices": ("id",),
    "questions": ("id",),
    "notions": ("id",),
    "passes": ("id",),
    "etiquettes": ("question_id", "notion_id", "passe"),
}


def _connexion(url: str):
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        raise SystemExit(
            "psycopg absent. Installer les dépendances du service :\n"
            "    pip install '.[service]'"
        ) from None
    return psycopg.connect(url, autocommit=False)


def verifier_schema(curseur) -> None:
    """Compare la base réelle au schéma attendu et refuse en nommant les écarts."""
    curseur.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema()"
    )
    reel: dict[str, set[str]] = {}
    for table, colonne in curseur.fetchall():
        reel.setdefault(table, set()).add(colonne)

    ecarts: list[str] = []
    for table, colonnes in ATTENDU.items():
        if table not in reel:
            ecarts.append(f"table absente : {table}")
            continue
        manquantes = [c for c in colonnes if c not in reel[table]]
        if manquantes:
            ecarts.append(f"{table} : colonnes absentes {', '.join(manquantes)}")
    if ecarts:
        raise SystemExit(
            "Le schéma de la base ne correspond pas à celui attendu :\n  "
            + "\n  ".join(ecarts)
            + "\n\nCréer ou aligner le schéma avec `--creer-schema` "
              "(voir service/schema.sql)."
        )


def _upsert(curseur, table: str, lignes: list[dict[str, Any]]) -> int:
    if not lignes:
        return 0
    colonnes = [c for c in ATTENDU[table] if any(c in ligne for ligne in lignes)]
    cles = CLES[table]
    majuscules = [c for c in colonnes if c not in cles]
    ordre = ", ".join(colonnes)
    trous = ", ".join(["%s"] * len(colonnes))
    conflit = ", ".join(cles)
    if majuscules:
        action = "DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in majuscules)
    else:
        action = "DO NOTHING"
    requete = (
        f"INSERT INTO {table} ({ordre}) VALUES ({trous}) "
        f"ON CONFLICT ({conflit}) {action}"
    )
    curseur.executemany(requete, [[ligne.get(c) for c in colonnes] for ligne in lignes])
    return len(lignes)


# --------------------------------------------------------------------------- #
# lecture des sorties de la chaîne
# --------------------------------------------------------------------------- #
def _fichiers(motif: str) -> list[Path]:
    chemin = Path(motif)
    if chemin.is_dir():
        return sorted(chemin.glob("*.json"))
    return [Path(p) for p in sorted(glob.glob(motif))]


def lire_corpus(dossier: str) -> tuple[list[dict], list[dict], list[dict]]:
    documents, exercices, questions = [], [], []
    for fichier in _fichiers(dossier):
        donnees = json.loads(fichier.read_text(encoding="utf-8"))
        documents.append({
            "id": donnees["fichier"],
            "fichier": donnees["fichier"],
            "empreinte": donnees["empreinte"],
            "filiere": donnees.get("filiere"),
            "niveau_exercice": donnees.get("niveau_exercice"),
            "caracteres_source": donnees.get("caracteres_source"),
            "caracteres_bruit": donnees.get("caracteres_bruit"),
            "ratio_extraction": donnees.get("ratio_extraction"),
        })
        # Douze exercices partagent leur identifiant avec un autre du même
        # fichier. `rang` les sépare, et l'identifiant stocké devient unique —
        # sinon l'import en écraserait onze en silence.
        vus: dict[str, int] = {}
        for exercice in donnees.get("exercices") or []:
            brut = exercice["id"]
            rang = vus.get(brut, 0)
            vus[brut] = rang + 1
            identifiant = brut if rang == 0 else f"{brut}~{rang + 1}"
            exercices.append({
                "id": identifiant,
                "document_id": donnees["fichier"],
                "titre": exercice.get("titre"),
                "niveau": exercice.get("niveau"),
                "filiere": exercice.get("filiere"),
                "preambule": exercice.get("preambule"),
                "corrige_non_attribue": exercice.get("corrige_non_attribue"),
                "ligne": exercice.get("ligne"),
                "rang": rang + 1,
            })
            for question in exercice.get("questions") or []:
                suffixe = question["id"].split("#", 1)[-1]
                questions.append({
                    "id": f"{identifiant}#{suffixe}",
                    "exercice_id": identifiant,
                    "numero": str(question.get("numero")),
                    "texte": question.get("texte"),
                    "solution": question.get("solution"),
                    "figure_manquante": bool(question.get("figure_manquante")),
                    "ligne": question.get("ligne"),
                })
    return documents, exercices, questions


def lire_notions(dossier: str) -> list[dict]:
    notions = []
    for fichier in sorted(Path(dossier).glob("*.yaml")):
        donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
        section = (donnees.get("section") or {}).get("id")
        for notion in donnees.get("notions") or []:
            notions.append({
                "id": notion["id"],
                "section_id": section or notion["id"].split(".", 1)[0],
                "libelle": notion.get("libelle"),
                "definition": notion.get("definition"),
            })
    return notions


def lire_etiquettes(dossier: str, passe: str) -> list[dict]:
    chemin = Path(dossier)
    if chemin.is_dir():
        chemin = chemin / "etiquettes.json"
    resultats = json.loads(chemin.read_text(encoding="utf-8"))
    lignes, vus = [], {}
    for resultat in resultats:
        brut = resultat["exercice_id"]
        rang = vus.get(brut, 0)
        vus[brut] = rang + 1
        exercice = brut if rang == 0 else f"{brut}~{rang + 1}"
        for question in resultat.get("questions") or []:
            suffixe = question["question_id"].split("#", 1)[-1]
            for etiquette in question.get("etiquettes") or []:
                lignes.append({
                    "question_id": f"{exercice}#{suffixe}",
                    "notion_id": etiquette["notion_id"],
                    "passe": passe,
                    "justification": etiquette.get("justification"),
                    "statut": question.get("statut"),
                    "langage": question.get("langage"),
                })
    return lignes


def _dedoublonner(lignes: list[dict], cles: Iterable[str]) -> list[dict]:
    """Dernier gagne. `executemany` ne tolère pas deux fois la même clé dans le
    MÊME lot : Postgres refuse d'appliquer deux `ON CONFLICT` sur une ligne."""
    unique: dict[tuple, dict] = {}
    for ligne in lignes:
        unique[tuple(ligne[c] for c in cles)] = ligne
    return list(unique.values())


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="annales-import",
        description="Charge les sorties de la chaîne dans Postgres. Idempotent.",
    )
    analyseur.add_argument("--url", default=os.environ.get("DATABASE_URL"),
                           help="URL Postgres (défaut : $DATABASE_URL)")
    analyseur.add_argument("--corpus", help="dossier des JSON de l'étage 1")
    analyseur.add_argument("--referentiel", help="dossier referentiel/genere/sections")
    analyseur.add_argument("--etiquettes", help="dossier de passe, ou etiquettes.json")
    analyseur.add_argument("--passe", help="identifiant de la passe (obligatoire avec --etiquettes)")
    analyseur.add_argument("--protocole", default="config/mesure.yaml",
                           help="YAML écrit tel quel dans passes.protocole (JSONB)")
    analyseur.add_argument("--signature", help="signature de protocole, si connue")
    analyseur.add_argument("--creer-schema", action="store_true",
                           help="applique service/schema.sql avant l'import")
    analyseur.add_argument("--verifier-seulement", action="store_true",
                           help="contrôle le schéma et sort, sans rien écrire")
    args = analyseur.parse_args(argv)

    if not args.url:
        raise SystemExit("URL Postgres absente : passer --url ou définir DATABASE_URL.")
    if args.etiquettes and not args.passe:
        raise SystemExit("--etiquettes exige --passe (identifiant de la passe).")

    with _connexion(args.url) as connexion:
        with connexion.cursor() as curseur:
            if args.creer_schema:
                curseur.execute((Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))
                print("schéma appliqué depuis service/schema.sql")
            verifier_schema(curseur)
            if args.verifier_seulement:
                print("schéma conforme")
                return 0

            comptes: dict[str, int] = {}
            if args.corpus:
                documents, exercices, questions = lire_corpus(args.corpus)
                comptes["documents"] = _upsert(
                    curseur, "documents", _dedoublonner(documents, ("empreinte",)))
                comptes["exercices"] = _upsert(
                    curseur, "exercices", _dedoublonner(exercices, ("id",)))
                comptes["questions"] = _upsert(
                    curseur, "questions", _dedoublonner(questions, ("id",)))
            if args.referentiel:
                comptes["notions"] = _upsert(
                    curseur, "notions", _dedoublonner(lire_notions(args.referentiel), ("id",)))
            if args.etiquettes:
                protocole = {}
                chemin = Path(args.protocole)
                if chemin.is_file():
                    protocole = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
                _upsert(curseur, "passes", [{
                    "id": args.passe,
                    "signature": args.signature,
                    "source": str(args.etiquettes),
                    "protocole": json.dumps(protocole, ensure_ascii=False),
                }])
                comptes["etiquettes"] = _upsert(
                    curseur, "etiquettes",
                    _dedoublonner(lire_etiquettes(args.etiquettes, args.passe),
                                  ("question_id", "notion_id", "passe")),
                )
        connexion.commit()

    for table, nombre in comptes.items():
        print(f"  {table:<12} {nombre:>6} ligne(s)")
    print("import terminé — rejouable à l'identique")
    return 0


if __name__ == "__main__":
    sys.exit(main())
