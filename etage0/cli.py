"""Étage 0 — programme officiel → référentiel de notions attribuables.

    etage0 segmenter          # déterministe, aucun appel : à valider À LA MAIN d'abord
    etage0 construire --dry-run
    etage0 construire --fournisseur anthropic --etalon referentiel/v1/sections

Le sous-commande `segmenter` existe parce que l'échec précédent du projet était
un bug d'étage déterministe qui a contaminé 2 011 étiquettes en aval. On valide
la segmentation avant de dépenser le premier euro.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import confrontation, contrats, exclusions, referentiel as ref
from .config import Config
from .fournisseurs import ErreurFournisseur, RefusModele, construire as construire_fournisseur
from .journal import Journal, empreinte
from .segmentation import Unite, filtrer, grouper_par_section, segmenter


def _ecrire(*morceaux: str) -> None:
    print(*morceaux, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #


def cmd_segmenter(config: Config, args: argparse.Namespace) -> int:
    rapport = segmenter(config.programme, config.profil.genres_ecartes)
    rapport = filtrer(rapport, config.profil.titres_exclus, config.profil.prefixes_exclus)
    groupes = grouper_par_section(rapport.unites)

    par_genre: dict[str, int] = {}
    for unite in rapport.unites:
        par_genre[unite.genre] = par_genre.get(unite.genre, 0) + 1

    _ecrire(f"sections retenues     : {len(groupes)}")
    _ecrire(f"unités candidates     : {len(rapport.unites)}")
    for genre, compte in sorted(par_genre.items()):
        _ecrire(f"  {genre:<16} {compte}")
    _ecrire(f"unités écartées       : {len(rapport.ecartees)}")
    for identifiant, motif, ligne in rapport.ecartees[:20]:
        _ecrire(f"  {identifiant:<28} ligne {ligne:<5} {motif}")
    if len(rapport.ecartees) > 20:
        _ecrire(f"  … {len(rapport.ecartees) - 20} de plus")

    if args.detail:
        for section_id, unites in groupes.items():
            print(f"\n{'=' * 70}\nSECTION {section_id} — {unites[0].section.titre}")
            for unite in unites:
                print(unite.rendu())

    if args.sortie:
        chemin = Path(args.sortie)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(
            json.dumps(
                [
                    {
                        "id": u.id,
                        "section": u.section.id,
                        "titre": u.section.titre,
                        "genre": u.genre,
                        "semestre": u.semestre,
                        "notions": u.notions,
                        "commentaires": u.commentaires,
                        "texte": u.texte,
                        "lignes": [u.ligne_debut, u.ligne_fin],
                    }
                    for u in rapport.unites
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _ecrire(f"\nécrit : {chemin}")
    return 0


# --------------------------------------------------------------------------- #


def cmd_construire(config: Config, args: argparse.Namespace) -> int:
    profil = config.profil
    rapport = segmenter(config.programme, profil.genres_ecartes)
    rapport = filtrer(rapport, profil.titres_exclus, profil.prefixes_exclus)
    groupes = grouper_par_section(rapport.unites)
    index_unites = {u.id: u for u in rapport.unites}

    outil_notions = contrats.schema_notions(profil)
    prefixe = contrats.prefixe_constant(profil)
    signature_prompt = empreinte(
        profil.version_prompt,
        profil.critere_admission,
        json.dumps(outil_notions, sort_keys=True, ensure_ascii=False),
        config.modele,
        config.fournisseur,
    )

    if args.dry_run:
        return _dry_run(groupes, prefixe, outil_notions, signature_prompt, args)

    journal = Journal.ouvrir(config.journal)
    if args.rejouer:
        purges = journal.oublier()
        _ecrire(f"journal purgé : {purges} entrée(s)")

    fournisseur = construire_fournisseur(config)
    _ecrire(
        f"fournisseur {fournisseur.nom} · modèle {config.modele} · "
        f"{len(groupes)} section(s) · signature {signature_prompt}"
    )

    decisions_par_section: dict[str, list[dict[str, Any]]] = {}
    # Une section perdue ne doit JAMAIS passer inaperçue : sans ce registre,
    # §3.4 et §4.3 ont disparu du référentiel v1 (glouton, diviser pour régner,
    # dichotomie, programmation dynamique, représentation des graphes) sans
    # laisser d'autre trace qu'une ligne sur stderr.
    sections_perdues: list[dict[str, str]] = []
    # Le grain du rejet est l'unité, pas la section : ces deux registres portent
    # ce qui a été écarté et ce qui a été normalisé, unité par unité, et les
    # deux finissent dans manifest.yaml.
    unites_rejetees: list[dict[str, str]] = []
    reparations: list[dict[str, str]] = []
    cumul = {"entree": 0, "sortie": 0, "cache_lus": 0, "cache_ecrits": 0,
             "appels": 0, "reprises": 0}

    for numero, (section_id, unites) in enumerate(sorted(groupes.items()), start=1):
        message = contrats.message_section(unites)
        cle = empreinte(signature_prompt, "notions", section_id, message)
        etiquette = f"notions/{section_id}"

        if cle in journal:
            charge = journal.lire(cle)
            cumul["reprises"] += 1
        else:
            try:
                reponse = fournisseur.appeler_outil(
                    prefixe, message, outil_notions, config.max_tokens
                )
            except RefusModele as err:
                _ecrire(f"  ✗ {section_id} : {err}")
                sections_perdues.append({"section": section_id, "cause": f"refus : {err}"})
                if args.strict:
                    return 2
                continue
            except ErreurFournisseur as err:
                _ecrire(f"  ✗ {section_id} : {err}")
                sections_perdues.append({"section": section_id, "cause": f"erreur fournisseur : {err}"})
                if args.strict:
                    return 2
                continue
            charge = reponse.charge
            cumul["entree"] += reponse.jetons_entree
            cumul["sortie"] += reponse.jetons_sortie
            cumul["cache_lus"] += reponse.jetons_cache_lus
            cumul["cache_ecrits"] += reponse.jetons_cache_ecrits
            cumul["appels"] += 1
            journal.ecrire(
                cle,
                etiquette,
                charge,
                {
                    **reponse.usage(),
                    "unites": [u.id for u in unites],
                    "notes": reponse.notes,
                },
            )

        try:
            rapport_contrat = contrats.valider_decisions(charge, unites, profil)
        except contrats.ErreurContrat as err:
            _ecrire(f"  ✗ {section_id} : contrat violé — {err}")
            journal.oublier(etiquette)
            sections_perdues.append({"section": section_id, "cause": f"contrat violé : {err}"})
            if args.strict:
                return 2
            continue

        for constat in rapport_contrat.rejets:
            unites_rejetees.append(
                {"section": section_id, "cible": constat.cible,
                 "regle": constat.code, "cause": constat.message}
            )
        for constat in rapport_contrat.reparations:
            reparations.append(
                {"section": section_id, "cible": constat.cible, "regle": constat.code,
                 "constat": constat.message, "reparation": constat.reparation or ""}
            )

        decisions = rapport_contrat.decisions
        decisions_par_section[section_id] = decisions
        produites = sum(len(d["notions"]) for d in decisions)
        refusees = sum(1 for d in decisions if d["verdict"] == "refuse")
        suffixe = ""
        if rapport_contrat.rejets:
            suffixe += f", {len(rapport_contrat.rejets)} rejet(s)"
        if rapport_contrat.reparations:
            suffixe += f", {len(rapport_contrat.reparations)} réparation(s)"
        _ecrire(
            f"  [{numero:>2}/{len(groupes)}] {section_id:<8} "
            f"{len(unites):>3} unités → {produites:>3} notions, {refusees:>2} refus{suffixe}"
        )
        for constat in rapport_contrat.rejets:
            _ecrire(f"       ✗ rejet {constat.code} — {constat.rendu()}")
        for constat in rapport_contrat.reparations:
            _ecrire(f"       ~ réparé {constat.code} — {constat.rendu()}")
        if args.strict and rapport_contrat.rejets:
            return 2

    referentiel = ref.assembler(decisions_par_section, index_unites, profil)

    # NORMALISATION AVANT LE CONTRÔLE. Le modèle invente des identifiants de
    # cible — `prouver_terminaison_variant` là où la notion s'appelle
    # `prouver_terminaison_par_variant`. Ce n'est pas une notion manquante,
    # c'est un mot différent pour la même chose, et laisser quatre renvois de
    # vocabulaire bloquer la publication d'un référentiel complet payé 3 $ est
    # disproportionné. Au-dessous du seuil, on ne repointe pas : un repointage
    # douteux ferait dire à une notion qu'elle en exclut une autre, à tort.
    examens = ref.normaliser_renvois(referentiel)
    reparations.extend(examens)
    repointes = [e for e in examens if e["repointe"]]
    sans_candidat = [e for e in examens if not e["repointe"]]
    if examens:
        _ecrire("")
        _ecrire(
            f"renvois inventés  : {len(examens)} — {len(repointes)} repointé(s), "
            f"{len(sans_candidat)} sans candidat au-dessus de {ref.SEUIL_SIMILARITE}"
        )
        for e in repointes:
            _ecrire(f"  ~ {e['renvoi_origine']!r} → {e['cible_retenue']} "
                    f"(score {e['score']:.2f})  depuis {e['cible']}")
        for e in sans_candidat:
            _ecrire(f"  ✗ {e['renvoi_origine']!r} : meilleur candidat "
                    f"{e['meilleur_candidat']} à {e['score']:.2f} — reste bloquant")

    anomalies = ref.valider(referentiel, profil)

    meta = {
        "fournisseur": fournisseur.nom,
        "modele": config.modele,
        "effort": config.effort,
        "signature_prompt": signature_prompt,
        "appels": cumul["appels"],
        "reprises": cumul["reprises"],
        "jetons_entree": cumul["entree"],
        "jetons_sortie": cumul["sortie"],
        "jetons_cache_lus": cumul["cache_lus"],
        "sections_perdues": sections_perdues,
    }
    ref.ecrire(referentiel, config, meta, unites_rejetees, reparations, anomalies)

    _ecrire("")
    _ecrire(f"notions produites : {len(referentiel.notions)}")
    _ecrire(f"unités refusées   : {len(referentiel.refus)}")
    if cumul["appels"]:
        prompt = cumul["entree"] + cumul["cache_lus"] + cumul["cache_ecrits"]
        _ecrire(
            f"jetons            : prompt {prompt} "
            f"({cumul['entree']} neufs + {cumul['cache_lus']} lus en cache + "
            f"{cumul['cache_ecrits']} écrits en cache) / {cumul['sortie']} sortie"
        )
        if cumul["cache_lus"] == 0 and cumul["appels"] > 1:
            _ecrire(
                "  ⚠ aucun jeton lu en cache sur plusieurs appels : le préfixe "
                "constant est invalidé quelque part."
            )
    _ecrire(f"écrit dans        : {config.sortie}")

    for perdue in sections_perdues:
        anomalies.append(
            ref.anomalie("section_perdue",
                         f"SECTION PERDUE {perdue['section']} — {perdue['cause']}")
        )
    for rejet in unites_rejetees:
        anomalies.append(
            ref.anomalie(
                "unite_rejetee",
                f"UNITÉ REJETÉE {rejet['cible']} ({rejet['regle']}) — {rejet['cause']}",
            )
        )
    if reparations:
        _ecrire(f"réparations       : {len(reparations)} (détail dans manifest.yaml)")
    if unites_rejetees:
        _ecrire(f"unités rejetées   : {len(unites_rejetees)} (détail dans manifest.yaml)")
    if sections_perdues:
        _ecrire("")
        _ecrire(
            f"⛔ {len(sections_perdues)} SECTION(S) ABSENTE(S) DU RÉFÉRENTIEL — "
            "il est incomplet, relancer avant toute exploitation."
        )
    # Deux catégories, jamais mélangées. Un défaut d'INTÉGRITÉ empêche de
    # livrer ; un défaut de GRANULARITÉ est l'état attendu d'une construction
    # brute, et le confondre avec le premier revient à jeter un artefact valide
    # payé 3 $ pour un motif qui se résorbe à l'étape suivante.
    bloquants = [a for a in anomalies if a.gravite == ref.FATAL]
    attendus = [a for a in anomalies if a.gravite != ref.FATAL]

    if bloquants:
        _ecrire("")
        _ecrire(f"⛔ INTÉGRITÉ — {len(bloquants)} défaut(s) :")
        for a in bloquants:
            _ecrire(f"  ✗ [{a.code or 'sans code'}] {a.message}")
    if attendus:
        _ecrire("")
        _ecrire(f"GRANULARITÉ — {len(attendus)} avertissement(s), "
                "le référentiel est livré :")
        for a in attendus:
            resorbe = ref.RESORBE_PAR.get(a.code)
            suffixe = f"  → normal à ce stade, se résorbe par {resorbe}" if resorbe else ""
            _ecrire(f"  · [{a.code or 'sans code'}] {a.message}{suffixe}")
        codes = {a.code for a in attendus} & set(ref.RESORBE_PAR)
        if codes:
            _ecrire("")
            _ecrire(
                "  Ces avertissements sont ATTENDUS sur une construction brute : "
                "mesurer la granularité avant la purge des annexes et la "
                "confrontation au corpus, c'est juger une chaîne incomplète "
                "selon les critères de la chaîne complète."
            )

    if config.etalon and config.etalon.is_dir():
        mesure = ref.comparer_etalon(referentiel, config.etalon)
        (config.sortie / "comparaison_etalon.json").write_text(
            json.dumps(mesure, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _rendre_etalon(mesure)

    if bloquants:
        _ecrire("")
        if args.strict:
            _ecrire(
                f"⛔ --strict : {len(bloquants)} défaut(s) d'intégrité, "
                "code retour 2, le référentiel n'est pas publié."
            )
        else:
            # Un référentiel construit intégralement — 44 sections sur 44 — ne
            # doit pas rester non publié pour deux renvois d'une section
            # d'annexes que la purge retirera. Bloquer là arrête toute la chaîne
            # aval : l'étiquetage sort aussitôt par « absence de référentiel ».
            # Le rapport dit exactement la même chose ; seule la conséquence
            # change.
            _ecrire(
                f"{len(bloquants)} défaut(s) d'intégrité — le référentiel est "
                "PUBLIÉ quand même, et ils sont recensés dans `manifest.yaml` "
                "sous `anomalies`. Relancer avec --strict pour que ces défauts "
                "fassent échouer la commande."
            )
    return 2 if (bloquants and args.strict) else 0


def _rendre_etalon(mesure: dict[str, Any]) -> None:
    _ecrire("")
    _ecrire(
        f"rappel sur l'étalon : {mesure['rappel_exact']} exact · "
        f"{mesure['rappel_avec_similarite']} avec appariement "
        f"(seuil {mesure['seuil_similarite']})"
    )
    for section, detail in mesure["detail"].items():
        _ecrire(
            f"  {section:<18} {detail['exacts']} exact + {detail['par_similarite']} apparié"
            f" / {detail['attendus']}"
            + (
                f"  manquants : {', '.join(detail['manquants'][:3])}"
                if detail["manquants"]
                else ""
            )
        )
    if mesure["appariements_par_similarite"]:
        _ecrire("")
        _ecrire("paires appariées par similarité — À CONTRÔLER :")
        for paire in mesure["appariements_par_similarite"]:
            marque = " " if paire["meme_section"] else "!"
            _ecrire(f"  {marque} {paire['score']:.2f}  {paire['etalon']}")
            _ecrire(f"           → {paire['obtenu']}")
            _ecrire(f"           étalon : {paire['libelle_etalon']}")
            _ecrire(f"           obtenu : {paire['libelle_obtenu']}")
        if mesure["apparies_hors_section"]:
            _ecrire(
                f"  ! = retrouvée mais rangée dans une autre section "
                f"({len(mesure['apparies_hors_section'])})"
            )


def cmd_injecter(config: Config, args: argparse.Namespace) -> int:
    """Régénère UNE section du programme et l'injecte dans un référentiel écrit.

    `construire` réécrit tout ETAGE0_SORTIE : l'employer pour rattraper une
    seule section écraserait le travail fait sur les autres — purge des
    annexes, exemples de confrontation. Ici, rien n'est touché en dehors des
    notions de la section demandée.
    """
    profil = config.profil
    rapport = segmenter(config.programme, profil.genres_ecartes)
    rapport = filtrer(rapport, profil.titres_exclus, profil.prefixes_exclus)
    groupes = grouper_par_section(rapport.unites)
    index_unites = {u.id: u for u in rapport.unites}

    unites = groupes.get(args.section)
    if not unites:
        _ecrire(f"Section {args.section!r} absente de la segmentation.")
        _ecrire(f"Sections connues : {', '.join(sorted(groupes))}")
        return 2

    dossier = config.sortie / "sections"
    if not dossier.is_dir():
        _ecrire(f"Référentiel introuvable : {dossier}")
        return 2
    existantes = ref.charger_notions(dossier)
    _ecrire(f"référentiel existant : {len(existantes)} notions · section {args.section} : {len(unites)} unités")

    outil = contrats.schema_notions(profil)
    prefixe = contrats.prefixe_constant(profil)
    message = contrats.message_section(unites)
    signature = empreinte(
        profil.version_prompt,
        profil.critere_admission,
        json.dumps(outil, sort_keys=True, ensure_ascii=False),
        config.modele,
        config.fournisseur,
    )

    if args.dry_run:
        print(message)
        _ecrire(f"\nDRY-RUN · signature {signature} · 1 appel")
        return 0

    journal = Journal.ouvrir(config.journal)
    cle = empreinte(signature, "notions", args.section, message)
    etiquette = f"notions/{args.section}"

    if cle in journal and not args.rejouer:
        charge = journal.lire(cle)
        _ecrire("repris depuis le journal (--rejouer pour forcer un appel)")
    else:
        fournisseur = construire_fournisseur(config)
        _ecrire(f"appel {fournisseur.nom} · modèle {config.modele}")
        try:
            reponse = fournisseur.appeler_outil(prefixe, message, outil, config.max_tokens)
        except (ErreurFournisseur, RefusModele) as err:
            _ecrire(f"✗ {err}")
            return 2
        charge = reponse.charge
        journal.ecrire(
            cle, etiquette, charge,
            {**reponse.usage(), "unites": [u.id for u in unites], "notes": reponse.notes},
        )
        u = reponse.usage()
        _ecrire(
            f"jetons : prompt {u['prompt_total']} ({u['entree']} neufs + "
            f"{u['cache_lus']} lus + {u['cache_ecrits']} écrits en cache) / "
            f"{u['sortie']} sortie"
        )

    try:
        rapport_contrat = contrats.valider_decisions(charge, unites, profil)
    except contrats.ErreurContrat as err:
        _ecrire(f"✗ contrat violé — {err}")
        journal.oublier(etiquette)
        return 2

    for constat in rapport_contrat.rejets:
        _ecrire(f"  ✗ rejet {constat.code} — {constat.rendu()}")
    for constat in rapport_contrat.reparations:
        _ecrire(f"  ~ réparé {constat.code} — {constat.rendu()}")

    # Une notion dont le slug existe déjà ne s'injecte pas. La renommer en
    # `…_2`, ce que fait l'assemblage pour les collisions internes à un appel,
    # fabriquerait ici un doublon dans un référentiel qui demande justement
    # qu'aucune définition opératoire n'en recouvre une autre.
    slugs_existants = {n["slug"]: n["id"] for n in existantes}
    collisions: list[tuple[str, dict[str, Any]]] = []
    for decision in rapport_contrat.decisions:
        gardees = []
        for notion in decision["notions"]:
            if notion["slug"] in slugs_existants:
                collisions.append((decision["unite_id"], notion))
            else:
                gardees.append(notion)
        decision["notions"] = gardees

    produit = ref.assembler(
        {args.section: rapport_contrat.decisions}, index_unites, profil, existantes
    )
    _ecrire(f"\n{len(produit.notions)} notion(s) produite(s), {len(produit.refus)} refus")
    for notion in produit.notions:
        _ecrire(f"  + {notion['id']:<60} {notion['libelle']}")

    for unite_id, notion in collisions:
        _ecrire(
            f"  ≡ {unite_id} : {notion['slug']!r} existe déjà "
            f"({slugs_existants[notion['slug']]}) — NON injectée, à arbitrer"
        )
        _ecrire(f"      proposé : {notion['libelle']}")
    for anomalie in produit.anomalies:
        _ecrire(f"  {'✗' if anomalie.gravite == 'bloquant' else '·'} {anomalie.message}")

    if args.simuler:
        _ecrire("\n(simulation — rien n'a été écrit ; retirer --simuler pour injecter)")
        return 0

    reparations = [
        {"section": args.section, "cible": c.cible, "regle": c.code,
         "constat": c.message, "reparation": c.reparation or ""}
        for c in rapport_contrat.reparations
    ]
    rejets = [
        {"section": args.section, "cible": c.cible, "regle": c.code, "cause": c.message}
        for c in rapport_contrat.rejets
    ] + [
        {
            "section": args.section,
            "cible": f"{unite_id}/{notion['slug']}",
            "regle": "collision_slug_existant",
            "cause": f"slug déjà porté par {slugs_existants[notion['slug']]} — non injectée",
        }
        for unite_id, notion in collisions
    ]
    ajoutees = ref.injecter(produit, config, args.section, reparations, rejets)
    for fichier, compte in sorted(ajoutees.items()):
        _ecrire(f"  → {compte} notion(s) dans {fichier}")

    anomalies = ref.verifier_renvois(
        ref.charger_notions(dossier), set(profil.ids_sections_cibles)
    )
    bloquants = [a for a in anomalies if a.gravite == "bloquant"]
    _ecrire("")
    _ecrire(f"passe renvois : {len(bloquants)} irrésolu(s) sur l'ensemble du référentiel")
    for anomalie in bloquants:
        _ecrire(f"  ✗ {anomalie.message}")
    return 0


# --------------------------------------------------------------------------- #


def cmd_etalon(config: Config, args: argparse.Namespace) -> int:
    """Rejoue la comparaison à l'étalon sur un référentiel déjà écrit.

    Sans régénérer : la mesure est un test du générateur, et un test doit
    pouvoir être relancé après correction de l'étalon sans repayer un appel.
    """
    if not config.etalon or not config.etalon.is_dir():
        _ecrire("Aucun étalon : renseigner ETAGE0_ETALON ou --etalon.")
        return 2
    dossier = Path(args.dossier) if args.dossier else config.sortie / "sections"
    if not dossier.is_dir():
        _ecrire(f"Dossier introuvable : {dossier}")
        return 2

    referentiel = ref.Referentiel(notions=ref.charger_notions(dossier))
    mesure = ref.comparer_etalon(referentiel, config.etalon, seuil=args.seuil)
    destination = config.sortie / "comparaison_etalon.json"
    destination.write_text(
        json.dumps(mesure, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _rendre_etalon(mesure)
    _ecrire("")
    _ecrire(f"écrit : {destination}")
    return 0


def _dry_run(
    groupes: dict[str, list[Unite]],
    prefixe: list[dict[str, Any]],
    outil: dict[str, Any],
    signature: str,
    args: argparse.Namespace,
) -> int:
    """Affiche les prompts exacts sans joindre le moindre service."""
    _ecrire(f"DRY-RUN · signature de prompt {signature} · {len(groupes)} appel(s)")
    print("=" * 78)
    print("PRÉFIXE SYSTÈME CONSTANT (point de cache sur le dernier bloc)")
    print("=" * 78)
    for bloc in prefixe:
        print(bloc["text"])
        if "cache_control" in bloc:
            print(f"\n[cache_control: {bloc['cache_control']}]")
    print()
    print("=" * 78)
    print(f"OUTIL DÉCLARÉ : {outil['name']} (strict={outil.get('strict')})")
    print("=" * 78)
    print(json.dumps(outil["input_schema"], ensure_ascii=False, indent=2))

    for section_id, unites in sorted(groupes.items()):
        if args.section and section_id != args.section:
            continue
        print()
        print("=" * 78)
        print(f"MESSAGE UTILISATEUR — section {section_id}")
        print("=" * 78)
        print(contrats.message_section(unites))
    return 0


# --------------------------------------------------------------------------- #


def cmd_renvois(config: Config, args: argparse.Namespace) -> int:
    """Passe finale de résolution des renvois, sur un référentiel déjà écrit.

    Séparée de `construire` parce qu'un renvoi peut viser une notion d'une
    section produite plus tard, ou injectée à la main : la seule vérification
    qui vaille se fait sur le dossier complet, après coup.
    """
    dossier = Path(args.dossier) if args.dossier else config.sortie / "sections"
    if not dossier.is_dir():
        _ecrire(f"Dossier introuvable : {dossier}")
        return 2

    notions = ref.charger_notions(dossier)
    ids_sections = set(config.profil.ids_sections_cibles)
    anomalies = ref.verifier_renvois(notions, ids_sections)

    renvois = [
        e
        for n in notions
        for e in (n.get("exclusions") or [])
        if e.get("voir") or e.get("voir_brut")
    ]
    par_type: dict[str, int] = {}
    for exclusion in renvois:
        cle = exclusion.get("voir_type") or "non résolu"
        par_type[cle] = par_type.get(cle, 0) + 1

    _ecrire(f"{len(notions)} notions · {len(renvois)} renvoi(s) `voir`")
    for type_cible, compte in sorted(par_type.items()):
        _ecrire(f"  {type_cible:<12} {compte:>4}")

    bloquants = [a for a in anomalies if a.gravite == "bloquant"]
    for anomalie in anomalies:
        _ecrire(f"  {'✗' if anomalie.gravite == 'bloquant' else '·'} {anomalie.message}")
    _ecrire("")
    _ecrire(f"{len(bloquants)} renvoi(s) irrésolu(s) sur {len(renvois)}")
    return 2 if bloquants else 0


# --------------------------------------------------------------------------- #


def cmd_exclusions(config: Config, args: argparse.Namespace) -> int:
    profil = config.profil
    rapport = segmenter(config.programme, profil.genres_ecartes)
    sections_par_ligne = {s.ligne: s.id for s in rapport.sections}
    mentions = exclusions.detecter(config.programme, profil.motifs_restrictifs, sections_par_ligne)
    _ecrire(f"{len(mentions)} mention(s) restrictive(s) détectée(s)")

    outil = contrats.schema_mentions(profil)
    prefixe = contrats.prefixe_mentions(profil)
    message = exclusions.message_mentions(mentions)

    if args.dry_run:
        for bloc in prefixe:
            print(bloc["text"])
        print("\n" + "=" * 78 + f"\nOUTIL : {outil['name']}\n" + "=" * 78)
        print(json.dumps(outil["input_schema"], ensure_ascii=False, indent=2))
        print("\n" + "=" * 78 + "\nMESSAGE\n" + "=" * 78)
        print(message)
        return 0

    journal = Journal.ouvrir(config.journal)
    signature = empreinte(profil.version_prompt, config.modele, config.fournisseur, "mentions")
    cle = empreinte(signature, message)

    if cle in journal:
        charge = journal.lire(cle)
        _ecrire("repris depuis le journal")
    else:
        fournisseur = construire_fournisseur(config)
        try:
            reponse = fournisseur.appeler_outil(prefixe, message, outil, config.max_tokens)
        except (ErreurFournisseur, RefusModele) as err:
            _ecrire(f"✗ {err}")
            return 2
        charge = reponse.charge
        journal.ecrire(cle, "mentions", charge, reponse.usage())
        u = reponse.usage()
        _ecrire(
            f"jetons : prompt {u['prompt_total']} ({u['entree']} neufs + "
            f"{u['cache_lus']} lus + {u['cache_ecrits']} écrits en cache) / "
            f"{u['sortie']} sortie"
        )

    fusionnees = exclusions.fusionner(mentions, charge.get("mentions", []))
    config.sortie.mkdir(parents=True, exist_ok=True)
    destination = config.sortie / "exclusions.json"
    destination.write_text(
        json.dumps(fusionnees, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    par_portee: dict[str, int] = {}
    for entree in fusionnees:
        par_portee[entree["portee"]] = par_portee.get(entree["portee"], 0) + 1
    for portee, compte in sorted(par_portee.items()):
        marque = "→ autorise hors_referentiel" if portee == "objet_exclu" else ""
        _ecrire(f"  {portee:<22} {compte:>3}  {marque}")
    _ecrire(f"écrit : {destination}")
    return 0


# --------------------------------------------------------------------------- #


def cmd_confronter(config: Config, args: argparse.Namespace) -> int:
    """Le corpus contre le référentiel. Aucun appel, aucune écriture de notion.

    Cette commande ne crée rien : elle ramène des passages avec leur
    provenance et applique la règle des deux fichiers distincts. La rédaction
    de la notion reste humaine — c'est ce qui empêche le référentiel de se
    remplir des tics de rédaction d'un seul concepteur de sujet.
    """
    sondes, entete = confrontation.charger_sondes(Path(args.sondes))
    if args.sonde:
        sondes = [s for s in sondes if args.sonde in s.nom]
        if not sondes:
            raise SystemExit(f"Aucune sonde ne correspond à « {args.sonde} ».")
    minimum = args.minimum or (entete.get("regle") or {}).get(
        "fichiers_distincts_minimum", confrontation.MINIMUM_PAR_DEFAUT
    )
    contexte = (entete.get("regle") or {}).get(
        "contexte_caracteres", confrontation.CONTEXTE_PAR_DEFAUT
    )

    chemins = [Path(c) for c in args.corpus]
    manquants = [c for c in chemins if not c.is_file()]
    if manquants:
        raise SystemExit(f"Corpus introuvable : {', '.join(str(m) for m in manquants)}")
    liste_zones = list(confrontation.zones(chemins))
    fichiers = sorted({z[0] for z in liste_zones})
    _ecrire(
        f"sondes {entete.get('version', '?')} · {len(sondes)} sonde(s) · "
        f"{len(liste_zones)} zone(s) de texte sur {len(fichiers)} fichier(s) · "
        f"règle : au moins {minimum} fichiers distincts"
    )

    resultats = confrontation.confronter(liste_zones, sondes, contexte)
    admises = [r for r in resultats if r.admise(minimum)]

    for resultat in sorted(resultats, key=lambda r: (-len(r.fichiers), r.sonde.nom)):
        _ecrire("")
        _ecrire("=" * 78)
        rappel = f" [déclaré : {resultat.sonde.statut}]" if resultat.sonde.statut else ""
        _ecrire(f"{resultat.sonde.nom}{rappel}")
        if resultat.sonde.notion:
            _ecrire(f"  notion : {resultat.sonde.notion}")
        _ecrire(f"  {resultat.verdict(minimum)} · {len(resultat.attestations)} zone(s)")
        if resultat.ecartees:
            _ecrire(f"  {resultat.ecartees} écartée(s) par l'anti-motif")
        par_fichier: dict[str, list] = {}
        for attestation in resultat.attestations:
            par_fichier.setdefault(attestation.fichier, []).append(attestation)
        for fichier, liste in sorted(par_fichier.items()):
            _ecrire(f"  [{fichier}] {len(liste)} zone(s)")
            for attestation in liste[: args.extraits]:
                _ecrire(f"      {attestation.origine}  ({attestation.zone})")
                _ecrire(f"        …{attestation.extrait[:170]}…")

    _ecrire("")
    _ecrire("=" * 78)
    _ecrire(f"{len(admises)}/{len(resultats)} sonde(s) atteignent le seuil de {minimum} fichiers.")
    # Une sonde déjà créée qui retombe sous le seuil sur un corpus élargi n'est
    # pas un détail : c'est une notion du référentiel qui n'était attestée que
    # par l'échantillon.
    regressions = [
        r for r in resultats if r.sonde.statut == "creee" and not r.admise(minimum)
    ]
    if regressions:
        _ecrire("")
        _ecrire(
            f"⚠ {len(regressions)} notion(s) DÉJÀ CRÉÉE(S) ne repassent pas le seuil "
            "sur ce corpus — à réexaminer, elles ne tenaient peut-être qu'à "
            "l'échantillon :"
        )
        for resultat in regressions:
            _ecrire(f"    {resultat.sonde.notion or resultat.sonde.nom} "
                    f"({len(resultat.fichiers)} fichier(s))")
    nouvelles = [
        r for r in resultats if r.sonde.statut in ("candidate", "ouverte") and r.admise(minimum)
    ]
    if nouvelles:
        _ecrire("")
        _ecrire(f"→ {len(nouvelles)} candidate(s) franchissent le seuil et sont à rédiger :")
        for resultat in nouvelles:
            _ecrire(f"    {resultat.sonde.notion or '(sans notion proposée) ' + resultat.sonde.nom}"
                    f" — {', '.join(resultat.fichiers)}")

    # `--sortie` global sert déjà au dossier du référentiel : la sortie de la
    # confrontation porte donc un dest distinct, sous peine d'écraser l'un par
    # l'autre sans que rien ne le dise.
    if args.sortie_confrontation:
        destination = Path(args.sortie_confrontation)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                confrontation.en_json(resultats, liste_zones, chemins, minimum),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _ecrire(f"écrit : {destination}")
    return 0


# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="etage0",
        description="Construit un référentiel de notions attribuables depuis un programme officiel.",
    )
    analyseur.add_argument(
        "--fournisseur",
        choices=["anthropic"],
        help="surcharge ETAGE0_FOURNISSEUR (point d'architecture : un seul fournisseur est branché)",
    )
    analyseur.add_argument("--modele", help="surcharge ETAGE0_MODELE")
    analyseur.add_argument("--sortie", help="surcharge ETAGE0_SORTIE")
    analyseur.add_argument("--etalon", help="dossier des sections écrites à la main")
    sous = analyseur.add_subparsers(dest="commande", required=True)

    p_seg = sous.add_parser("segmenter", help="segmentation déterministe, aucun appel LLM")
    p_seg.add_argument("--detail", action="store_true", help="imprime chaque unité")
    p_seg.add_argument("--sortie-json", dest="sortie", help="écrit les unités en JSON")
    p_seg.set_defaults(fonction=cmd_segmenter)

    p_cons = sous.add_parser("construire", help="segmente puis soumet au critère d'admission")
    p_cons.add_argument("--dry-run", action="store_true", help="affiche les prompts, n'appelle rien")
    p_cons.add_argument("--section", help="en dry-run, limite l'affichage à une section")
    p_cons.add_argument("--rejouer", action="store_true", help="ignore et purge le journal")
    p_cons.add_argument(
        "--strict", action="store_true",
        help="sort en erreur à la première anomalie de section, ET fait échouer "
             "la commande sur un défaut d'intégrité du contrôle final. Sans lui, "
             "le contrôle rapporte tout mais le référentiel est publié : bloquer "
             "la publication d'un référentiel complet arrête toute la chaîne aval.",
    )
    p_cons.set_defaults(fonction=cmd_construire)

    p_inj = sous.add_parser(
        "injecter",
        help="régénère UNE section du programme et l'ajoute au référentiel écrit",
    )
    p_inj.add_argument("--section", required=True, help="section du programme, ex. 4.3")
    p_inj.add_argument("--dry-run", action="store_true", help="affiche le prompt, n'appelle rien")
    p_inj.add_argument("--simuler", action="store_true", help="appelle et valide, mais n'écrit pas")
    p_inj.add_argument("--rejouer", action="store_true", help="ignore l'entrée de journal existante")
    p_inj.set_defaults(fonction=cmd_injecter)

    p_eta = sous.add_parser("etalon", help="rejoue la comparaison à l'étalon, sans régénérer")
    p_eta.add_argument("dossier", nargs="?", help="dossier sections/ (défaut : ETAGE0_SORTIE/sections)")
    p_eta.add_argument(
        "--seuil", type=float, default=ref.SEUIL_SIMILARITE,
        help=f"seuil d'appariement par similarité (défaut {ref.SEUIL_SIMILARITE})",
    )
    p_eta.set_defaults(fonction=cmd_etalon)

    p_ren = sous.add_parser("renvois", help="passe finale : résout les `voir` d'un référentiel écrit")
    p_ren.add_argument("dossier", nargs="?", help="dossier sections/ (défaut : ETAGE0_SORTIE/sections)")
    p_ren.set_defaults(fonction=cmd_renvois)

    p_exc = sous.add_parser("exclusions", help="classe les mentions restrictives du programme")
    p_exc.add_argument("--dry-run", action="store_true")
    p_exc.set_defaults(fonction=cmd_exclusions)

    p_conf = sous.add_parser(
        "confronter",
        help="cherche dans le corpus les notions que le programme ne nomme pas ; n'appelle rien",
    )
    p_conf.add_argument("corpus", nargs="+", help="fichiers JSON produits par l'étage 1")
    p_conf.add_argument("--sondes", default="referentiel/sondes.yaml")
    p_conf.add_argument("--sonde", help="ne joue qu'une sonde (correspondance sur le nom)")
    p_conf.add_argument("--minimum", type=int, help="surcharge la règle des N fichiers distincts")
    p_conf.add_argument("--extraits", type=int, default=2, help="extraits affichés par fichier")
    p_conf.add_argument("--sortie", dest="sortie_confrontation",
                        help="écrit le relevé complet en JSON")
    p_conf.set_defaults(fonction=cmd_confronter)

    args = analyseur.parse_args(argv)
    config = Config.depuis_env()
    if args.fournisseur:
        config = replace(config, fournisseur=args.fournisseur)
    if args.modele:
        config = replace(config, modele=args.modele)
    if args.sortie:
        config = replace(config, sortie=Path(args.sortie))
    if args.etalon:
        config = replace(config, etalon=Path(args.etalon))
    return args.fonction(config, args)


if __name__ == "__main__":
    raise SystemExit(main())
