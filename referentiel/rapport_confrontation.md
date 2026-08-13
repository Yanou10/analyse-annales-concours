# Rapport de confrontation — référentiel v1 face au corpus

Passe sans appel LLM. Aucun libellé ni structure modifié : purge des annexes
exécutée, exemples écrits, corrections **proposées** et en attente de validation.

---

## 0. Le résultat qui prime sur tous les autres : deux sections manquent

Avant toute analyse de découpage — **le référentiel est incomplet**, et c'est un
défaut de mon code, pas de sa conception.

| Section du programme | Unités jamais décidées | Contenu perdu |
|---|---:|---|
| **§3.4** Structures de données relationnelles | 7 | représentation d'un graphe par matrice / listes d'adjacence, pondération, graphe biparti |
| **§4.3** Décomposition d'un problème en sous-problèmes | 6 | **algorithme glouton, diviser pour régner, dichotomie, programmation dynamique** |

Ces sections n'apparaissent ni dans `sections/*.yaml`, ni dans `refus.json` :
elles ont échoué pendant la passe et `cmd_construire` les a sautées avec un
`continue`, en ne laissant qu'une ligne sur `stderr`. Le manifeste a ensuite été
écrit comme si la passe était complète.

C'est exactement le mode de défaillance que le projet cherche à éviter : une
sortie qui a l'air entière et ne l'est pas.

**Correction déjà appliquée au code** (`etage0/cli.py`) : toute section perdue
est désormais enregistrée dans `manifest.yaml → genere_par.sections_perdues`,
remontée en anomalie **bloquante**, annoncée en fin de passe, et fait sortir la
commande en code 2 — indépendamment de `--strict`.

**Action requise avant toute autre correction** : relancer `etage0 construire`.
Les quatre notions de §4.3 sont parmi les plus lourdes du corpus — `2024_InfoC`
leur consacre à elle seule les parties II et III.

---

## 1. Purge des annexes

Votre consigne nommait 4 sources ; le champ `origine.genre == "annexe"` en
marquait **43**. J'ai retenu le genre, plus fidèle à l'intention (« proviennent
des annexes A et B ») que la liste de sources, incomplète.

Le tri a dû se scinder en **deux** opérations, parce que les entrées d'annexe
n'étaient pas toutes de même nature :

| Section | Déplacées vers `langages.json` | Supprimées (doublons) |
|---|---:|---:|
| idiomes | 22 | 3 |
| sd_sequentielles | 3 | 1 |
| ressources | 2 | 7 |
| recursion | 2 | 0 |
| correction | 1 | 0 |
| complexite_algo | 1 | 0 |
| **Total** | **31** | **11** |

**206 → 164 notions.**

### Pourquoi 11 suppressions et non 42 déplacements

Les entrées d'annexe de `ressources` ne sont pas des éléments de langage : ce
sont des **doublons de génération**. « Créer des fils d'exécution et attendre
leur terminaison » figure deux fois à l'identique (similarité 1,00), une fois
depuis §5.3 du corps, une fois depuis l'annexe A.2. Les verser dans
`langages.json` les aurait mal rangées et aurait laissé le doublon en place.

Doublons supprimés — la notion du **corps** est conservée :

- `ressources` : fichier texte, fils d'exécution, mutex, sémaphore, `malloc`/`free` (×2), pile/tas
- `sd_sequentielles` : dictionnaire par table de hachage
- `idiomes` : type inféré, linéarisation de tableau, filtrage par motif

### Les 4 exceptions conservées dans `idiomes`

Trois d'entre elles ne relevaient pas des annexes : elles viennent du **corps
§3.1** (`origine.genre == "table"`), la consigne ne les visait donc pas.

| Notion | Justification |
|---|---|
| `inferer_type_fragment_code` | Corps §3.1 : « un étudiant est capable d'inférer un type à la lecture d'un fragment de code ». Raisonnement sur les types, pas syntaxe d'un langage. |
| `lineariser_tableau_multidimensionnel` | Corps §3.1. L'arithmétique d'indices `i*m+j` est transférable, et `2024_TPAlgo` partie 3 la pose directement. |
| `distinguer_structure_mutable_immuable` | Corps §3.1. Décision de conception : `2024_InfoA` construit un AVL **persistant**, et Q14 porte exactement sur le partage de sous-structures entre versions. |
| `ecrire_filtrage_par_motifs` | Seule exception réellement issue d'une annexe. Un sujet MPI 2024 entier lui est consacré et le traite comme **objet d'étude** (matrices de filtrage, relation de compatibilité `m ≤σ v`, élimination du joker), pas comme idiome OCaml. |

Refusées comme exceptions, alors que je les avais défendues dans l'analyse
initiale : `simuler_retours_multiples_par_pointeurs` et
`transtyper_void_pointeur_c`. Elles n'existent que parce que C manque de
n-uplets et de généricité — elles ne passent donc pas « indépendamment de tout
langage ».

---

## 2. Couverture de la confrontation — à lire avant les chiffres

Le corpus contient **556 occurrences brutes** de « Question N » hors conteneurs,
soit après retrait d'`InfoF` (doublon d'`InfoC`) et des renvois internes aux
corrigés, de l'ordre de **400 à 450 questions réelles** — nettement au-dessus
de votre estimation de 260.

Je n'ai confronté avec rigueur que ce que j'ai lu intégralement et peux citer :

| Fichier | Questions | Confrontées |
|---|---:|---:|
| `2024_InfoA` | 22 | 22 |
| `2024_InfoC` | 37 | 37 |
| autres (3 rapports d'oral, 1 TP) | ~350 | 0 |

**Les chiffres ci-dessous portent donc sur 59 questions, pas sur le corpus.**
Ils suffisent à faire apparaître les défauts de découpage — c'était l'objet —
mais pas à conclure sur les fréquences.

---

## 3. Tableau par section

| Section | Notions | Questions capturées (/59) | Notions sans exemple |
|---|---:|---:|---:|
| preuve | 2 | 2 | 1 |
| correction | 10 | 9 | 7 |
| complexite_algo | 7 | 9 | 5 |
| recursion | 3 | 6 | 2 |
| modelisation | 3 | 1 | 2 |
| sd_sequentielles | 6 | 0 | 6 |
| sd_hierarchiques | 11 | 5 | 9 |
| graphes_repr | 5 | 0 | 5 |
| graphes_algo | 12 | 0 | 12 |
| strategies | 15 | 5 | 13 |
| textes | 6 | 0 | 6 |
| logique | 19 | 0 | 19 |
| langages | 22 | 0 | 22 |
| complexite_pb | 7 | 0 | 7 |
| ressources | 21 | 1 | 20 |
| bdd | 11 | 0 | 11 |
| idiomes | 4 | 1 | 3 |
| **Total** | **164** | **26** | **150** |

Conformément à votre consigne, aucune notion n'est classée actif / fragile /
candidat : deux sujets ne permettent pas de conclure à l'absence.

### Nombre moyen de notions par question : **1,62**

Nettement sous les 3 attendus. Trois causes, par ordre d'importance :

1. **Les trous structurels** (§4.3, §4.5 partiellement, techniques de preuve).
   `2024_InfoC` II.2 et II.3 — glouton puis programmation dynamique — ne
   capturent **rien**, alors qu'elles devraient porter 3 étiquettes chacune.
2. **Les définitions sont écrites depuis le programme, pas depuis les questions.**
   Les `declencheurs` sont plausibles mais reprennent le vocabulaire du
   programme, pas les tournures des énoncés.
3. Une part d'auto-censure de ma part : à définition ambiguë, je n'ai pas
   étiqueté. C'est le point 5 (indécidabilité).

**33 des 59 questions ne capturent aucune notion.** C'est le chiffre à corriger
en priorité, pas la moyenne.

---

## 4. Redondances

Recouvrement mesuré sur les exemples positifs.

| Paire | Recouvrement | Correction proposée |
|---|---|---|
| `complexite_algo.analyser_complexite_pire_cas` ↔ `complexite_algo.evaluer_complexite_algorithme` | ~95 % (similarité de libellé 0,82) | **Fusion.** La seconde est un chapeau issu d'un paragraphe de prose ; elle n'a aucun déclencheur que la première n'ait pas. |
| `correction.etablir_correction_algorithme` ↔ `correction.prouver_correction_partielle_par_invariant` | ~70 % | **Redéfinir** la première en « établir la correction **sans invariant de boucle explicite** » (preuve par cas, par construction), ou la supprimer comme chapeau. |
| `ressources.gerer_allocation_dynamique_memoire` ↔ `ressources.gerer_allocation_dynamique_c` | ~90 % (0,81) | **Fusion.** L'une vient de §3.1, l'autre de §5.1 ; c'est la même action. |
| `sd_hierarchiques.implementer_unir_trouver_naif` ↔ `..._par_arbres` | à mesurer | **Conserver.** 0,78 de similarité mais deux implémentations qu'on révise séparément — le programme les oppose explicitement. |
| `graphes_repr.parcourir_graphe_largeur` ↔ `..._profondeur` | à mesurer | **Conserver.** 0,86 de similarité, mais les cas d'usage diffèrent (plus court chemin non pondéré vs tri topologique). |

---

## 5. Indécidabilités

Questions où l'hésitation vient de la **rédaction**, pas d'un multi-étiquetage
légitime.

| Cas | Notions en concurrence | Clarification proposée |
|---|---|---|
| `2024_InfoA` Q4 — « Montrer que h(t) ≤ 2log(n(t)+1), on pourra considérer N_h » | `preuve.prouver_par_induction_structurelle` vs une notion de récurrence numérique **inexistante** | Ajouter `preuve.recurrence_numerique`, et préciser dans la définition de l'induction structurelle : « le raisonnement porte sur les constructeurs, pas sur un entier ». |
| Toute question portant sur une formule logique | `preuve.prouver_par_induction_structurelle` vs `logique.parcourir_formule_par_induction_structurelle` | Les deux définitions se recouvrent totalement. Garder la générique et faire de la seconde un exemple positif, ou restreindre la seconde à « écrire une fonction récursive sur le type formule ». |
| `2024_InfoA` Q6 — « join termine et ne peut pas planter » | `prouver_terminaison_par_variant` vs `etablir_correction_algorithme` | La partie « ne peut pas planter » n'est ni l'une ni l'autre : c'est une preuve d'inatteignabilité de code. Notion à créer. |
| `2024_InfoA` Q20 — « être précis quant aux structures de données **et algorithmes** utilisés » | `modelisation.choisir_structure_donnees_selon_operations` vs `graphes_repr.choisir_representation_graphe_selon_complexite` | Restreindre la seconde aux graphes de façon explicite ; la première ne dit pas qu'elle les exclut. |

---

## 6. Trous

### 6a. Trous par section perdue — à corriger en relançant la passe

`glouton`, `diviser pour régner`, `dichotomie`, `programmation dynamique`,
`représentation d'un graphe`. Questions non couvertes en conséquence :
`InfoC` II.2, II.3 ; `InfoA` Q21 (recherche dichotomique), Q20 en partie.

### 6b. Trous de conception — la section `preuve` est atrophiée

Elle compte **2 notions**. Toutes les techniques transverses que l'analyse
initiale avait identifiées manquent, et ce sont elles qui portent le corpus ENS :

| Notion manquante | Attestation dans les 59 questions |
|---|---|
| Prouver une équivalence par double implication | `InfoC` I.3, IV.2, IV.5, V.2, V.3, VI.10 — **6 questions** |
| Justifier une solution optimale par un argument d'échange | `InfoC` II.1 |
| Construire une famille infinie d'instances pour réfuter une borne | `InfoC` III.2, III.4, III.7, VI.3 — **4 questions** |
| Mener une récurrence sur un paramètre entier | `InfoA` Q4 ; `InfoC` III.2 |
| Dénombrer ou énumérer exhaustivement | `InfoA` Q1, Q3 ; `InfoC` I.1, I.2 |
| Établir une égalité par encadrement des deux côtés | `InfoA` Q4 |
| Structurer une preuve par disjonction de cas | `InfoA` Q7 ; `InfoC` IV.4 |

Cause : le générateur travaille section par section **du programme**, et ces
techniques n'y figurent pas. Le profil les prévoyait (`sections_cibles.preuve`
porte la justification), mais rien ne pouvait les produire. Il faut une passe
dédiée, alimentée par le corpus et non par le programme.

### 6c. Trous de définition trop étroite

| Question non couverte | Diagnostic |
|---|---|
| `InfoA` Q14 — complexité **en espace** | `complexite_algo` n'a aucune notion d'espace. Le programme la nomme pourtant (§1.1, §4.3). À créer. |
| `InfoA` Q18 — « Σ Ti peut être en Θ(N²) » | Aucune notion de **minoration / pire cas atteignable**. À créer. |
| `InfoA` Q7, Q8, Q11 — rotations, rééquilibrage AVL | `sd_hierarchiques` ne connaît que l'`arbre bicolore`. Élargir en « maintenir l'équilibre d'un arbre de recherche par rotations ». |
| `InfoA` Q10 — « Expliquer ce que fait la fonction » | Rattaché faute de mieux à `specifier_entrees_sorties_algorithme`, qui vise l'écriture d'une spécification, pas la lecture de code. Notion à créer. |

### 6d. Hors référentiel légitime

`InfoC` parties IV à VI (complexité paramétrée, FPT, noyau, optimisation
linéaire) et `InfoA` partie III (géométrie algorithmique) sortent du programme.

**Contrôle demandé, et il échoue** : aucune n'a d'entrée correspondante dans
`exclusions.json` — le fichier n'existe pas encore, `etage0 exclusions` n'a pas
été lancé. Et il ne les couvrira pas : ces objets ne sont pas *déclarés* hors
programme, ils en sont *absents*. C'est la raison `absent_du_programme`, qui ne
peut venir que du corpus.

---

## 7. Saturations

Sur 26 questions capturées seulement — à relire après correction des trous.

| Notion | Occurrences | Extrapolation | Éclatement proposé |
|---|---:|---|---|
| `correction.etablir_correction_algorithme` | 9 / 26 | ~35 % des questions | **Chapeau à supprimer.** Il capte tout ce que les notions précises ne captent pas. Répartir vers invariant, variant, préconditions préservées, disjonction de cas. |
| `complexite_algo.analyser_complexite_pire_cas` | 9 / 26 | ~35 % | Éclater **par technique de justification** (récurrence / comptage d'opérations / amortissement / taille de l'arbre d'appels), jamais par objet. |
| `recursion.ecrire_fonction_recursive` | 6 / 26 | ~23 % | Éclater : écriture directe vs restructuration par accumulateur ou fonction auxiliaire sous contrainte de coût. |

Les deux premières sont les futurs aimants. Elles sont d'une nature différente
de l'aimant de la version précédente : celui-ci était un item de **vocabulaire**,
ceux-ci sont des **chapeaux d'action** trop larges. Le critère d'admission les a
laissés passer parce qu'ils commencent bien par un verbe.

**Correction proposée au critère d'admission** : ajouter une règle 8 — « une
action dont la définition opératoire n'exclut aucune autre notion de sa section
est un chapeau : la refuser ».

---

## 8. Questions du corpus non couvertes

`2024_InfoA` : Q1, Q3 (dénombrement) · Q11 (dérouler une insertion) · Q14
partiellement (espace) · Q18 (minoration) · Q19, Q21 (dichotomie, géométrie).

`2024_InfoC` : I.1, I.2 (dénombrement, valeurs sur familles) · I.3, I.4
(double implication) · II.1 (échange) · II.2 (glouton) · II.3 (programmation
dynamique) · III.2, III.3, III.4 (famille infinie) · IV.2, IV.4, IV.5 · V.1 à
V.6 · VI.1 à VI.4, VI.6 à VI.10.

Soit **33 questions sur 59**.

---

## 9. Note pour l'étage d'évaluation

Votre remarque est juste et je la retiens telle quelle : avec du multi-étiquetage,
`part = occurrences_notion / occurrences_totales` se resserre mécaniquement quand
le nombre moyen d'étiquettes augmente, ce qui rend le seuil de 4 % non comparable
d'une version à l'autre.

L'étage 4 calculera donc :

```
part(notion) = nombre de QUESTIONS portant la notion / nombre total de questions
```

Les deux mesures seront affichées côte à côte — `part_questions` porte le seuil
de 4 %, `part_occurrences` sert à lire la charge relative — accompagnées du
nombre moyen d'étiquettes par question, sans lequel ni l'une ni l'autre ne
s'interprète.

---

## 10. Ce que je proposais (superseded — voir §11)

Rien n'est appliqué : ni fusion, ni éclatement, ni redéfinition.

1. **Relancer `etage0 construire`** — sans §3.4 et §4.3 le reste de l'analyse
   porte sur un référentiel amputé.
2. Lancer `etage0 exclusions`, absent à ce jour.
3. Supprimer les 2 chapeaux (`etablir_correction_algorithme`,
   `evaluer_complexite_algorithme`) et fusionner les 2 paires d'allocation.
4. Créer la section `preuve` par une passe **corpus**, pas programme (≈ 7 notions).
5. Créer les 4 notions de trou de définition (espace, minoration, rotations,
   lecture de code).
6. Ajouter la règle 8 au critère d'admission du profil, puis regénérer.
7. Reprendre la confrontation sur les 5 fichiers restants.


---
---

# Mise à jour — exécution de l'ordre validé

## 11. État des 4 étapes

| Étape | État | Détail |
|---|---|---|
| 1. Relancer `construire` | **bloquée** | aucun identifiant Anthropic dans cet environnement |
| 2. `exclusions` + 3 statuts | **statuts consignés, passe bloquée** | même cause |
| 3. Confrontation des 5 fichiers restants | **partielle** | 1 fichier inventorié sur 4 distincts |
| 4. Propositions révisées | **reportée** | dépend de 1 et 3 — délibérément non faite |
| 4bis. Règle 8 rétroactive | **faite** | indépendante du corpus |

### 11.1 Étapes 1 et 2 — bloquées sur les accès

`ANTHROPIC_API_KEY` absente, CLI `ant` non installée. Rien d'autre ne manque.

Le journal contient 42 entrées et **ni `notions/3.4` ni `notions/4.3`** — la
reprise ne rejouera donc que les deux sections perdues :

```bash
export ANTHROPIC_API_KEY=...          # ou : ant auth login
etage0 construire --fournisseur anthropic --etalon referentiel/v1/sections
etage0 exclusions
```

**Coût : 2 appels + 1.** Les 40 autres sections sont reprises depuis le journal.

Les trois statuts sont consignés dans `profils/informatique-mpi.yaml` sous
`mentions_restrictives.statuts_question`, avec la précision qui compte :
`absent_du_programme` ne peut pas être établi par `etage0 exclusions`, qui ne lit
que le programme. Il s'établit pendant la confrontation. `2024_InfoC` IV-VI et
`2024_InfoA` III y sont nommément rattachés.

### 11.2 Étape 3 — partielle, et je dis pourquoi

**Fait :** `2022_InfoU-exercices` inventorié — **87 questions** réparties sur 13
exercices (B1-B5, C1-C4, L1-L4). Contenu dominé par des objets absents du
programme : monoïde syntaxique, circuits booléens universels, ordres
d'intervalles, treillis de mariages stables, chip firing. Les notions du
référentiel qui y sont réellement attestées relèvent surtout des techniques de
preuve (« Montrer que … si et seulement si », L4.2 terminaison de Gale-Shapley,
L4.3 correction) et des automates (C1-C3).

**Non fait :** `2024_Info-rapport` (128), `2022_InfoLCR-rapport` (179),
`2024_TPAlgo` (37).

**Tentative écartée.** J'ai essayé un balayage lexical par notion pour couvrir
les 344 questions restantes à moindre coût. Il donne 139 notions sur 164
« attestées dans ≥ 2 fichiers », dont « Déterminer et justifier la clé primaire
d'une table » avec 6 attestations — alors que `SELECT` et `SQL` n'apparaissent
**nulle part** dans le corpus. La méthode apparie des mots isolés (« déterminer »,
« table »), pas des notions. Artefact supprimé, résultat non reporté.

Une confrontation honnête sur ces 344 questions demande de les lire. Je ne l'ai
pas fait ici, et je préfère le dire plutôt que livrer un tableau chiffré qui
aurait l'apparence d'une mesure. **Les chiffres de §3 restent ceux de 59
questions** et ne doivent pas être cités comme portant sur le corpus.

### 11.3 Étape 4 — délibérément non faite

Vos points 3 à 6 restent en attente, comme vous l'avez demandé : ils supposent
§3.4 et §4.3 présentes et le corpus vu. La règle des **deux fichiers distincts**
pour la section `preuve` est retenue ; sur les seules données actuelles, deux
candidates la franchiraient déjà (double implication : `InfoC` ×6 + `InfoU` B5.1,
C1.3, C3.1 ; terminaison/correction d'un algorithme fourni : `InfoA` Q6 + `InfoU`
L4.2-L4.3), mais je ne les propose pas avant d'avoir vu les rapports de jury.

---

## 12. Règle 8 appliquée rétroactivement

Opérationnalisation retenue : *une notion dont aucun critère d'exclusion ne
renvoie vers une autre notion de sa propre section ne se distingue de rien*.

**22 notions sur 164** échouent au test.

| Section | Échecs | Notions |
|---|---:|---|
| modelisation | **3/3** | choisir une structure de données ; modéliser un jeu par graphe biparti ; modéliser par SAT |
| idiomes | **3/4** | inférer un type ; distinguer mutable/immuable ; écrire un filtrage par motifs |
| complexite_algo | 4/7 | résoudre une récurrence ; comparer les coûts d'implémentation ; évaluer la complexité *(chapeau déjà signalé)* ; explosion de taille d'une forme normale |
| ressources | 4/21 | chaîne de compilation ; coût des appels récursifs ; allocation par pointeurs ; occupation mémoire d'un processus |
| recursion | 2/3 | écrire une fonction récursive ; dérouler un arbre d'activations |
| sd_sequentielles | 2/6 | spécifier une structure abstraite ; sérialiser |
| graphes_algo | 2/12 | couplage par chemins augmentants ; A* |
| correction | 1/10 | admissibilité et monotonie d'une heuristique |
| sd_hierarchiques | 1/11 | arbre k-dimensionnel |

Liste complète : `referentiel/regle8_chapeaux.json`.

### Ce que l'audit révèle, et qui n'était pas prévu

**La règle 8 mécanique ne capture pas les deux chapeaux que j'avais identifiés.**
`correction.etablir_correction_algorithme` (9 questions sur 26) et
`complexite_algo.analyser_complexite_pire_cas` (9/26) possèdent bien des
exclusions intra-section, et passent donc le test — tout en absorbant un tiers
des questions.

La règle 8 est donc **nécessaire et non suffisante**. Elle repère les notions mal
rédigées ; elle ne repère pas les notions bien rédigées mais trop larges. Il faut
un second volet, empirique, que seul le corpus fournit :

> **Règle 8a (rédaction, vérifiable sans corpus).** Une notion dont aucun critère
> d'exclusion ne renvoie vers une autre notion de sa section est un chapeau.
>
> **Règle 8b (charge, vérifiable seulement sur le corpus).** Une notion dont la
> part des questions dépasse le seuil alors que ses exclusions sont correctement
> rédigées n'est pas mal écrite : elle est trop large. Elle s'éclate par
> technique, pas par objet.

Deux sections méritent d'être signalées à part : `modelisation` (3/3) et
`idiomes` (3/4) échouent **intégralement**. Dans les deux cas la cause est
identique et bénigne — ce sont des sections à 3 ou 4 notions dont les membres ne
se ressemblent pas, donc rien à exclure en interne. La règle 8 y produit un faux
positif structurel. Correction proposée : ne l'appliquer qu'aux sections de plus
de 5 notions, et traiter les petites sections à la main.

---

## 13. Sur la moyenne d'étiquettes

Retenu sans réserve : 1,62 est un symptôme, pas une cible. Aucun réglage ne
visera ce nombre. La cible reste **les 33 questions sur 59 qui ne capturent
rien**, et l'étage 4 affichera la moyenne comme diagnostic, jamais comme
objectif.
