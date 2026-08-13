"""Assemblage, émission et validation du référentiel.

Tout ce qui est ici est déterministe : le modèle a décidé, ce module met en
forme, détecte les incohérences et mesure. La validation n'échoue pas sur un
écart de cible (80–120 notions) — elle le rapporte : le dimensionnement se
décide sur la mesure du corpus, pas sur un seuil posé a priori.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from .config import Config, Profil
from .segmentation import Unite

RE_INFINITIF = re.compile(r"^[A-ZÉÈÀÇ][\wéèêàçîôûï'-]*(?:er|ir|re|oir)\b", re.UNICODE)


@dataclass
class Anomalie:
    gravite: str  # bloquant | avertissement
    message: str
    #: Code de règle. Il sert à deux choses : porter la sévérité par la
    #: table plutôt que par le site d'appel, et nommer la règle dans le
    #: rapport — « ça a échoué » sans dire sur quelle règle oblige à
    #: relire le code pour comprendre.
    code: str = ""


@dataclass
class Referentiel:
    notions: list[dict[str, Any]] = field(default_factory=list)
    refus: list[dict[str, Any]] = field(default_factory=list)
    anomalies: list[Anomalie] = field(default_factory=list)

    def par_section(self) -> dict[str, list[dict[str, Any]]]:
        groupes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for notion in self.notions:
            groupes[notion["section_id"]].append(notion)
        return dict(groupes)


def assembler(
    decisions_par_section: dict[str, list[dict[str, Any]]],
    unites: dict[str, Unite],
    profil: Profil,
    notions_existantes: list[dict[str, Any]] | None = None,
) -> Referentiel:
    """Met en forme les décisions.

    `notions_existantes` sert lorsqu'on régénère une seule section pour
    l'injecter dans un référentiel déjà écrit : les slugs déjà pris et les
    cibles de renvoi déjà disponibles en font partie, sans quoi l'injection
    produirait des doublons et des renvois faussement morts.
    """
    referentiel = Referentiel()
    deja_la = notions_existantes or []
    vus: Counter[str] = Counter({n["slug"]: 1 for n in deja_la})

    for section_id, decisions in sorted(decisions_par_section.items()):
        for decision in decisions:
            unite = unites.get(decision["unite_id"])
            source = (
                f"{unite.section.id}:{unite.ligne_debut}-{unite.ligne_fin}"
                if unite
                else decision["unite_id"]
            )
            if decision["verdict"] == "refuse":
                referentiel.refus.append(
                    {
                        "unite_id": decision["unite_id"],
                        "source": source,
                        "extrait": (unite.notions or unite.texte)[:180] if unite else "",
                        "raison": decision["raison"],
                    }
                )
                continue

            for brute in decision["notions"]:
                slug = brute["slug"]
                vus[slug] += 1
                if vus[slug] > 1:
                    slug = f"{slug}_{vus[brute['slug']]}"
                    referentiel.anomalies.append(anomalie(
                        "slug_duplique",
                        f"slug dupliqué {brute['slug']!r} renommé en {slug!r} "
                        f"(source {source}) — candidat à la fusion",
                    ))
                referentiel.notions.append(
                    {
                        "id": f"{brute['section_cible']}.{slug}",
                        "slug": slug,
                        "section_id": brute["section_cible"],
                        "libelle": brute["libelle"],
                        "semestre": unite.semestre if unite else None,
                        "origine": {
                            "genre": unite.genre if unite else "inconnu",
                            "cellule": brute["origine_cellule"],
                            "source": source,
                            "verdict": decision["verdict"],
                        },
                        "definition_operatoire": brute["definition_operatoire"],
                        "declencheurs": brute["declencheurs"],
                        "exclusions": brute["exclusions"],
                        "exemples_positifs": [],  # remplis par la passe corpus
                        "exemples_negatifs": [],
                        "langages_plausibles": brute["langages_plausibles"],
                        "statut": "actif",  # rare / jamais_observe : calculés à l'étage 4
                    }
                )

    _resoudre_renvois(referentiel, profil, deja_la)
    return referentiel


# --------------------------------------------------------------------------- #
# Renvois. Un `voir` est typé : il désigne une NOTION ou une SECTION, et les
# deux ne se vérifient pas dans le même espace de noms. C'est faute de cette
# distinction que `complexite_algo` — un identifiant de section parfaitement
# valide — passait pour un renvoi mort vers une notion.
# --------------------------------------------------------------------------- #

TYPE_NOTION = "notion"
TYPE_SECTION = "section"


def _resoudre_renvois(
    referentiel: Referentiel,
    profil: Profil,
    notions_existantes: list[dict[str, Any]] | None = None,
) -> None:
    """Transforme les `voir_slug` en renvois typés et résolus.

    Ne signale rien : c'est `verifier_renvois` qui rapporte, et elle seule, sur
    l'ensemble final. Un renvoi non résolu sort ici avec `voir: null` et son
    texte d'origine conservé dans `voir_brut` — sans quoi la faute de frappe
    ne serait plus rattrapable à la relecture.
    """
    connues = (notions_existantes or []) + referentiel.notions
    par_slug = {n["slug"]: n["id"] for n in connues}
    par_id = {n["id"] for n in connues}
    sections = set(profil.ids_sections_cibles)

    for notion in referentiel.notions:
        resolues = []
        for exclusion in notion["exclusions"]:
            if "voir_slug" not in exclusion:
                # déjà résolue lors d'une passe antérieure : on n'y retouche pas,
                # le `voir_slug` d'origine n'existe plus pour la reconstruire.
                resolues.append(exclusion)
                continue
            cible = exclusion.get("voir_slug")
            resolue: dict[str, Any] = {
                "motif": exclusion["motif"],
                "voir": None,
                "voir_type": None,
            }
            if cible:
                if cible in par_slug:
                    resolue["voir"], resolue["voir_type"] = par_slug[cible], TYPE_NOTION
                elif cible in par_id:
                    resolue["voir"], resolue["voir_type"] = cible, TYPE_NOTION
                elif cible in sections:
                    # Renvoi vers une aire entière plutôt qu'une notion : c'est
                    # plus grossier que voulu, mais ce n'est pas mort.
                    resolue["voir"], resolue["voir_type"] = cible, TYPE_SECTION
                else:
                    resolue["voir_brut"] = cible
            resolues.append(resolue)
        notion["exclusions"] = resolues


FATAL = "bloquant"
ATTENDU = "avertissement"

#: Sévérité du CONTRÔLE FINAL, par code de règle. La distinction fatal /
#: réparable existait au niveau des unités, dans le registre de règles ; elle
#: n'avait jamais été appliquée ici. Une table plutôt qu'une chaîne répétée à
#: chaque `Anomalie(...)` : la sévérité se lit et se change en un seul endroit.
#:
#: Ce qui est FATAL est un défaut d'INTÉGRITÉ — le référentiel serait
#: inutilisable. Ce qui est ATTENDU est un défaut de GRANULARITÉ, normal sur
#: une construction brute : les mesurer là revient à juger une chaîne
#: incomplète selon les critères de la chaîne complète. Le contrôle aurait
#: toujours raison, et ce serait toujours inutile.
SEVERITE_CONTROLE: dict[str, str] = {
    # intégrité
    "renvoi_non_resolu": FATAL,
    "renvoi_sans_type": FATAL,
    "renvoi_mort_notion": FATAL,
    "voir_type_inconnu": FATAL,
    "identifiant_double": FATAL,
    "section_perdue": FATAL,
    # granularité
    "renvoi_vers_section": ATTENDU,
    "renvoi_mort_section": ATTENDU,
    "section_au_dessus_seuil": ATTENDU,
    "section_vide": ATTENDU,
    "notions_au_dessus_cible": ATTENDU,
    "notions_sous_cible": ATTENDU,
    "libelle_sans_infinitif": ATTENDU,
    "slug_duplique": ATTENDU,
    "unite_rejetee": ATTENDU,
    "auto_exclusion": ATTENDU,
}

#: Avertissements normaux à ce stade, avec l'étape qui les résorbe. Les
#: afficher sans cette mention fait passer pour un défaut l'état attendu du
#: pipeline.
RESORBE_PAR: dict[str, str] = {
    "notions_au_dessus_cible": "`etage0 purger` (retrait des annexes)",
    "section_au_dessus_seuil": "`etage0 purger` (retrait des annexes)",
    "section_vide": "`etage0 confronter` (alimentation par le corpus)",
    "renvoi_vers_section": "l'arbitrage manuel des renvois",
    "renvoi_mort_section": "l'arbitrage manuel des renvois",
}


def anomalie(code: str, message: str) -> Anomalie:
    """Fabrique une anomalie dont la sévérité vient de la table, pas du site
    d'appel. Un code absent est FATAL par défaut : mieux vaut bloquer sur une
    règle qu'on a oublié de classer que la laisser passer en silence."""
    return Anomalie(SEVERITE_CONTROLE.get(code, FATAL), message, code)


def verifier_renvois(
    notions: list[dict[str, Any]], ids_sections: set[str]
) -> list[Anomalie]:
    """Passe finale : chaque `voir` résout-il, sur le référentiel COMPLET ?

    La vérification faite à la résolution ne suffit pas : elle ne voit que les
    sections produites par l'appel en cours. Un renvoi vers une notion d'une
    section générée plus tard — ou injectée à la main après coup — n'y est pas
    couvert. Cette passe se fait sur l'ensemble final, et sur lui seul.
    """
    anomalies: list[Anomalie] = []
    ids_notions = {n["id"] for n in notions}
    for notion in notions:
        for exclusion in notion.get("exclusions") or []:
            cible, type_cible = exclusion.get("voir"), exclusion.get("voir_type")
            brut = exclusion.get("voir_brut")
            if cible is None:
                if brut:
                    anomalies.append(anomalie(
                        "renvoi_non_resolu",
                        f"{notion['id']} : renvoi non résolu vers {brut!r}",
                    ))
                continue
            if type_cible is None:
                anomalies.append(anomalie(
                    "renvoi_sans_type",
                    f"{notion['id']} : renvoi vers {cible!r} sans `voir_type` — "
                    "impossible de savoir dans quel espace de noms le vérifier",
                ))
            elif type_cible == TYPE_NOTION and cible not in ids_notions:
                anomalies.append(anomalie(
                    "renvoi_mort_notion",
                    f"{notion['id']} : renvoi mort vers la notion {cible!r}",
                ))
            elif type_cible == TYPE_SECTION and cible not in ids_sections:
                # Pointer une section absente du profil est un défaut de
                # PORTÉE, pas d'intégrité : la section existe au programme,
                # elle n'est simplement pas une cible du profil.
                anomalies.append(anomalie(
                    "renvoi_mort_section",
                    f"{notion['id']} : renvoi vers la section {cible!r}, absente des "
                    "sections cibles du profil",
                ))
            elif type_cible == TYPE_SECTION:
                anomalies.append(
                    anomalie(
                        "renvoi_vers_section",
                        f"{notion['id']} : renvoi vers la section {cible!r} et non vers "
                        "une notion — exclusion moins tranchante que prévu",
                    )
                )
            elif type_cible != TYPE_NOTION:
                anomalies.append(
                    anomalie("voir_type_inconnu",
                             f"{notion['id']} : `voir_type` inconnu {type_cible!r}")
                )
            if cible == notion["id"]:
                anomalies.append(
                    anomalie("auto_exclusion", f"{notion['id']} : s'exclut elle-même")
                )
    return anomalies


def charger_notions(dossier: Path) -> list[dict[str, Any]]:
    """Relit les notions déjà écrites sur disque, section par section.

    Permet de rejouer les passes de validation sans régénérer : c'est ce qui
    rend une section injectée à la main vérifiable comme les autres.
    """
    notions: list[dict[str, Any]] = []
    for fichier in sorted(dossier.glob("*.yaml")):
        donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
        section = (donnees.get("section") or {}).get("id")
        for notion in donnees.get("notions") or []:
            notions.append({**notion, "section_id": notion.get("section_id", section)})
    return notions


def valider(referentiel: Referentiel, profil: Profil) -> list[Anomalie] :
    anomalies = list(referentiel.anomalies)
    cibles = profil.cibles
    total = len(referentiel.notions)

    anomalies.extend(
        verifier_renvois(referentiel.notions, set(profil.ids_sections_cibles))
    )

    identifiants = Counter(n["id"] for n in referentiel.notions)
    for identifiant, compte in identifiants.items():
        if compte > 1:
            anomalies.append(anomalie("identifiant_double",
                                      f"identifiant en double : {identifiant}"))

    for notion in referentiel.notions:
        if not RE_INFINITIF.match(notion["libelle"]):
            anomalies.append(anomalie(
                "libelle_sans_infinitif",
                f"{notion['id']} : libellé « {notion['libelle']} » ne commence "
                "pas par un verbe à l'infinitif (nommage par l'objet ?)",
            ))

    par_section = referentiel.par_section()
    plafond = cibles.get("notions_par_section_max")
    if plafond:
        for section_id, notions in par_section.items():
            if len(notions) > plafond:
                anomalies.append(anomalie(
                    "section_au_dessus_seuil",
                    f"section {section_id} : {len(notions)} notions (> {plafond})",
                ))
    for section in profil.sections_cibles:
        if section["id"] not in par_section:
            anomalies.append(anomalie(
                "section_vide",
                f"section {section['id']} vide — à alimenter par la passe corpus "
                "ou à retirer du profil",
            ))

    mini, maxi = cibles.get("notions_min"), cibles.get("notions_max")
    if mini and total < mini:
        anomalies.append(anomalie(
            "notions_sous_cible",
            f"{total} notions (cible ≥ {mini}) : granularité trop grosse",
        ))
    if maxi and total > maxi:
        anomalies.append(anomalie(
            "notions_au_dessus_cible",
            f"{total} notions (cible ≤ {maxi}) : granularité trop fine",
        ))
    return anomalies


# --------------------------------------------------------------------------- #


def ecrire(
    referentiel: Referentiel,
    config: Config,
    meta: dict[str, Any],
    unites_rejetees: list[dict[str, str]] | None = None,
    reparations: list[dict[str, str]] | None = None,
    anomalies: list[Anomalie] | None = None,
) -> None:
    profil = config.profil
    racine = config.sortie
    (racine / "sections").mkdir(parents=True, exist_ok=True)

    par_section = referentiel.par_section()
    libelles = {s["id"]: s for s in profil.sections_cibles}
    fichiers = []

    for ordre, section in enumerate(profil.sections_cibles, start=1):
        notions = par_section.get(section["id"], [])
        nom = f"{ordre:02d}-{section['id'].replace('_', '-')}.yaml"
        contenu = {
            "section": {
                "id": section["id"],
                "libelle": section["libelle"],
                "ordre": ordre,
                "perimetre": " ".join(section.get("perimetre", "").split()),
            },
            "notions": [
                {k: v for k, v in n.items() if k != "section_id"} for n in notions
            ],
        }
        (racine / "sections" / nom).write_text(
            yaml.safe_dump(contenu, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
        fichiers.append({"id": section["id"], "fichier": f"sections/{nom}", "notions": len(notions)})

    # Une réparation non tracée est le même défaut qu'une section perdue sans
    # bruit : ce qui a été normalisé doit se lire dans le manifeste, unité par
    # unité, sans avoir à relire les journaux.
    rejets = list(unites_rejetees or [])
    reparees = list(reparations or [])
    operations = [
        "génération automatique depuis le programme officiel (étage 0)",
        f"{len(referentiel.refus)} unité(s) refusée(s) au critère d'admission",
    ]
    if reparees:
        operations.append(
            f"{len(reparees)} réparation(s) de contrat appliquée(s) — voir `reparations`"
        )
    if rejets:
        operations.append(
            f"{len(rejets)} unité(s)/notion(s) rejetée(s) au contrat — voir `unites_rejetees`"
        )

    manifeste = {
        "version": config.version_referentiel,
        "date": date.today().isoformat(),
        "matiere": profil.matiere,
        "programme_source": str(config.programme.name),
        "profil": str(profil.chemin.name),
        "genere_par": meta,
        "sections": fichiers,
        "notions_total": len(referentiel.notions),
        "reparations": reparees,
        "unites_rejetees": rejets,
        # Le contrôle final ne fait plus échouer la commande : ses constats
        # doivent donc être RECENSÉS, pas seulement affichés. Un défaut
        # d'intégrité qui ne vit que dans un flux stderr disparaît avec le
        # terminal, et le référentiel publié ne saurait plus ce qu'on lui
        # reproche.
        "anomalies": [
            {"gravite": a.gravite, "code": a.code, "message": a.message}
            for a in (anomalies or [])
        ],
        "migrations": {},
        "changelog": [
            {
                "version": config.version_referentiel,
                "date": date.today().isoformat(),
                "operations": operations,
            }
        ],
    }
    (racine / "manifest.yaml").write_text(
        yaml.safe_dump(manifeste, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )

    (racine / "refus.json").write_text(
        json.dumps(referentiel.refus, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def injecter(
    produit: Referentiel,
    config: Config,
    section_programme: str,
    reparations: list[dict[str, str]],
    rejets: list[dict[str, str]],
) -> dict[str, int]:
    """Ajoute les notions d'une section régénérée à un référentiel déjà écrit.

    N'ouvre que les fichiers concernés, et n'y ajoute qu'à la fin de `notions`.
    Le reste du référentiel — y compris les exemples de confrontation et les
    purges faites à la main — n'est pas relu, donc pas réécrit.
    """
    racine = config.sortie
    dossier = racine / "sections"
    par_section = produit.par_section()

    fichiers_par_section = {}
    for fichier in sorted(dossier.glob("*.yaml")):
        donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
        identifiant = (donnees.get("section") or {}).get("id")
        if identifiant:
            fichiers_par_section[identifiant] = (fichier, donnees)

    ajoutees: dict[str, int] = {}
    for section_id, notions in par_section.items():
        if section_id not in fichiers_par_section:
            raise ValueError(
                f"section cible {section_id!r} sans fichier dans {dossier} — "
                "le profil et le référentiel écrit ont divergé"
            )
        fichier, donnees = fichiers_par_section[section_id]
        existants = {n["id"] for n in donnees.get("notions") or []}
        nouvelles = [
            {k: v for k, v in n.items() if k != "section_id"}
            for n in notions
            if n["id"] not in existants
        ]
        if not nouvelles:
            continue
        donnees.setdefault("notions", []).extend(nouvelles)
        fichier.write_text(
            yaml.safe_dump(donnees, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
        ajoutees[f"sections/{fichier.name}"] = len(nouvelles)

    # --- refus : la section injectée en a, refus.json doit les porter ------ #
    chemin_refus = racine / "refus.json"
    if produit.refus:
        anciens = (
            json.loads(chemin_refus.read_text(encoding="utf-8"))
            if chemin_refus.is_file()
            else []
        )
        connus = {r["unite_id"] for r in anciens}
        anciens.extend(r for r in produit.refus if r["unite_id"] not in connus)
        chemin_refus.write_text(
            json.dumps(anciens, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- manifeste : recompté sur le disque, jamais sur une variable ------- #
    chemin_manifeste = racine / "manifest.yaml"
    manifeste = yaml.safe_load(chemin_manifeste.read_text(encoding="utf-8")) or {}
    total = 0
    for entree in manifeste.get("sections") or []:
        chemin = racine / entree["fichier"]
        donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        entree["notions"] = len(donnees.get("notions") or [])
        total += entree["notions"]
    manifeste["notions_total"] = total
    manifeste["date"] = date.today().isoformat()
    manifeste.setdefault("reparations", []).extend(reparations)
    manifeste.setdefault("unites_rejetees", []).extend(rejets)

    operations = [
        f"section {section_programme} du programme régénérée seule et injectée "
        f"({sum(ajoutees.values())} notion(s), {len(produit.refus)} refus)"
    ]
    if reparations:
        operations.append(
            f"{len(reparations)} réparation(s) de contrat appliquée(s) — voir `reparations`"
        )
    if rejets:
        operations.append(
            f"{len(rejets)} objet(s) rejeté(s) au contrat — voir `unites_rejetees`"
        )
    manifeste.setdefault("changelog", []).append(
        {
            "version": config.version_referentiel,
            "date": date.today().isoformat(),
            "operations": operations,
        }
    )
    chemin_manifeste.write_text(
        yaml.safe_dump(manifeste, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    return ajoutees


# --------------------------------------------------------------------------- #


#: Au-dessous, deux libellés ne décrivent pas la même action.
#:
#: Réglé à la main sur les paires du référentiel courant. Monté de 0,62 à 0,70
#: après contrôle : à 0,62, « Prouver une équivalence par double implication »
#: appariait « Résoudre une instance 2-SAT par le graphe d'implications » (0,65)
#: sur la seule sous-chaîne « implication ». Les vraies paires observées sont
#: toutes à 0,72 ou au-dessus. Mieux vaut rater une paire et la voir en
#: `manquants` que d'en inventer une et la compter comme un succès : le second
#: cas gonfle le rappel sans que rien ne le signale.
SEUIL_SIMILARITE = 0.70


def _normaliser_libelle(texte: str) -> str:
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn"
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sans_accent.lower()).split())


def _similarite(a_libelle: str, a_id: str, b_libelle: str, b_id: str) -> float:
    """Ressemblance de deux notions : le meilleur des deux angles.

    Le libellé et le slug se dégradent différemment. « induction_structurelle »
    contre « prouver_par_induction_structurelle » se rattrape sur le slug ;
    deux slugs sans rapport pour une même action se rattrapent sur le libellé.
    """
    lib = SequenceMatcher(
        None, _normaliser_libelle(a_libelle), _normaliser_libelle(b_libelle)
    ).ratio()
    slug_a, slug_b = a_id.split(".", 1)[-1], b_id.split(".", 1)[-1]
    slug = SequenceMatcher(None, slug_a, slug_b).ratio()
    # Jaccard, et non un recouvrement rapporté au plus court : celui-ci sature
    # à 1 dès que le slug le plus court est inclus dans l'autre, si bien que
    # `induction_structurelle` appariait aussi bien
    # `parcourir_formule_par_induction_structurelle` que la notion voulue.
    jetons_a, jetons_b = set(slug_a.split("_")), set(slug_b.split("_"))
    jaccard = (
        len(jetons_a & jetons_b) / len(jetons_a | jetons_b) if jetons_a | jetons_b else 0.0
    )
    return max(lib, slug, jaccard)


def normaliser_renvois(
    referentiel: Referentiel, seuil: float = SEUIL_SIMILARITE
) -> list[dict[str, Any]]:
    """Repointe les renvois non résolus vers la notion existante la plus proche.

    Le modèle invente des identifiants de cible : il écrit
    `prouver_terminaison_variant` là où la notion s'appelle autrement. Ce n'est
    pas une notion manquante, c'est un mot différent pour la même chose — et
    laisser quatre renvois de vocabulaire bloquer la publication d'un
    référentiel complet, payé 3 $, est disproportionné.

    L'appariement est celui de l'étalon, `_similarite`, et pour la même raison :
    le libellé et le slug se dégradent différemment, on garde le meilleur des
    deux angles. La même prudence aussi — **au-dessous du seuil on ne repointe
    pas**, le renvoi reste non résolu et donc bloquant. Un repointage douteux
    serait pire qu'un blocage : il ferait dire à une notion qu'elle en exclut
    une autre, à tort et sans trace.

    Rend la liste de TOUS les cas examinés, repointés ou non. Les seconds
    portent leur meilleur candidat et son score : c'est exactement ce qu'il faut
    pour décider à la main, et le taire obligerait à refaire la mesure.
    """
    examens: list[dict[str, Any]] = []
    candidats = [(n["libelle"], n["id"]) for n in referentiel.notions]

    for notion in referentiel.notions:
        for exclusion in notion.get("exclusions") or []:
            brut = exclusion.get("voir_brut")
            if exclusion.get("voir") is not None or not brut:
                continue
            meilleur_id, meilleur_libelle, meilleur_score = None, None, 0.0
            for libelle, identifiant in candidats:
                if identifiant == notion["id"]:
                    continue  # une notion ne s'exclut pas elle-même
                score = _similarite(brut, brut, libelle, identifiant)
                if score > meilleur_score:
                    meilleur_id, meilleur_libelle, meilleur_score = identifiant, libelle, score

            repointe = meilleur_id is not None and meilleur_score >= seuil
            if repointe:
                exclusion["voir"] = meilleur_id
                exclusion["voir_type"] = TYPE_NOTION
                exclusion.pop("voir_brut", None)
            examens.append({
                "section": notion["section_id"],
                "cible": notion["id"],
                "regle": "renvoi_repointe" if repointe else "renvoi_sans_candidat",
                "constat": f"renvoi non résolu vers {brut!r}",
                "reparation": (
                    f"repointé vers {meilleur_id} (score {meilleur_score:.2f})"
                    if repointe else
                    f"NON repointé — meilleur candidat {meilleur_id} "
                    f"(score {meilleur_score:.2f} < {seuil})"
                ),
                "renvoi_origine": brut,
                "cible_retenue": meilleur_id if repointe else None,
                "meilleur_candidat": meilleur_id,
                "libelle_candidat": meilleur_libelle,
                "score": round(meilleur_score, 4),
                "repointe": repointe,
            })
    return examens


def comparer_etalon(
    referentiel: Referentiel, dossier_etalon: Path, seuil: float = SEUIL_SIMILARITE
) -> dict[str, Any]:
    """Mesure le rappel du générateur contre les sections écrites à la main.

    Appariement en deux temps. D'abord l'identifiant exact : c'est le seul
    appariement qui ne demande aucun arbitrage. Puis, sur ce qui reste, la
    similarité de libellé et de slug — parce qu'un étalon écrit à la main ne
    peut pas deviner le mot que le générateur choisira, et qu'un rappel de 0,0
    obtenu contre `induction_structurelle` / `prouver_par_induction_structurelle`
    mesure l'écart de vocabulaire, pas celui du référentiel.

    Les paires du second temps sont rendues dans `appariements_par_similarite`
    pour être contrôlées à l'œil : elles ne sont pas des succès démontrés.
    """
    attendus: dict[str, list[dict[str, str]]] = {}
    for fichier in sorted(dossier_etalon.glob("*.yaml")):
        donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
        section = (donnees.get("section") or {}).get("id")
        if not section:
            continue
        attendus[section] = [
            {"id": n["id"], "libelle": n.get("libelle", "")}
            for n in donnees.get("notions", [])
        ]

    obtenus = {n["id"]: n for n in referentiel.notions}

    # --- premier temps : identifiant exact --------------------------------- #
    exacts: dict[str, str] = {}
    restants: list[tuple[str, dict[str, str]]] = []
    for section, notions in attendus.items():
        for notion in notions:
            if notion["id"] in obtenus:
                exacts[notion["id"]] = notion["id"]
            else:
                restants.append((section, notion))

    # --- second temps : similarité, appariement un-à-un, meilleur d'abord --- #
    libres = {i for i in obtenus if i not in set(exacts.values())}
    candidats = [
        (
            _similarite(
                notion["libelle"], notion["id"], obtenus[cible]["libelle"], cible
            ),
            notion["id"],
            cible,
            section,
        )
        for section, notion in restants
        for cible in libres
    ]
    candidats.sort(key=lambda c: (-c[0], c[1], c[2]))

    apparies: dict[str, dict[str, Any]] = {}
    pris: set[str] = set()
    for score, identifiant_etalon, cible, section in candidats:
        if score < seuil or identifiant_etalon in apparies or cible in pris:
            continue
        apparies[identifiant_etalon] = {
            "etalon": identifiant_etalon,
            "obtenu": cible,
            "score": round(score, 3),
            "libelle_etalon": next(
                n["libelle"] for _, n in restants if n["id"] == identifiant_etalon
            ),
            "libelle_obtenu": obtenus[cible]["libelle"],
            "meme_section": obtenus[cible]["section_id"] == section,
        }
        pris.add(cible)

    detail = {}
    for section, notions in attendus.items():
        identifiants = [n["id"] for n in notions]
        detail[section] = {
            "attendus": len(identifiants),
            "exacts": len([i for i in identifiants if i in exacts]),
            "par_similarite": len([i for i in identifiants if i in apparies]),
            "manquants": [
                i for i in identifiants if i not in exacts and i not in apparies
            ],
        }

    total = sum(d["attendus"] for d in detail.values())
    total_exacts = sum(d["exacts"] for d in detail.values())
    total_similaires = sum(d["par_similarite"] for d in detail.values())
    hors_section = sorted(
        p["etalon"] for p in apparies.values() if not p["meme_section"]
    )
    return {
        "sections_comparees": sorted(detail),
        "seuil_similarite": seuil,
        "rappel_exact": round(total_exacts / total, 3) if total else None,
        "rappel_avec_similarite": (
            round((total_exacts + total_similaires) / total, 3) if total else None
        ),
        "appariements_par_similarite": sorted(
            apparies.values(), key=lambda p: -p["score"]
        ),
        "apparies_hors_section": hors_section,
        "detail": detail,
        "note": (
            "Deux temps. `rappel_exact` ne compte que les identifiants identiques : "
            "c'est un plancher, insensible au vocabulaire. `rappel_avec_similarite` "
            f"y ajoute les paires appariées au-dessus de {seuil} sur le libellé ou le "
            "slug — À CONTRÔLER une par une dans `appariements_par_similarite` avant "
            "d'en tirer un chiffre. Une paire `meme_section: false` signale une notion "
            "retrouvée mais rangée ailleurs que dans l'étalon."
        ),
    }
