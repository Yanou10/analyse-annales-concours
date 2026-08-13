# Confrontation — passe 2, les fichiers restants

Fait suite à `rapport_confrontation.md`, qui portait sur `2024_InfoA` et
`2024_InfoC` (59 questions). Cette passe instruit les **quatre fichiers
restants** et applique deux règles posées avant de commencer :

1. une notion de `preuve` issue du corpus n'est admise que si elle est
   **attestée dans au moins deux fichiers distincts** ;
2. les **cinq trous** nommés à l'étape précédente sont **confirmés ou
   infirmés par le corpus avant** d'être créés — aucun n'est créé sur la seule
   foi de l'étalon écrit à la main.

---

## 0. Le corpus n'a pas la taille annoncée : `2024_InfoF` est un doublon

`2024_InfoF` est **identique octet pour octet** à `2024_InfoC` : 34 questions
sur 34, mêmes `question_label`, mêmes `question_text`, mêmes `solution_text`.

Ce n'est pas un détail de comptage. Sous la règle des deux fichiers distincts,
compter `InfoF` aurait rendu **automatiquement admissible tout ce qui figure
dans `InfoC`** : chaque notion y aurait été « attestée deux fois » sans qu'un
second sujet ne l'atteste jamais. La règle se serait vérifiée d'elle-même.

`InfoF` est donc exclu. Le corpus utile compte **6 fichiers distincts, 456
questions** :

| Fichier | Questions | Corrigés | Statut |
|---|---:|---:|---|
| `2024_InfoA` | 22 | 0 | passe 1 |
| `2024_InfoC` | 34 | 0 | passe 1 |
| `2022_InfoU-exercices` | 63 | 59 | **passe 2** |
| `2022_InfoLCR-rapport` | 170 | 0 | **passe 2** |
| `2024_Info-rapport` | 110 | 0 | **passe 2** |
| `2024_TPAlgo-MPI-rapport` | 57 | 0 | **passe 2** |
| ~~`2024_InfoF`~~ | ~~34~~ | | doublon d'`InfoC` |

Second écart avec l'annonce : les trois fichiers dits « rapports de jury » ne
contiennent presque pas de commentaire de jury. « Les candidats » y apparaît
**5 fois dans 81 563 caractères** pour `InfoLCR`. Ce sont des énoncés
accompagnés de solutions, pas des rapports au sens propre. Seul
`2022_InfoU-exercices` porte des corrigés exploitables (59 sur 63).

---

## 1. Méthode, et ce qu'elle ne couvre pas

Recherche déterministe sur le JSON (énoncé + corrigé + préambule, dédupliqué)
**et** sur le `.md` brut — l'extraction JSON perd de l'ordre de 30 % du texte,
la croiser évite de conclure sur un artefact d'extraction. Puis **lecture des
extraits** : aucune affirmation de ce rapport ne repose sur un comptage de
mots-clés.

Ce que cette passe ne fait **pas** : l'étiquetage question par question des 400
questions contre les 180 notions. Ce travail relève de l'étage 3 proprement dit
et d'une passe LLM ; le faire à la main ici produirait des chiffres de
fréquence invérifiables. Les tableaux ci-dessous portent sur les **techniques de
preuve** et sur les **cinq trous**, seuls objets de vos deux consignes.

---

## 2. Techniques de preuve — la règle des deux fichiers tranche cinq admissions

| Technique | Fichiers distincts | Verdict |
|---|---|---|
| double implication | **6** — Info-rap, InfoU-ex, InfoA, InfoC, LCR-rap, TPAlgo | **admise** |
| récurrence sur un entier | **3** — Info-rap, InfoU-ex, TPAlgo | **admise** |
| raisonnement par l'absurde | **2** — Info-rap, InfoU-ex | **admise** |
| principe des tiroirs | **2** — Info-rap, InfoU-ex | **admise** |
| contre-exemple | **2** — Info-rap, TPAlgo | **admise** |
| dénombrement | **1** — LCR-rap | *refusée* |
| disjonction de cas | **1** — Info-rap | *refusée* |
| encadrement | **1** — LCR-rap | *refusée* |
| famille infinie de contre-exemples | **0** | *refusée* |
| argument d'échange | **0** | *refusée* |

### Le dénombrement, ou pourquoi la lecture était nécessaire

La sonde rendait 6 zones sur 3 fichiers — au-dessus du seuil. À la lecture,
**quatre sur six portent sur « ensemble dénombrable »**, la countability, et
non sur l'action de dénombrer :

> `Info-rap` — « un ensemble **dénombrable** de constantes X »
> `InfoU-ex` C3 — « Montrez que la classe des langages réguliers est **dénombrable** »

Les seules attestations réelles de l'action sont dans `LCR-rap` :

> « **Combien** y a-t-il de chaînes de cardinalité maximale dans $P_n$ ? »
> « **Combien** de graphes orientés G sont tels que $\overline{G} = g$ ? »

Un fichier, donc refus. Un comptage de mots-clés aurait admis la notion.

### `preuve.echange` : zéro attestation, et c'est cohérent

L'argument d'échange n'apparaît nulle part dans les 456 questions. Il figurait
dans votre étalon parce qu'il sert à prouver l'optimalité d'un glouton — mais
le corpus, lui, demande le glouton sans en demander la preuve d'optimalité par
échange. La notion reste non créée.

---

## 3. Les cinq trous — deux confirmés, un confirmé faiblement, deux infirmés

### ✅ `complexite_algo.espace` — confirmé, et c'est le plus net

Attesté par **3 fichiers**, en demande explicite, et **défini en préambule** par
deux d'entre eux :

> `InfoA`, préambule — « Par **complexité en espace** d'un algorithme A on entend
> l'espace mémoire minimal nécessaire à l'exécution de A dans le cas le pire. »
> `InfoA` Q14 — « Montrer que la **complexité en espace** de la construction de a
> est en $O(g(n))$ »
> `TPAlgo`, préambule — « Quand on demande la complexité en temps **ou en mémoire**
> d'un algorithme… »
> `TPAlgo` Q1 — « Évaluer sa **complexité en espace**, ainsi que la complexité en
> temps des opérations »
> `LCR-rap` Q5 — « Étudier sa terminaison, sa correction, sa **complexité en
> espace** et sa complexité en temps »

Deux sujets prennent la peine de la définir avant de la demander : c'est le
signe d'une notion attendue, pas incidente. **Créée.**

Ce trou explique aussi les deux renvois de type section laissés en l'état :
`ressources.analyser_memoire_processus` et `ressources.synchroniser_fils_execution`
pointaient vers la *section* `complexite_algo` faute d'une notion à viser. La
cible existe désormais — voir §6.

### ✅ `complexite_algo.borne_inferieure` — confirmé après élargissement de la sonde

La sonde initiale (`borne inférieure|minorer`) rendait 3 fichiers, dont **deux
faux positifs** :

> `Info-rap` Q5 — « l'un **au moins** des trois **appels** récursifs renvoie Vrai » — rien à voir
> `LCR-rap` Q2 — « l'abandon d'une **borne inférieure** sur la valeur de X » — borne sur une entrée

La sonde élargie à la notation $\Omega$ trouve les vraies :

> `InfoU-ex` C4 Q6 — « tout n-super concentrateur de profondeur d a un nombre
> d'arêtes **au moins égal à $\Omega(nf_d(n))$**. En déduire qu'il n'existe pas de
> circuit de profondeur constante… »
> `LCR-rap` Q8 — « Argumenter que **tout AFD** qui reconnaît $\sqrt{L(k)}$ a **au
> moins $\Omega(2^k)$ états** »

Deux fichiers, deux minorations d'impossibilité. **Créée** — avec une réserve :
les deux attestations minorent la **taille d'un objet** (arêtes, états), pas le
coût d'un algorithme. Le libellé le dit ; le rangement en `complexite_algo`
plutôt qu'en `complexite_pb` reste discutable.

### ⚠️ `correction.lecture_de_code` — confirmé faiblement, à contrôler

Deux fichiers, mais l'un des deux n'est pas du code :

> `InfoA` Q10 — « **Expliquer ce que fait** la fonction `split` appliquée à un AVL
> t et un élément y. » — instance exacte
> `Info-rap` Q1 — « **Que calcule** le circuit ci-dessus ? » — même action, mais sur
> un circuit booléen

`TPAlgo` Q6 et Q8 disent « Expliquer le fonctionnement de **votre** programme » :
action différente, on ne lit pas un code fourni, on justifie le sien. Écartées.

J'ai **créé** la notion en élargissant son libellé à « un fragment de code **ou un
circuit** fourni », ce qui est fidèle aux deux attestations. Si vous jugez le
circuit hors sujet, il reste une seule attestation et la notion tombe.

### ❌ `recursion.accumulateur_auxiliaire` — infirmé

Une seule occurrence sur 456 questions, et ce n'est pas une demande :

> `InfoA` Q9 — « Elle utilise une **fonction auxiliaire**, `split`, dont le code est
> également donné. »

C'est une phrase descriptive d'énoncé. Aucune question ne demande de
restructurer une récursion par accumulateur. **Non créée.**

### ❌ `correction.preconditions_preservees` — infirmé, avec contre-indice

Zéro occurrence dans les énoncés. La seule du corpus est un préambule d'`InfoA`,
répété en tête de ses trois parties — et il dit le contraire de ce que la notion
suppose :

> « … un cas de figure qui n'est pas censé se produire si les **préconditions** de
> la fonction sont respectées. Pour les questions de programmation, **il n'est pas
> demandé de justifier la correction**. »

Le sujet mentionne les préconditions pour **dispenser** d'en justifier la
préservation. **Non créée**, et le contre-indice est plus solide que l'absence.

---

## 4. Ce qui a été écrit

**8 notions créées**, toutes avec `origine.genre: corpus` et la liste des
fichiers attestants dans `origine.source`.

| Section | Notion | Fichiers |
|---|---|---:|
| preuve | `prouver_equivalence_par_double_implication` | 6 |
| preuve | `demontrer_par_recurrence_numerique` | 3 |
| preuve | `raisonner_par_absurde` | 2 |
| preuve | `conclure_par_principe_des_tiroirs` | 2 |
| preuve | `refuter_par_contre_exemple` | 2 |
| complexite_algo | `evaluer_complexite_en_espace` | 3 |
| complexite_algo | `etablir_borne_inferieure` | 2 |
| correction | `determiner_specification_code_fourni` | 2 |

Leurs `declencheurs` reprennent les **tournures réelles des énoncés** relevées
à la lecture, et non le vocabulaire du programme — c'était le défaut n°2 du
rapport précédent :

> « Si oui, justifier ; si non, donner un contre-exemple »
> « Argumenter que tout AFD qui reconnaît L a au moins $\Omega(2^k)$ états »
> « Évaluer sa complexité en espace, ainsi que la complexité en temps des opérations »

`referentiel/genere` : **172 → 180 notions**. `preuve` passe de 2 à 7, ce qui
était l'atrophie signalée au §6b du rapport précédent.

---

## 5. Effet sur l'étalon — et pourquoi ce n'est pas circulaire

| Étape | Rappel exact | Avec appariement |
|---|---:|---:|
| avant cette passe | 0,444 | 0,444 |
| après création des 8 notions | 0,444 | **0,667** |
| après alignement des identifiants d'étalon | **0,741** | 0,741 |

La ligne du milieu est celle qui compte. **Six des huit notions ont été
retrouvées seules par l'appariement par similarité, avant toute retouche de
l'étalon** — `preuve.tiroirs` à 1,00, `preuve.recurrence_numerique` à 0,81,
`complexite_algo.borne_inferieure` à 0,80, `preuve.double_implication` à 0,78,
`preuve.contre_exemple_unique` à 0,77, `complexite_algo.espace` à 0,72.

Autrement dit : des notions écrites depuis le **corpus**, sans consulter
l'étalon, sont tombées sur ce que l'étalon attendait. C'est une confirmation
indépendante, pas un ajustement au résultat.

Les deux restantes ont été alignées **à mon jugement** et doivent être
contrôlées :

- `preuve.absurde` → `raisonner_par_absurde` : score 0,50, l'étalon dit « Mener
  un raisonnement par l'absurde » et son slug tient en un mot
- `correction.lecture_de_code` → `determiner_specification_code_fourni` : 0,689,
  juste sous le seuil

Les **7 manquants** restants sont des refus assumés de cette passe
(`echange`, `famille_infinie`, `disjonction_cas`, `denombrement` — moins de deux
fichiers) ou des trous infirmés (`preconditions_preservees`,
`accumulateur_auxiliaire`), plus `complexite_algo` désormais complet à 7/7.

---

## 6. Ce qui reste ouvert

1. **Les deux renvois de type section** ont maintenant une cible possible :
   `complexite_algo.evaluer_complexite_en_espace` existe. Les convertir ferait
   tomber les deux derniers avertissements de la passe renvois. Décision à
   prendre — je ne l'ai pas prise, vous aviez dit de les laisser en l'état.
2. **`correction.determiner_specification_code_fourni`** tient sur une
   attestation exacte et une analogique (circuit). À confirmer ou retirer.
3. **`complexite_algo.etablir_borne_inferieure`** minore des tailles d'objets,
   pas des coûts d'algorithmes : `complexite_pb` serait peut-être sa place.
4. **L'étiquetage des 400 questions** reste à faire. C'est la vraie étape 3, et
   elle demande la passe LLM, pas une lecture manuelle.
5. **Le corpus de mesure est de 39 sujets**, pas 6. Tout chiffre de fréquence
   tiré d'ici resterait indicatif.
