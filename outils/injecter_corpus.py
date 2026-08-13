"""Injecte les notions ATTESTÉES PAR LE CORPUS, et elles seules.

Deux règles, posées avant la passe :
  - une notion de `preuve` n'est admise que si elle est attestée dans au moins
    DEUX fichiers distincts. 2024_InfoF étant identique à 2024_InfoC, il ne
    compte pas comme fichier distinct ;
  - les cinq trous nommés à l'étape précédente sont confirmés ou infirmés par
    le corpus AVANT création — aucun n'est créé sur la seule foi de l'étalon.

Les `declencheurs` reprennent les tournures RÉELLES des énoncés, relevées à la
lecture, et non le vocabulaire du programme : c'était le défaut n°2 du rapport
de confrontation précédent.
"""
import os, sys
from pathlib import Path

os.chdir(r"c:\Users\natha\Downloads\analyse sujets")
sys.path.insert(0, ".")

from dataclasses import replace
from etage0 import referentiel as ref
from etage0.config import Config

APPLIQUER = "--appliquer" in sys.argv


def notion(identifiant, libelle, definition, declencheurs, exclusions, exemples,
           langages=("theorique",), fichiers=()):
    section, slug = identifiant.split(".", 1)
    return {
        "id": identifiant,
        "slug": slug,
        "section_id": section,
        "libelle": libelle,
        "semestre": None,
        "origine": {
            "genre": "corpus",
            "cellule": "confrontation",
            "source": "corpus:" + ",".join(fichiers),
            "verdict": "atteste_corpus",
        },
        "definition_operatoire": definition,
        "declencheurs": list(declencheurs),
        "exclusions": [
            {"motif": m, "voir": v, "voir_type": ("notion" if v else None)}
            for m, v in exclusions
        ],
        "exemples_positifs": [{"source": s, "question": q} for s, q in exemples],
        "exemples_negatifs": [],
        "langages_plausibles": list(langages),
        "statut": "actif",
    }


INFO = "2024_Info-rapport"
EXO = "2022_InfoU-exercices"
TP = "2024_TPAlgo-MPI-rapport"
LCR = "2022_InfoLCR-rapport"
A, C = "2024_InfoA", "2024_InfoC"

NOTIONS = [
    # ------------------------------------------------------------------ #
    # Techniques de preuve — toutes à ≥ 2 fichiers distincts
    # ------------------------------------------------------------------ #
    notion(
        "preuve.demontrer_par_recurrence_numerique",
        "Démontrer une propriété par récurrence sur un paramètre entier",
        "La question demande d'établir une propriété indexée par un entier — taille, "
        "rang d'itération, nombre d'étapes — en traitant le cas de base puis l'hérédité. "
        "Retenir quand le paramètre de récurrence est un entier et non une structure.",
        ["Montrer par récurrence sur n que …",
         "On prouve par récurrence sur r que …",
         "Indication : on peut faire une récurrence sur le nombre de …"],
        [("La récurrence porte sur une structure de données et non sur un entier",
          "preuve.prouver_par_induction_structurelle"),
         ("Il s'agit de résoudre une récurrence de coût, pas d'établir une propriété",
          "complexite_algo.resoudre_recurrence_de_cout")],
        [(INFO, "Q1"), (INFO, "Q5"), (INFO, "Q6"), (EXO, "Q3"), (TP, "Q2")],
        fichiers=(INFO, EXO, TP),
    ),
    notion(
        "preuve.raisonner_par_absurde",
        "Raisonner par l'absurde pour établir une impossibilité",
        "La question demande de montrer qu'un objet ne peut pas exister ou qu'une borne "
        "ne peut pas être atteinte, en supposant le contraire et en dérivant une "
        "contradiction. Typique des résultats d'impossibilité.",
        ["Est-il possible de … ? Non, et prouvons-le par l'absurde",
         "Montrer qu'il n'existe pas de …",
         "On raisonne par l'absurde"],
        [("Un seul contre-exemple explicite suffit à conclure",
          "preuve.refuter_par_contre_exemple"),
         ("La contradiction vient d'un comptage de cases et d'objets",
          "preuve.conclure_par_principe_des_tiroirs")],
        [(INFO, "Q4"), (INFO, "Q7"), (EXO, "Q3"), (EXO, "Q4")],
        fichiers=(INFO, EXO),
    ),
    notion(
        "preuve.refuter_par_contre_exemple",
        "Réfuter un énoncé en exhibant un contre-exemple",
        "La question propose une propriété plausible — souvent l'optimalité d'un "
        "algorithme naïf — et demande de la réfuter en construisant une instance "
        "explicite où elle échoue.",
        ["Si oui, justifier ; si non, donner un contre-exemple",
         "Trouver des contre-exemples simples pour n = 2 et n = 3",
         "L'algorithme calcule-t-il toujours une solution, si elle existe ?"],
        [("L'impossibilité est générale et ne s'exhibe pas sur une instance",
          "preuve.raisonner_par_absurde"),
         ("Il s'agit de construire un jeu de tests couvrant, pas de réfuter",
          "correction.construire_jeu_tests_couverture")],
        [(INFO, "Q3"), (TP, "Q4")],
        fichiers=(INFO, TP),
    ),
    notion(
        "preuve.conclure_par_principe_des_tiroirs",
        "Conclure par le principe des tiroirs ou un argument de comptage",
        "La question demande d'établir qu'une collision, une répétition ou un "
        "dépassement est inévitable, en comparant un nombre d'objets à un nombre de "
        "places. Le cœur de la réponse est une inégalité de cardinaux.",
        ["Par le principe des tiroirs, au moins une case reçoit deux objets",
         "Montrer qu'il existe nécessairement deux … de même …",
         "Il n'y a que k paires possibles pour n éléments"],
        [("La contradiction ne repose pas sur un comptage de places",
          "preuve.raisonner_par_absurde"),
         ("La question demande de compter exactement, pas de conclure à une collision",
          None)],
        [(INFO, "Q7"), (EXO, "Q2"), (EXO, "Q6")],
        fichiers=(INFO, EXO),
    ),
    notion(
        "preuve.prouver_equivalence_par_double_implication",
        "Prouver une équivalence en traitant les deux implications",
        "L'énoncé pose un « si et seulement si » ou demande explicitement la "
        "réciproque, et attend les deux sens séparément — souvent un sens immédiat et "
        "un sens qui demande une construction.",
        ["Montrer que X si et seulement si Y",
         "Réciproquement, tout … peut-il être obtenu de cette manière ?",
         "Montrer les deux inclusions"],
        [("Un seul sens est demandé, l'autre est admis", None),
         ("L'équivalence porte sur deux formules logiques et s'établit par les lois usuelles",
          "logique.etablir_equivalence_par_lois")],
        [(INFO, "Q2"), (INFO, "Q7"), (EXO, "Q1"), (A, "Q3"), (C, "Q2"), (LCR, "Q4"), (TP, "Q3")],
        fichiers=(INFO, EXO, A, C, LCR, TP),
    ),
    # ------------------------------------------------------------------ #
    # Trous nommés — seuls les CONFIRMÉS sont créés
    # ------------------------------------------------------------------ #
    notion(
        "complexite_algo.evaluer_complexite_en_espace",
        "Évaluer la complexité en espace d'un algorithme",
        "La question demande l'ordre de grandeur de la mémoire occupée par un "
        "algorithme ou une structure en fonction de la taille de l'entrée, "
        "indépendamment du temps — souvent posée dans la même phrase que le temps, "
        "et à ne pas confondre avec lui.",
        ["Évaluer sa complexité en espace, ainsi que la complexité en temps des opérations",
         "Montrer que la complexité en espace de la construction est en O(g(n))",
         "Étudier sa terminaison, sa correction, sa complexité en espace et en temps"],
        [("Il s'agit du coût en temps et non de l'occupation mémoire",
          "complexite_algo.evaluer_complexite_algorithme"),
         ("L'occupation mesurée est celle d'un processus, pas celle d'un algorithme",
          "ressources.analyser_memoire_processus"),
         ("Le coût mémoire est celui de la pile d'appels récursifs",
          "ressources.analyser_cout_machine_appels_recursifs")],
        [(A, "Q14"), (TP, "Q1"), (TP, "Q10"), (LCR, "Q5")],
        langages=("theorique", "pseudocode"),
        fichiers=(A, TP, LCR),
    ),
    notion(
        "complexite_algo.etablir_borne_inferieure",
        "Établir une borne inférieure sur un coût ou sur la taille d'un objet",
        "La question demande de montrer qu'aucune solution ne peut faire mieux qu'une "
        "certaine grandeur — nombre d'états, d'arêtes, d'opérations — typiquement en "
        "Ω(·), et souvent pour en déduire une impossibilité.",
        ["Argumenter que tout AFD qui reconnaît L a au moins Ω(2^k) états",
         "Montrer que tout … a un nombre d'arêtes au moins égal à Ω(·)",
         "En déduire qu'il n'existe pas de circuit de profondeur constante"],
        [("La borne demandée est un majorant du coût",
          "complexite_algo.evaluer_complexite_algorithme"),
         ("L'impossibilité s'obtient par réduction depuis un problème connu",
          "complexite_pb.reduire_polynomialement_probleme")],
        [(EXO, "Q6"), (LCR, "Q8")],
        fichiers=(EXO, LCR),
    ),
    notion(
        "correction.determiner_specification_code_fourni",
        "Déterminer ce que calcule un fragment de code ou un circuit fourni",
        "La question fournit du code, un algorithme ou un circuit SANS dire ce qu'il "
        "fait, et demande d'en énoncer la spécification. La difficulté est la lecture, "
        "pas l'écriture ni la preuve.",
        ["Expliquer ce que fait la fonction f appliquée à …",
         "Que calcule le circuit ci-dessus ?",
         "Décrire le rôle de cette fonction auxiliaire"],
        [("La spécification est donnée et c'est la correction qui est à prouver",
          "correction.etablir_correction_algorithme"),
         ("Seul le type de l'expression est demandé, pas sa sémantique",
          "idiomes.inferer_type_fragment_code"),
         ("Il s'agit d'expliquer son PROPRE programme, pas d'en lire un fourni", None)],
        [(A, "Q10"), (INFO, "Q1")],
        langages=("ocaml", "pseudocode", "theorique"),
        fichiers=(A, INFO),
    ),
]

# ------------------------------------------------------------------------- #

for cle, valeur in {
    "ETAGE0_RACINE": ".", "ETAGE0_PROGRAMME": "spe777_annexe_1373646.md",
    "ETAGE0_ETALON": "referentiel/v1/sections",
}.items():
    os.environ.setdefault(cle, valeur)
config = Config.depuis_env()

existantes = ref.charger_notions(config.sortie / "sections")
ids, slugs = {n["id"] for n in existantes}, {n["slug"] for n in existantes}

print(f"référentiel : {len(existantes)} notions")
conflits = [n["id"] for n in NOTIONS if n["id"] in ids or n["slug"] in slugs]
if conflits:
    raise SystemExit(f"collision avec l'existant : {conflits}")

# Chaque `voir` doit résoudre AVANT écriture.
cibles = ids | {n["id"] for n in NOTIONS}
morts = [
    (n["id"], e["voir"]) for n in NOTIONS for e in n["exclusions"]
    if e["voir"] and e["voir"] not in cibles
]
if morts:
    raise SystemExit(f"renvois morts dans les notions à créer : {morts}")

par_section = {}
for n in NOTIONS:
    par_section.setdefault(n["section_id"], []).append(n)
for section, notions in sorted(par_section.items()):
    print(f"  {section:<18} +{len(notions)}")
    for n in notions:
        print(f"      {n['id']}")
        print(f"        {n['libelle']}")
        print(f"        attesté : {n['origine']['source'][7:]}")

if not APPLIQUER:
    print("\n(simulation — relancer avec --appliquer)")
    raise SystemExit

produit = ref.Referentiel(notions=NOTIONS)
ajoutees = ref.injecter(produit, config, "corpus (confrontation des 6 fichiers)", [], [])
for fichier, compte in sorted(ajoutees.items()):
    print(f"  → {compte} notion(s) dans {fichier}")
