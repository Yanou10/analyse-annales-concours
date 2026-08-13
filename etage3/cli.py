"""Étage 3 — corpus extrait + référentiel → étiquettes.

    etage3 etiqueter corpus/2024_InfoA.json --dry-run
    etage3 etiqueter corpus/2024_InfoA.json --sortie etiquettes/
    etage3 etiqueter corpus/*.json --sortie etiquettes/

`--dry-run` remplace la répétition sur modèle local : il montre les deux
prompts exacts et les deux schémas d'outil, sans joindre le moindre service.
C'est là que se trouvent les erreurs de plomberie, et il ne coûte rien.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import yaml

from etage0.config import Config
from etage0.fournisseurs import ErreurFournisseur, RefusModele, construire as construire_fournisseur
from etage0.journal import Journal, empreinte

from . import contrats
from .contrats import MAX_SECTIONS, MIN_SECTIONS
from .etiquetage import (
    charger_corpus,
    charger_exclusions,
    charger_referentiel,
    valider_etiquettes,
)


#: Sections de `config/mesure.yaml` qui DÉTERMINENT la réponse du modèle, par
#: opposition à celles qui la commentent (`reproductibilite`, `reserves`, les
#: empreintes). Elles entrent dans la signature de journal par construction :
#: c'est la troisième fois qu'une signature incomplète menace la validité d'une
#: mesure — d'abord les réglages d'échantillonnage, puis le vocabulaire du
#: schéma. Les ajouter au coup par coup ne tient pas ; les prendre depuis le
#: protocole, si.
SECTIONS_OPERANTES = ("modele", "etiquetage")


def _ecrire(*morceaux: str) -> None:
    print(*morceaux, file=sys.stderr, flush=True)


def charger_protocole(chemin: Path) -> dict:
    if not chemin.is_file():
        raise SystemExit(
            f"Protocole de mesure introuvable : {chemin}. "
            "Aucune passe ne doit tourner sans protocole figé."
        )
    return yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}


def verifier_protocole(config: Config, protocole: dict) -> None:
    """Le protocole écrit et la configuration effective doivent coïncider.

    Sans cette vérification, `config/mesure.yaml` documenterait une passe et
    l'exécution en ferait une autre — on mesurerait une chose en en publiant
    une seconde, ce que tout le reste du projet cherche à empêcher.
    """
    modele = protocole.get("modele") or {}
    etiquetage = (protocole.get("etiquetage") or {}).get("pre_filtrage") or {}
    justification = (protocole.get("etiquetage") or {}).get("justification") or {}
    ecarts = []
    for cle, attendu, reel in (
        ("modele.id", modele.get("id"), config.modele),
        ("modele.reflexion", modele.get("reflexion"), config.reflexion),
        ("modele.effort", modele.get("effort"), config.effort),
        ("modele.max_tokens", modele.get("max_tokens"), config.max_tokens),
        ("pre_filtrage.sections_min", etiquetage.get("sections_min"), MIN_SECTIONS),
        ("pre_filtrage.sections_max", etiquetage.get("sections_max"), MAX_SECTIONS),
        ("justification.mots_minimum", justification.get("mots_minimum"),
         contrats.MIN_MOTS_JUSTIFICATION),
    ):
        if attendu is not None and attendu != reel:
            ecarts.append(f"{cle} : protocole {attendu!r}, exécution {reel!r}")
    if ecarts:
        raise SystemExit(
            "La configuration effective s'écarte du protocole figé :\n  "
            + "\n  ".join(ecarts)
            + "\nCorriger config/mesure.yaml ou l'environnement avant de mesurer."
        )


#: Un lot soumis mais non récupéré est de l'argent déjà engagé : son identifiant
#: est écrit sur disque AVANT l'attente, pour qu'une interruption se reprenne au
#: lieu de resoumettre.
FICHIER_LOTS = Path(".etage3/lots.json")
PAS_DE_SONDAGE = 30


#: Le mode strict compile une GRAMMAIRE par schéma d'outil distinct, et
#: l'organisation est plafonnée à 20 compilations par minute. Le pré-filtrage
#: partage un schéma unique et passe sans encombre ; l'étiquetage en présente un
#: par exercice — 260 d'un coup, dont 237 refusés. Le plafond ne se voit pas en
#: mode synchrone, où les appels s'espacent d'eux-mêmes : c'est le lot qui le
#: révèle. On soumet donc l'étiquetage par tranches sous le plafond.
TRANCHE_GRAMMAIRES = 15


def _lots_connus() -> dict[str, str]:
    if FICHIER_LOTS.is_file():
        return json.loads(FICHIER_LOTS.read_text(encoding="utf-8"))
    return {}


def _memoriser_lot(cle: str, identifiant: str | None) -> None:
    """`None` oublie l'entrée : un lot consommé ne doit pas être « repris ».

    Sans cet oubli, une relance après échecs partiels relisait le même lot
    terminé et retrouvait les mêmes erreurs au lieu d'en soumettre un neuf.
    """
    lots = _lots_connus()
    if identifiant is None:
        lots.pop(cle, None)
    else:
        lots[cle] = identifiant
    FICHIER_LOTS.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_LOTS.write_text(json.dumps(lots, ensure_ascii=False, indent=2), encoding="utf-8")


def _jouer_lot(
    fournisseur, journal, cle_lot: str, requetes: list[dict], outils: dict[str, str],
    etiquettes: dict[str, str], cumul: dict, attente_max: int,
) -> int:
    """Soumet (ou reprend) un lot, attend son terme, écrit tout au journal.

    Le `custom_id` est la CLÉ DE JOURNAL elle-même. Les résultats d'un lot
    reviennent dans un ordre quelconque ; faire porter la réassociation par la
    clé plutôt que par une correspondance annexe la rend juste par construction,
    et rend l'écriture au journal immédiate.
    """
    import time

    lots = _lots_connus()
    identifiant = lots.get(cle_lot)
    if identifiant:
        _ecrire(f"  lot {cle_lot} : reprise de {identifiant} déjà soumis")
    else:
        identifiant = fournisseur.soumettre_lot(requetes)
        _memoriser_lot(cle_lot, identifiant)
        _ecrire(f"  lot {cle_lot} : {len(requetes)} requête(s) soumises — {identifiant}")

    debut = time.time()
    while True:
        statut, compteurs = fournisseur.etat_lot(identifiant)
        if statut == "ended":
            break
        if time.time() - debut > attente_max:
            raise SystemExit(
                f"Lot {identifiant} toujours en cours après {attente_max} s. "
                f"Il est enregistré : relancer la même commande le reprendra."
            )
        _ecrire(
            f"    {statut} · {compteurs['aboutis']} abouti(s), "
            f"{compteurs['en_cours']} en cours, {compteurs['erreurs']} erreur(s)"
        )
        time.sleep(PAS_DE_SONDAGE)

    resultats = fournisseur.resultats_lot(identifiant, outils)
    echecs = 0
    motifs: dict[str, int] = {}
    for custom_id, resultat in resultats.items():
        if isinstance(resultat, str):
            motifs[resultat[:90]] = motifs.get(resultat[:90], 0) + 1
            echecs += 1
            continue
        cumul["entree"] += resultat.jetons_entree
        cumul["sortie"] += resultat.jetons_sortie
        cumul["cache"] += resultat.jetons_cache_lus
        cumul["cache_ecrits"] += resultat.jetons_cache_ecrits
        cumul["appels"] += 1
        journal.ecrire(custom_id, etiquettes[custom_id], resultat.charge, resultat.usage())
    # Le lot est consommé : l'oublier, sinon une relance le « reprend » et
    # retrouve les mêmes échecs au lieu d'en soumettre un neuf.
    _memoriser_lot(cle_lot, None)
    _ecrire(
        f"  lot {cle_lot} : {len(resultats) - echecs} réponse(s) écrites au journal, "
        f"{echecs} échec(s)"
    )
    # Les échecs sont AGRÉGÉS par motif : 237 lignes identiques noient le motif,
    # qui est la seule information utile.
    for motif, nombre in sorted(motifs.items(), key=lambda kv: -kv[1]):
        _ecrire(f"    ✗ {nombre:>4} × {motif}")
    return echecs


def _precharger_par_lot(
    documents, args, config, fournisseur, journal, signature, prefixe_sections,
    outil_sections, par_section, ids_sections, profil, exclusions, cumul,
) -> None:
    """Remplit le journal en DEUX lots, puis laisse la boucle normale relire.

    Les deux phases ne peuvent pas tenir dans un seul lot : le prompt
    d'étiquetage dépend des sections que le pré-filtrage vient de rendre. On
    soumet donc le pré-filtrage, on attend, on construit l'étiquetage, on
    soumet. La boucle principale n'est pas modifiée — elle retrouve tout au
    journal et ne part en appel direct pour rien.
    """
    attente = args.attente_lot

    # --- phase 1 : pré-filtrage ------------------------------------------- #
    requetes, outils, etiquettes = [], {}, {}
    for document, exercice in _exercices(documents, args.limite, args.exercice):
        if not exercice["questions"]:
            continue
        message = contrats.message_exercice(exercice, document["fichier"])
        cle = empreinte(signature, "sections", exercice["id"], message)
        if cle in journal:
            continue
        requetes.append({
            "custom_id": cle,
            "params": fournisseur.parametres_appel(
                prefixe_sections, message[:12000], outil_sections, 2000
            ),
        })
        outils[cle] = outil_sections["name"]
        etiquettes[cle] = f"etage3/{exercice['id']}"
    if requetes:
        _ecrire(f"\nlot 1/2 — pré-filtrage : {len(requetes)} exercice(s) à soumettre")
        _jouer_lot(fournisseur, journal, f"{signature}-sections", requetes,
                   outils, etiquettes, cumul, attente)
    else:
        _ecrire("\nlot 1/2 — pré-filtrage : rien à soumettre, tout est au journal")

    # --- phase 2 : étiquetage --------------------------------------------- #
    requetes, outils, etiquettes = [], {}, {}
    for document, exercice in _exercices(documents, args.limite, args.exercice):
        if not exercice["questions"]:
            continue
        message = contrats.message_exercice(exercice, document["fichier"])
        charge_sections = journal.lire(empreinte(signature, "sections", exercice["id"], message))
        if charge_sections is None:
            continue  # le pré-filtrage a échoué pour lui ; la boucle le dira
        retenues, _ = _retenir_sections(
            charge_sections, par_section, ids_sections, args.toutes_sections, exercice["id"]
        )
        candidates = [n for s in retenues for n in par_section.get(s, [])]
        if not candidates:
            continue
        cle = empreinte(signature, "etiquettes", exercice["id"], ",".join(retenues), message)
        if cle in journal:
            continue
        outil = contrats.schema_etiquettes(
            [n["id"] for n in candidates],
            [q["id"] for q in exercice["questions"]],
            profil.valeurs_langage,
        )
        requetes.append({
            "custom_id": cle,
            "params": fournisseur.parametres_appel(
                contrats.prefixe_etiquetage(candidates, profil.matiere, exclusions),
                message, outil, config.max_tokens,
            ),
        })
        outils[cle] = outil["name"]
        etiquettes[cle] = f"etage3/{exercice['id']}"
    if not requetes:
        _ecrire("\nlot 2/2 — étiquetage : rien à soumettre, tout est au journal")
        return

    # Une tranche = un paquet de schémas d'outil distincts sous le plafond de
    # compilation de grammaires. Les tranches sont séquentielles : chacune doit
    # être terminée avant la suivante, sinon leurs compilations se cumulent
    # dans la même minute et le plafond retombe.
    tranche = max(1, args.tranche_lot)
    tranches = [requetes[i : i + tranche] for i in range(0, len(requetes), tranche)]
    _ecrire(
        f"\nlot 2/2 — étiquetage : {len(requetes)} exercice(s) en {len(tranches)} tranche(s) "
        f"de {tranche} — un schéma d'outil par exercice, donc une compilation de "
        f"grammaire par requête (plafond : 20/minute)"
    )
    echecs = 0
    for rang, paquet in enumerate(tranches, start=1):
        _ecrire(f"  tranche {rang}/{len(tranches)}")
        echecs += _jouer_lot(
            fournisseur, journal, f"{signature}-etiquettes-{rang:03d}", paquet,
            outils, etiquettes, cumul, attente,
        )
    if echecs:
        _ecrire(
            f"\n{echecs} requête(s) d'étiquetage en échec sur {len(requetes)}. "
            "Elles ne sont pas au journal : relancer la même commande les resoumettra."
        )


def _retenir_sections(
    charge_sections: dict, par_section: dict, ids_sections: list[str],
    toutes: bool, exercice_id: str,
) -> tuple[list[str], bool]:
    """Sections retenues pour un exercice, et si la borne haute a été dépassée.

    Extrait de la boucle pour que le mode LOT et le mode direct appliquent la
    MÊME règle : deux copies de cette logique finiraient par diverger, et une
    campagne en lot mesurerait alors autre chose qu'une passe directe.

    Contrainte 2 <= n <= 4, validée ici : `minItems`/`maxItems` ne sont pas
    exprimables en mode strict — deuxième fois après l'enum nullable. On ne
    TRONQUE pas au-delà de 4 : l'ordre rendu n'a pas de sens sémantique, et
    couper dessus supprimerait de l'information au hasard.
    """
    retenues, vues = [], set()
    for entree in charge_sections.get("sections") or []:
        identifiant = entree.get("id")
        if identifiant in par_section and identifiant not in vues:
            vues.add(identifiant)
            retenues.append(identifiant)
    depasse = len(retenues) > MAX_SECTIONS
    if depasse:
        _ecrire(
            f"       · {exercice_id} : {len(retenues)} sections demandées "
            f"(> {MAX_SECTIONS}) — toutes conservées, borne haute à revoir"
        )
    if len(retenues) < MIN_SECTIONS:
        _ecrire(f"       · {exercice_id} : {len(retenues)} section(s) — repli élargi")
        retenues = (retenues + [s for s in ids_sections if s not in vues])[:MIN_SECTIONS]
    if toutes:
        # Diagnostic : soumettre les 182 notions départage le pré-filtrage du
        # prompt. Si le nombre d'étiquettes monte, c'est le filtre qui coupait ;
        # s'il ne bouge pas, la cause est ailleurs.
        retenues = list(ids_sections)
    return retenues, depasse


def _exercices(documents, limite=None, cible=None):
    for document in documents:
        for exercice in document["exercices"]:
            if cible and exercice["id"] != cible:
                continue
            yield document, exercice
            if limite:
                limite -= 1
                if limite <= 0:
                    return


def cmd_etiqueter(config: Config, args: argparse.Namespace) -> int:
    profil = config.profil
    notions, par_section = charger_referentiel(config.sortie / "sections")
    exclusions = charger_exclusions(config.sortie / "exclusions.json")
    documents = charger_corpus([Path(c) for c in args.corpus])
    sections = profil.sections_cibles
    ids_sections = [s["id"] for s in sections]

    outil_sections = contrats.schema_sections(ids_sections)
    prefixe_sections = contrats.prefixe_sections(sections, profil.matiere)

    total = sum(len(d["exercices"]) for d in documents)
    _ecrire(
        f"{len(notions)} notions · {len(exclusions)} mention(s) restrictive(s) · "
        f"{total} exercice(s) dans {len(documents)} document(s)"
    )

    if args.dry_run:
        return _dry_run(
            documents, prefixe_sections, outil_sections, par_section, profil,
            exclusions, args,
        )

    protocole = charger_protocole(Path(args.protocole))
    verifier_protocole(config, protocole)

    journal = Journal.ouvrir(config.journal)
    fournisseur = construire_fournisseur(config)
    # Réflexion et effort entrent dans la signature : sans eux, une passe
    # réflexion coupée rejouerait depuis le journal des réponses obtenues avec
    # réflexion, et mesurerait une chose en en publiant une autre. Ce sont les
    # deux SEULS leviers — les modèles courants rejettent `temperature`.
    signature = empreinte(
        "etage3", profil.version_prompt, config.modele, args.graine or "",
        json.dumps(outil_sections, sort_keys=True, ensure_ascii=False),
        # Tout ce que le protocole déclare comme opérant entre ici, par
        # construction — plutôt qu'ajouté au coup par coup après chaque
        # incident.
        json.dumps(
            {s: protocole.get(s) for s in SECTIONS_OPERANTES},
            sort_keys=True, ensure_ascii=False,
        ),
        contrats.CONSIGNES,
    )
    _ecrire(
        f"fournisseur {fournisseur.nom} · modèle {config.modele} · "
        f"réflexion {'oui' if config.reflexion else 'non'} · "
        f"effort {config.effort} · signature {signature}"
    )

    depassements: list[str] = []
    manquants: list[str] = []
    cumul = {"entree": 0, "sortie": 0, "cache": 0, "cache_ecrits": 0,
             "appels": 0, "reprises": 0}

    if args.batch:
        _precharger_par_lot(
            documents, args, config, fournisseur, journal, signature,
            prefixe_sections, outil_sections, par_section, ids_sections,
            profil, exclusions, cumul,
        )
        _ecrire("\nlots terminés — la suite se lit au journal, sans appel direct.")

    # ----------------------------------------------------------------------- #
    # DEUX PHASES. Le pré-filtrage passe d'abord sur tout le corpus, puis les
    # exercices sont TRIÉS PAR COMBINAISON DE SECTIONS avant l'étiquetage.
    #
    # Le préfixe d'étiquetage — le bloc référentiel — n'est constant que pour
    # une même combinaison. Traités dans l'ordre du corpus, les exercices font
    # alterner les combinaisons et chaque appel réécrit le cache au lieu de le
    # lire. Groupés, les appels consécutifs partagent le préfixe : la première
    # écriture est amortie sur tout le groupe. Cela ne change aucune clé de
    # journal, aucun prompt et aucun résultat — seulement l'ordre des appels.
    # ----------------------------------------------------------------------- #
    plan: list[tuple] = []
    for document, exercice in _exercices(documents, args.limite, args.exercice):
        if not exercice["questions"]:
            continue
        etiquette_journal = f"etage3/{exercice['id']}"

        # --- 1. pré-filtrage ------------------------------------------------ #
        message = contrats.message_exercice(exercice, document["fichier"])
        cle = empreinte(signature, "sections", exercice["id"], message)
        if cle in journal:
            charge_sections = journal.lire(cle)
            cumul["reprises"] += 1
        else:
            if args.batch:
                # En mode LOT, un manque au journal est un échec de lot — pas
                # une invitation à appeler en direct. Sans ce garde-fou, une
                # campagne dont le lot échoue se termine en appels synchrones
                # au PLEIN TARIF sans que rien ne le signale ; c'est arrivé.
                manquants.append(exercice["id"])
                continue
            try:
                reponse = fournisseur.appeler_outil(
                    prefixe_sections, message[:12000], outil_sections, 2000
                )
            except (ErreurFournisseur, RefusModele) as err:
                _ecrire(f"  ✗ {exercice['id']} : pré-filtrage — {err}")
                continue
            charge_sections = reponse.charge
            cumul["entree"] += reponse.jetons_entree
            cumul["sortie"] += reponse.jetons_sortie
            cumul["cache"] += reponse.jetons_cache_lus
            cumul["cache_ecrits"] += reponse.jetons_cache_ecrits
            cumul["appels"] += 1
            journal.ecrire(cle, etiquette_journal, charge_sections, reponse.usage())

        retenues, depasse = _retenir_sections(
            charge_sections, par_section, ids_sections, args.toutes_sections, exercice["id"]
        )
        if depasse:
            depassements.append(exercice["id"])
        candidates = [n for s in retenues for n in par_section.get(s, [])]
        if not candidates:
            _ecrire(f"  ✗ {exercice['id']} : aucune notion candidate")
            continue
        plan.append((tuple(sorted(retenues)), document, exercice, message,
                     retenues, candidates, etiquette_journal, len(plan)))

    # --- tri par combinaison de sections ------------------------------------ #
    plan.sort(key=lambda e: (e[0], e[2]["id"]))
    groupes = len({e[0] for e in plan})
    if plan:
        _ecrire(
            f"  {len(plan)} exercice(s) regroupés en {groupes} combinaison(s) de "
            f"sections — les appels d'étiquetage suivent ce regroupement pour "
            f"que le préfixe se répète"
        )

    resultats = []
    for _, document, exercice, message, retenues, candidates, etiquette_journal, rang in plan:
        # --- 2. étiquetage -------------------------------------------------- #
        ids_notions = [n["id"] for n in candidates]
        ids_questions = [q["id"] for q in exercice["questions"]]
        outil = contrats.schema_etiquettes(ids_notions, ids_questions, profil.valeurs_langage)
        prefixe = contrats.prefixe_etiquetage(candidates, profil.matiere, exclusions)
        cle = empreinte(signature, "etiquettes", exercice["id"], ",".join(retenues), message)
        if cle in journal:
            charge = journal.lire(cle)
            cumul["reprises"] += 1
        else:
            if args.batch:
                manquants.append(exercice["id"])
                continue
            try:
                reponse = fournisseur.appeler_outil(prefixe, message, outil, config.max_tokens)
            except (ErreurFournisseur, RefusModele) as err:
                _ecrire(f"  ✗ {exercice['id']} : étiquetage — {err}")
                continue
            charge = reponse.charge
            cumul["entree"] += reponse.jetons_entree
            cumul["sortie"] += reponse.jetons_sortie
            cumul["cache"] += reponse.jetons_cache_lus
            cumul["cache_ecrits"] += reponse.jetons_cache_ecrits
            cumul["appels"] += 1
            journal.ecrire(cle, etiquette_journal, charge, reponse.usage())

        resultat = valider_etiquettes(charge, exercice, set(ids_notions))
        resultat.fichier = document["fichier"]
        resultat.sections_retenues = retenues
        resultats.append((rang, resultat))

        posees = sum(len(q["etiquettes"]) for q in resultat.questions)
        _ecrire(
            f"  {exercice['id'][:52]:<52} {len(exercice['questions']):>3} q → "
            f"{posees:>3} étiq · {len(resultat.rejets):>2} rejet(s) · "
            f"sections {'+'.join(retenues)}"
        )
        for rejet in resultat.rejets:
            _ecrire(f"       ✗ {rejet.code} · {rejet.notion_id} · {rejet.detail[:70]}")

    # L'ordre des APPELS suit les combinaisons ; l'ordre de la SORTIE reste
    # celui du corpus, pour que deux passes restent comparables ligne à ligne.
    resultats = [r for _, r in sorted(resultats, key=lambda x: x[0])]

    if manquants:
        _ecrire("")
        _ecrire(
            f"⚠ {len(manquants)} appel(s) absent(s) du journal et NON rejoués en direct "
            "(mode lot). La mesure ci-dessous porte donc sur un corpus incomplet. "
            "Relancer la même commande resoumettra les manquants."
        )
        for identifiant in manquants[:10]:
            _ecrire(f"    {identifiant}")
        if len(manquants) > 10:
            _ecrire(f"    … et {len(manquants) - 10} autre(s)")
    if depassements:
        _ecrire("")
        _ecrire(
            f"pré-filtrage : {len(depassements)} exercice(s) sur "
            f"{len(resultats)} ont demandé plus de {MAX_SECTIONS} sections. "
            "Au-delà de la moitié, c'est la borne haute qui est mal choisie."
        )
    _rendre_mesures(resultats, cumul, notions)

    if args.sortie:
        racine = Path(args.sortie)
        racine.mkdir(parents=True, exist_ok=True)
        (racine / "etiquettes.json").write_text(
            json.dumps([dataclasses.asdict(r) for r in resultats], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _ecrire(f"\nécrit : {racine / 'etiquettes.json'}")
    return 0


def _rendre_mesures(resultats, cumul, notions) -> None:
    from collections import Counter

    questions = [q for r in resultats for q in r.questions]
    if not questions:
        _ecrire("\naucune question étiquetée")
        return
    etiquettes = [(q, e) for q in questions for e in q["etiquettes"]]
    par_notion_questions = Counter()
    for question in questions:
        for notion_id in {e["notion_id"] for e in question["etiquettes"]}:
            par_notion_questions[notion_id] += 1
    par_notion_occurrences = Counter(e["notion_id"] for _, e in etiquettes)

    n = len(questions)
    _ecrire("")
    _ecrire(f"questions étiquetées : {n} · étiquettes posées : {len(etiquettes)}")
    _ecrire(f"moyenne d'étiquettes par question : {len(etiquettes) / n:.2f}")
    statuts = Counter(q["statut"] for q in questions)
    for statut, compte in statuts.most_common():
        _ecrire(f"  {statut:<18} {compte:>4}  {100 * compte / n:>5.1f} %")
    hors = Counter(
        q["raison_hors_referentiel"] for q in questions if q["statut"] == "hors_referentiel"
    )
    for raison, compte in hors.most_common():
        _ecrire(f"    dont {str(raison):<14} {compte:>4}")

    # Remplace l'ancien statut `absent_du_programme`, que le modèle ne pouvait
    # pas produire faute de voir le programme. Ici c'est déterministe : la
    # question n'a reçu aucune notion, point.
    sans_notion = [q for q in questions if not q["etiquettes"]]
    if sans_notion:
        par_statut = Counter(q["statut"] for q in sans_notion)
        _ecrire(
            f"  {'aucune notion':<18} {len(sans_notion):>4}  "
            f"{100 * len(sans_notion) / n:>5.1f} %  "
            f"({', '.join(f'{k}={v}' for k, v in par_statut.most_common())})"
        )
    _ecrire("")
    _ecrire(f"notions distinctes utilisées : {len(par_notion_questions)} / {len(notions)}")
    _ecrire("top 10 (part des questions · part des occurrences) :")
    for notion_id, compte in par_notion_questions.most_common(10):
        _ecrire(
            f"  {notion_id[:56]:<56} {compte:>3}  {100 * compte / n:>5.1f} %  "
            f"{100 * par_notion_occurrences[notion_id] / max(1, len(etiquettes)):>5.1f} %"
        )
    cumul_top10 = sum(c for _, c in par_notion_questions.most_common(10))
    _ecrire(f"cumul top 10 : {100 * cumul_top10 / max(1, len(etiquettes)):.1f} % des occurrences")
    langues = Counter(q["langage"] for q in questions)
    _ecrire("langage (déduit de la consigne) : " + ", ".join(f"{k}={v}" for k, v in langues.most_common()))
    if cumul["appels"]:
        prompt = cumul["entree"] + cumul["cache"] + cumul["cache_ecrits"]
        _ecrire(
            f"jetons : prompt {prompt} ({cumul['entree']} neufs + {cumul['cache']} lus "
            f"+ {cumul['cache_ecrits']} écrits en cache) / {cumul['sortie']} sortie · "
            f"{cumul['appels']} appel(s), {cumul['reprises']} reprise(s)"
        )
        if prompt:
            _ecrire(
                f"         cache : {100 * cumul['cache'] / prompt:.0f} % du prompt lu "
                f"en cache, {100 * cumul['cache_ecrits'] / prompt:.0f} % écrit"
            )


def _dry_run(documents, prefixe_sections, outil_sections, par_section, profil,
             exclusions, args) -> int:
    couple = next(_exercices(documents, limite=1, cible=args.exercice), None)
    if couple is None:
        _ecrire("aucun exercice à montrer")
        return 2
    document, exercice = couple
    message = contrats.message_exercice(exercice, document["fichier"])

    print("=" * 78)
    print("APPEL 1 / 2 — PRÉ-FILTRAGE : quelles sections du référentiel ?")
    print("=" * 78)
    for bloc in prefixe_sections:
        print(bloc["text"])
        if "cache_control" in bloc:
            print(f"\n[cache_control: {bloc['cache_control']}]")
    print("\n" + "-" * 78 + f"\nOUTIL : {outil_sections['name']} (strict={outil_sections['strict']})\n" + "-" * 78)
    print(json.dumps(outil_sections["input_schema"], ensure_ascii=False, indent=2))
    print("\n" + "-" * 78 + "\nMESSAGE UTILISATEUR\n" + "-" * 78)
    print(message[:12000])

    sections_simulees = args.sections.split(",") if args.sections else list(par_section)[:3]
    candidates = [n for s in sections_simulees for n in par_section.get(s, [])]
    outil = contrats.schema_etiquettes(
        [n["id"] for n in candidates],
        [q["id"] for q in exercice["questions"]],
        profil.valeurs_langage,
    )
    prefixe = contrats.prefixe_etiquetage(candidates, profil.matiere, exclusions)

    print("\n\n" + "=" * 78)
    print(f"APPEL 2 / 2 — ÉTIQUETAGE · sections simulées : {'+'.join(sections_simulees)} "
          f"({len(candidates)} notions sur {sum(len(v) for v in par_section.values())})")
    print("=" * 78)
    for i, bloc in enumerate(prefixe, start=1):
        print(f"\n----- BLOC SYSTÈME {i} / {len(prefixe)} -----")
        print(bloc["text"])
        if "cache_control" in bloc:
            print(f"\n[cache_control: {bloc['cache_control']}  ← couvre TOUS les blocs précédents]")
    print("\n" + "-" * 78 + f"\nOUTIL : {outil['name']} (strict={outil['strict']})\n" + "-" * 78)
    print(json.dumps(outil["input_schema"], ensure_ascii=False, indent=2))
    print("\n" + "-" * 78 + "\nMESSAGE UTILISATEUR\n" + "-" * 78)
    print(message)
    return 0


def cmd_dispersion(config: "Config | None", args: argparse.Namespace) -> int:
    """Conservé comme alias : la mesure a déménagé à l'étage 4.

    `etage3 dispersion` est la forme documentée dans le carnet ; la casser
    silencieusement serait le même défaut que tout le reste du projet combat.
    L'implémentation, elle, n'a rien à faire dans le code d'étiquetage.
    """
    from etage4.cli import main as etage4_main

    _ecrire("note : la dispersion est passée à l'étage 4 — `etage4 dispersion A B`.")
    return etage4_main(["dispersion", args.passes[0], args.passes[1]])


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="etage3", description="Étiquette le corpus extrait.")
    analyseur.add_argument("--modele", help="surcharge ETAGE0_MODELE")
    analyseur.add_argument(
        "--fournisseur", choices=["anthropic"],
        help="point d'architecture : un seul fournisseur est branché",
    )
    sous = analyseur.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("etiqueter")
    p.add_argument("corpus", nargs="+", help="fichiers JSON produits par l'étage 1")
    p.add_argument("--dry-run", action="store_true", help="affiche les prompts, n'appelle rien")
    p.add_argument("--exercice", help="limite à un exercice (son id)")
    p.add_argument("--limite", type=int, help="nombre maximum d'exercices")
    p.add_argument("--sections", help="en dry-run, sections à simuler (séparées par des virgules)")
    p.add_argument("--graine", help="DIAGNOSTIC : sale la clé de journal pour forcer un nouvel appel "
                                    "et mesurer la variance d'une passe à l'autre")
    p.add_argument("--toutes-sections", action="store_true",
                   help="DIAGNOSTIC : ignore le pré-filtrage et soumet les 182 notions")
    p.add_argument("--batch", action="store_true",
                   help="passe par la Batch API : moitié prix, retour asynchrone, "
                        "réassociation par custom_id")
    p.add_argument("--attente-lot", type=int, default=24 * 3600, dest="attente_lot",
                   help="secondes d'attente maximale par lot (défaut : 24 h)")
    p.add_argument("--tranche-lot", type=int, default=TRANCHE_GRAMMAIRES, dest="tranche_lot",
                   help=f"requêtes d'étiquetage par tranche (défaut : {TRANCHE_GRAMMAIRES}, "
                        "sous le plafond de 20 compilations de grammaire par minute)")
    p.add_argument("--sortie", help="dossier où écrire etiquettes.json")
    p.add_argument("--protocole", default="config/mesure.yaml",
                   help="protocole de mesure figé (défaut : config/mesure.yaml)")
    p.set_defaults(fonction=cmd_etiqueter)

    d = sous.add_parser(
        "dispersion",
        help="compare deux passes et classe les exercices par instabilité",
    )
    d.add_argument("passes", nargs=2, help="deux dossiers de sortie d'étiquetage")
    d.set_defaults(fonction=cmd_dispersion)

    args = analyseur.parse_args(argv)
    from dataclasses import replace

    # `dispersion` ne joint rien : lui imposer une configuration de fournisseur
    # complète le rendait indisponible sur une machine qui ne fait que lire les
    # mesures — exactement le public de cette commande.
    if args.fonction is cmd_dispersion:
        return cmd_dispersion(None, args)

    config = Config.depuis_env()
    if args.modele:
        config = replace(config, modele=args.modele)
    if args.fournisseur:
        config = replace(config, fournisseur=args.fournisseur)
    return args.fonction(config, args)


if __name__ == "__main__":
    raise SystemExit(main())
