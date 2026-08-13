# Où sont partis les jetons — 10 et 11 août 2026

Rapport de lecture des journaux : §0 à §5 ont été établis sans modifier une
ligne de code, sans lancer de passe et sans aucun appel API — y compris
`count_tokens`, qui aurait affiné les estimations mais reste un appel.

Le **§6**, ajouté ensuite sur demande, documente les corrections appliquées au
comptage et à l'ordre des appels, ainsi que la vérification du tarif à la
source. Elles n'ont elles non plus coûté aucun appel : la validation s'est
faite en rejouant la passe complète depuis le journal.

---

## 0. Ce que les journaux permettent, et ce qu'ils ne permettent pas

**`.etage0/journal.jsonl` n'enregistre pas les jetons.** Chaque entrée porte
`cle`, `etiquette`, `charge` et un `meta` réduit à `{"modele": …}` — plus
`unites` et `notes` pour l'étage 0. Le comptage n'existe que sur `stderr`,
perdu à la fermeture du terminal.

Ce que le journal donne donc exactement : **352 entrées = 352 appels réussis**,
avec leur modèle et leur objet. Ce qu'il ne donne pas : un seul jeton.

Les volumes ci-dessous viennent des sorties d'exécution relevées pendant les
sessions. Trois exécutions n'ont pas laissé de comptage exploitable et sont
**marquées `estimé`**.

**Un défaut de comptage à corriger, et il explique l'essentiel de l'écart avec
la console** : `Reponse` expose `jetons_cache_ecrits`, mais aucune des boucles
d'appel ne l'additionne dans son cumul. **Les jetons d'écriture en cache n'ont
jamais été comptés nulle part**, alors qu'ils sont facturés à 1,25× le prix
d'entrée. Preuve chiffrée : en reconstruisant le prompt exact du lot 2 (28
appels, `2022_InfoU-exercices`) j'obtiens **669 736 caractères** pour
**104 748 jetons comptés**, soit **6,39 caractères par jeton**. Le français
technique tourne autour de 3,5–4. Le compteur ignore donc environ **40 % du
volume de prompt réellement facturé**.

---

## 1. Toutes les exécutions retrouvables, par coût décroissant

Tarifs appliqués, **vérifiés à la source** (voir la correction en §3) :
**Sonnet 5** $2,00 / $10,00 par MJetons — prix standard, sans échéance —
lecture de cache $0,20, écriture 5 min $2,50. **Opus 5** $5,00 / $25,00,
lecture $0,50, écriture $6,25.
« entrée » = jetons non mis en cache ; le prompt total est entrée + cache lu
+ cache écrit (non compté, voir §0).

| # | date | étape | corpus traité | modèle | réflexion | pré-filtrage | appels | entrée | cache lu | cache écrit | sortie | coût |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | 10 août | étage 0 `construire` | programme, 44 sections | Opus 5 | active | n/a | 44 | 37 432 | 185 674 | non compté | 117 572 | **3,22 $** |
| 2 | 11 août | étage 3 passe lot 1 | InfoA + InfoC + TPAlgo | Sonnet 5 | coupée | oui | 42 | 149 487 | 40 220 | non compté | 29 793 | **0,61 $** |
| 3 | 11 août | étage 3 **DIAGNOSTIC sans pré-filtrage** | InfoA + InfoC, **182 notions** | Sonnet 5 | active | **NON** | 9 | ~229 587 | 0 | non compté | ~13 500 | **0,59 $** *estimé* |
| 4 | 11 août | étage 3 passe lot 4 | LCR-rapport | Sonnet 5 | coupée | oui | 46 | 98 508 | 46 253 | non compté | 38 268 | **0,59 $** |
| 5 | 11 août | étage 3 dispersion **dA** | LCR-rapport | Sonnet 5 | coupée | oui | 46 | 98 508 | 44 242 | non compté | 37 005 | **0,58 $** |
| 6 | 11 août | étage 3 dispersion **dB** | LCR-rapport | Sonnet 5 | coupée | oui | 46 | 98 508 | 46 253 | non compté | 34 223 | **0,55 $** |
| 7 | 11 août | étage 3 passe lot 3 | Info-rapport | Sonnet 5 | coupée | oui | 36 | 79 864 | 36 198 | non compté | 26 346 | **0,43 $** |
| 8 | 11 août | étage 3 passe lot 2 | InfoU-exercices | Sonnet 5 | coupée | oui | 28 | 76 594 | 28 154 | non compté | 24 766 | **0,41 $** |
| 9 | 11 août | étage 3 InfoC **r0b** (reproductibilité) | InfoC | Sonnet 5 | coupée | oui | 12 | 26 690 | 69 825 | non compté | 8 962 | **0,16 $** |
| 10 | 11 août | étage 3 InfoC **r0a** (reproductibilité) | InfoC | Sonnet 5 | coupée | oui | 12 | 26 690 | 10 055 | non compté | 8 903 | **0,14 $** |
| 11 | 11 août | étage 3 InfoA + InfoC | 2 fichiers | Sonnet 5 | active | oui | 12 | 26 690 | 12 066 | non compté | 8 486 | **0,14 $** |
| 12 | 11 août | étage 3 InfoC **passe 2** (variance) | InfoC | Sonnet 5 | active | oui | 12 | 26 690 | 10 055 | non compté | 8 465 | **0,14 $** |
| 13 | 11 août | étage 0 `injecter §4.3` | spe777 §4.3 | Opus 5 | active | n/a | 1 | 1 189 | 0 | non compté | 4 709 | **0,12 $** |
| 14 | 11 août | étage 3 InfoA | InfoA | Sonnet 5 | active | oui | 3 | 9 991 | 0 | non compté | 4 597 | **0,07 $** |
| 15 | 11 août | étage 3 InfoA — 1re tentative, schéma 400 | InfoA | Sonnet 5 | active | oui | 3 | ~12 000 | 0 | non compté | ~600 | **0,03 $** *estimé* |
| 16 | 11 août | étage 0 `exclusions` | 27 mentions | Sonnet 5 | active | n/a | 1 | ~2 500 | 0 | non compté | ~2 500 | **0,03 $** *estimé* |
| — | — | étage 3 `passe-complete`, `dispersion`, tous les `--dry-run`, `--simuler`, re-validations | — | — | — | — | **0** | 0 | 0 | 0 | 0 | **0 $** |
| | | | | | | | **353** | | | | | **7,80 $** |

**Appels échoués, non facturés et non journalisés** : 3 × HTTP 400 (enum
nullable en mode strict), 6 × HTTP 400 (`temperature` déprécié), 2 × HTTP 529
(surcharge). Un 400 n'est pas facturé ; un 529 non plus.

Les trois lignes *estimées* le sont ainsi : la ligne 3 par reconstruction du
préfixe réel (159 603 caractères pour 182 notions, mesuré) divisé par le ratio
observé ; les lignes 15 et 16 par analogie avec des appels de même forme.

---

## 2. Ventilation

### Par étape

| étape | appels | coût | part |
|---|---:|---:|---:|
| **Étage 0** — construction du référentiel, §4.3, exclusions | 46 | **3,37 $** | 43 % |
| **Étage 1** — extraction | 0 | **0 $** | 0 % |
| **Étage 3 — production** (les 4 lots de la passe complète) | 152 | **2,04 $** | 26 % |
| **Étage 3 — mise au point et mesures** | 155 | **2,39 $** | 31 % |

L'étage 1 n'a rien coûté : il est entièrement déterministe, aucun appel LLM.
C'est le seul étage dans ce cas, et c'est aussi celui où six défauts ont été
trouvés — par des tests, pas par des appels.

### Par modèle

| modèle | appels | entrée | cache lu | prompt compté | sortie | coût |
|---|---:|---:|---:|---:|---:|---:|
| Opus 5 | 45 | 38 621 | 185 674 | 224 295 | 122 281 | 3,34 $ |
| Sonnet 5 | 308 | 962 307 | 343 321 | 1 305 628 | 246 414 | 4,46 $ |

**Opus 5 fait 13 % des appels et 43 % du coût.** Un appel Opus coûte en
moyenne 0,074 $ contre 0,014 $ pour un appel Sonnet — cinq fois plus, pour un
volume de sortie par appel bien supérieur (2 717 jetons contre 800).

### Part de la réflexion étendue

Non isolable directement : l'API ne facture pas les jetons de réflexion à part,
ils sont dans `output_tokens`. Mais la comparaison à configuration égale la
cerne, sur les mêmes 12 appels d'`InfoC` :

| | sortie | écart |
|---|---:|---:|
| réflexion **active** (passe 2) | 8 465 | — |
| réflexion **coupée** (r0a) | 8 903 | **+5 %** |

**Couper la réflexion n'a pas réduit la sortie, elle l'a légèrement augmentée.**
La réflexion ne représentait donc pas une part mesurable du coût sur cette
tâche — ce qui est cohérent avec ce qu'on a observé par ailleurs : le modèle ne
délibérait guère sur un choix dans une liste courte. **Le gain de couper la
réflexion est la reproductibilité, pas l'argent.** Sur l'étage 0, en revanche,
Opus 5 en réflexion adaptative sort 2 717 jetons par appel : là, elle pèse.

### Le coût de la passe sans pré-filtrage — chiffre exact demandé

| | par appel | 9 appels |
|---|---:|---:|
| préfixe **sans** pré-filtrage, 182 notions | 159 603 car. → **~25 510 jetons** | ~229 587 |
| préfixe **avec** pré-filtrage, ~39 notions en moyenne | 37 429 car. → **~6 401 jetons** | ~57 613 |
| **surcoût** | | **~171 974 jetons de prompt** |

Le préfixe complet est **4,3× plus gros**. Le diagnostic a donc coûté environ
**0,59 $ dont ~0,44 $ de pur surcoût**, pour 9 appels sur 2 fichiers.

La projection est ce qui compte : appliquer cette configuration aux 76
exercices du corpus aurait coûté **~1,94 M jetons de prompt** au lieu de
~487 k, soit **3,88 $ contre 0,97 $** pour la seule partie étiquetage.
**Le pré-filtrage économise 75 % du prompt** — et le diagnostic a montré qu'il
ne coûte rien en nombre d'étiquettes retenues (68 dans les deux cas).

### Efficacité du cache

**343 321 jetons lus en cache / 1 305 628 jetons de prompt comptés = 26 %.**

Chiffre trompeur, et à la baisse : le dénominateur exclut les écritures en
cache, jamais comptées. Le taux réel est plus élevé. Il reste que le cache est
structurellement bridé par le pré-filtrage — le préfixe n'est constant que
pour une même combinaison de sections, et 76 exercices produisent une trentaine
de combinaisons distinctes. C'est un arbitrage assumé et documenté dans
`etage3/contrats.py` : préfixe complet = cache parfait mais étiquetage moins
précis.

Le seul préfixe vraiment cachable est celui du **pré-filtrage** — 3 401
caractères, identique à tous les appels. Il explique les pics de lecture en
cache des lots.

### Réconciliation avec la console — l'écart, et où il est

| | console | mes journaux | écart |
|---|---:|---:|---:|
| Sonnet 5 | ~4 500 000 | 1 552 042 (prompt 1 305 628 + sortie 246 414) | **~2 950 000 manquants** |
| Opus 5 | ~500 000 | 346 576 (prompt 224 295 + sortie 122 281) | **~153 000 manquants** |

**Mes journaux ne totalisent pas ces volumes, et voici ce qui explique l'écart.**

1. **Les écritures en cache, jamais comptées** — cause principale. Le ratio
   mesuré (6,39 car./jeton contre ~3,8 attendus) implique qu'environ 40 % du
   prompt facturé échappe au compteur. Appliqué aux 1,31 M comptés, cela situe
   le prompt réel Sonnet autour de **2,2 M** : l'écart tombe de 2,95 M à
   ~2,3 M.
2. **Les sessions antérieures au 10 août.** La ligne 1 du tableau vient du
   `manifest.yaml`, pas d'une exécution observée — et ce manifeste ne décrit
   que la passe finale retenue. Le référentiel v1, la passe qui a perdu §3.4 et
   §4.3, `genere_v2` (213 notions, présent sur disque) et les essais de profil
   ont tous consommé des jetons dont **aucune trace ne subsiste** : le journal
   a été purgé à chaque `--rejouer`, et `oublier(etiquette)` efface les entrées
   d'une section dès qu'un contrat est violé. `genere_v2` seul représente une
   passe complète de 44 sections, soit un ordre de grandeur comparable à la
   ligne 1.
3. **Les appels détruits par la purge de journal.** `journal.oublier(etiquette)`
   est appelé à chaque `ErreurContrat` : les appels payés dont la réponse a été
   rejetée ne laissent rien.

Autrement dit : **l'écart n'est pas une anomalie de facturation, c'est une
lacune d'instrumentation.** Deux corrections rendraient le prochain rapport
exact — additionner `jetons_cache_ecrits` dans les cumuls, et écrire l'`usage`
de chaque appel dans le journal à côté de la charge. Aucune n'est faite ici :
le rapport est en lecture seule.

---

## 3. Coût unitaire, en configuration actuelle

Configuration : Sonnet 5, réflexion coupée, pré-filtrage actif, effort `high`.

| | valeur |
|---|---:|
| **une passe étage 3 complète** — 507 questions, 76 exercices, 152 appels | **2,04 $** |
| par question | **0,0040 $** |
| par exercice | 0,027 $ |
| par appel | 0,013 $ |

### Extrapolation aux 39 sujets (~3 300 questions)

En raisonnant à la question, l'unité la plus stable — le corpus prototype tient
507 questions pour 76 exercices, soit 6,7 questions par exercice ; 3 300
questions représentent donc ~494 exercices et ~988 appels.

| | jetons de prompt | jetons de sortie | **coût** |
|---|---:|---:|---:|
| une passe, tarif normal | ~3,2 M | ~1,6 M | **~13,20 $** |
| une passe, **API Batch −50 %** | ~3,2 M | ~1,6 M | **~6,60 $** |

Les deux chiffres sont à majorer d'environ 40 % pour les écritures en cache non
comptées : **~18 $ au tarif normal, ~9 $ en Batch**. Ordre de grandeur : une
passe complète sur le corpus de mesure coûte moins de vingt dollars.

### Correction — il n'y a pas d'échéance tarifaire

La première version de ce rapport annonçait que le tarif $2/$10 de Sonnet 5
expirait le 31 août 2026 et recommandait de lancer les 33 sujets avant cette
date. **C'était faux.** Je l'avais repris d'une table en cache sans le
vérifier. La page de tarification officielle dit :

> *« The $2/$10 per million input/output token pricing for Claude Sonnet 5,
> announced at launch as introductory pricing through August 31, 2026, **is now
> the standard price**. The previously scheduled increase to $3/$15 per million
> input/output tokens on September 1, 2026 **will not occur**. »*

**Le tarif est définitif.** Aucune urgence de calendrier. Les montants du
rapport sont inchangés — ils étaient déjà calculés à $2/$10 — et les autres
tarifs sont confirmés à la source : écriture de cache 5 min $2,50/MTok
(1,25×), lecture $0,20/MTok (0,1×), Batch $1/$5 (−50 %). Pour Opus 5 : $5/$25,
écriture $6,25, lecture $0,50.

---

## 4. Ce qui ne se reproduira pas

| | coût | se reproduit ? |
|---|---:|---|
| Étage 0 — construction du référentiel (44 sections, Opus 5) | 3,22 $ | **non** — une fois par matière |
| Étage 0 — injection §4.3, exclusions | 0,15 $ | **non** — rattrapages ponctuels |
| Étage 3 — diagnostic sans pré-filtrage | 0,59 $ | **non** — expérience tranchée, le filtre est innocenté |
| Étage 3 — reproductibilité et variance (r0a, r0b, passe 2, dA, dB) | 1,58 $ | **partiellement** — à refaire à chaque changement de protocole, pas à chaque passe |
| Étage 3 — mise au point (InfoA, InfoA+InfoC, tentative 400) | 0,24 $ | **non** |
| **Étage 3 — la passe elle-même** | **2,04 $** | **oui, et c'est tout** |

**Coût de construction : 5,76 $ (74 %). Coût de production : 2,04 $ (26 %).**

En régime établi, une passe d'étiquetage sur le prototype coûte **2,04 $**, et
sur les 39 sujets **~18 $**. Tout le reste — 74 % de la dépense de ces deux
jours — a servi à construire l'instrument et à en mesurer la fidélité.

Une réserve honnête : la mesure de dispersion (1,58 $, 21 % du total) **n'est
pas un coût perdu et n'est pas non plus à usage unique**. Elle est à refaire
chaque fois que le protocole change — modèle, réflexion, bornes du
pré-filtrage, vocabulaire du schéma. C'est le prix de savoir ce que valent les
chiffres publiés, et à 1,58 $ pour deux passes sur un fichier, il est modeste.

---

## 5. Trois leviers, chiffrés sur les 39 sujets

Base de comparaison : **~18 $** pour une passe complète, écritures en cache
incluses.

### Levier 1 — API Batch

**Économie : ~9 $ par passe, soit 50 %.**

Le Batch facture toutes les composantes à moitié prix et supporte l'appel
d'outils, le mode strict et la mise en cache. Le prix est la latence : la
plupart des lots finissent en moins d'une heure, le maximum contractuel est de
24 h. Pour une passe de mesure lancée le soir et lue le lendemain, c'est sans
inconvénient.

Deux contraintes à connaître avant de s'y engager : les résultats reviennent
**dans un ordre quelconque**, à réassocier par `custom_id` — l'identifiant
d'exercice s'y prête directement ; et le paramètre `fallbacks` est **rejeté**
sur le Batch, ce qui est sans effet ici puisque Sonnet 5 ne le supporte déjà
pas.

### Levier 2 — resserrement du pré-filtrage

**Économie : ~1,50 $ par passe, soit 8 %.** Le levier le plus faible des trois.

Le pré-filtrage fonctionne déjà : **74 exercices sur 76 sont restés dans la
borne de 4 sections**, 2 seulement ont demandé 5. La moyenne observée est de
~39 notions soumises sur 182, soit **21 %** — le gros de l'économie est déjà
acquis, et c'est le diagnostic à 0,59 $ qui l'a établi.

Ce qui reste : passer la borne haute de 4 à 3 sections ramènerait la moyenne
d'environ 39 à ~29 notions, soit **~25 % de prompt d'étiquetage en moins**.
Mais tu as tranché contre la troncature, avec un argument que le chiffre ne
contredit pas : couper sur un ordre sans portée sémantique supprime de
l'information au hasard. **Je ne recommande pas ce levier** — 8 % ne paie pas
le risque de perdre la section qui portait la bonne notion.

### Levier 3 — reprise depuis le journal

**Économie : jusqu'à 100 % d'une passe répétée — et 0 % dès que le protocole
change.**

Le mécanisme fonctionne : sur les 353 appels, la passe combinée finale a été
produite **sans un seul appel**, entièrement depuis le journal. Le coût
constaté de la reprise est nul.

Mais son rendement réel a été médiocre pendant ces deux jours, et pour une
bonne raison : **la signature a changé trois fois** — réglages
d'échantillonnage, puis vocabulaire du schéma, puis protocole complet. Chaque
changement a invalidé le journal existant. Les 92 entrées de LCR sous les
graines `dA`/`dB` ont dû être refaites pour la passe finale, soit **~1,15 $
dépensé deux fois**.

Ce n'est pas un défaut du mécanisme : **rejouer une réponse produite sous un
autre protocole serait bien pire que la repayer**. Le levier ne se mesure donc
pas en économie immédiate mais en discipline : maintenant que `config/mesure.yaml`
est figé et entre dans la signature par construction, les prochaines passes
sous le même protocole seront gratuites. C'est **le levier le plus rentable des
trois pour les 39 sujets**, à condition de ne plus toucher au protocole entre
les lots — et de lancer les 33 sujets restants en une seule campagne plutôt
qu'en essais successifs.

---

---

## 6. Corrections appliquées après ce rapport

### Comptage des jetons — fait

`Reponse.usage()` rend désormais le comptage complet d'un appel : `entree`,
`cache_lus`, **`cache_ecrits`**, `sortie` et `prompt_total`. Il est
additionné dans les cumuls des trois commandes qui appellent le modèle
(`etage0 construire`, `etage0 injecter`, `etage3 etiqueter`) et **écrit dans le
journal à chaque appel**, à côté de la charge. `etage0 exclusions`, qui
n'affichait aucun comptage, en affiche un.

L'affichage passe de « entrée / sortie » à **prompt total décomposé** :

```
jetons : prompt 144761 (98508 neufs + 46253 lus + 0 écrits en cache) / 38268 sortie
         cache : 32 % du prompt lu en cache, 0 % écrit
```

Le prochain rapport n'aura donc rien à estimer, et la réconciliation avec la
console pourra être exacte. Les 352 entrées déjà au journal restent sans
comptage — c'est irrécupérable.

### Tri par combinaison de sections — fait, et il rapporte moins qu'espéré

L'étiquetage se fait maintenant en **deux phases** : le pré-filtrage passe
d'abord sur tout le corpus, puis les exercices sont **triés par combinaison de
sections** avant l'étiquetage, pour que des appels consécutifs partagent le
préfixe. Aucune clé de journal, aucun prompt et aucun résultat ne change —
vérifié en rejouant la passe complète depuis le journal avec une clé d'API
invalide : **507 questions, 556 étiquettes, 1,10 de moyenne, 82/182 notions,
cumul top 10 47,5 %, à l'identique.** L'ordre de la SORTIE reste celui du
corpus pour que deux passes restent comparables ligne à ligne.

Le gain réel est modeste, et le chiffre mérite d'être dit :

```
76 exercices → 52 combinaisons de sections distinctes

  39 exercices ont une combinaison UNIQUE     (51 %)  préfixe écrit puis jeté
  37 partagent leur combinaison               (49 %)  dont 24 lisent au lieu d'écrire

  1 groupe de 10 · 1 de 4 · 1 de 3 · 10 de 2 · 39 de 1
```

**24 écritures de cache évitées sur 76**, à ~6 400 jetons de préfixe, soit
~0,35 $ par passe — **17 %**. C'est réel mais ce n'est pas le levier que
j'imaginais : le pré-filtrage produit des combinaisons trop diverses pour que
le regroupement paie beaucoup. La moitié des exercices reste seule dans sa
combinaison.

Le seul gros groupe — 10 exercices — partage
`complexite_algo + modelisation + preuve + strategies`, la combinaison
générique. C'est cohérent avec le reste : le corpus se concentre sur `preuve`
et `complexite_algo`, et le pré-filtrage le reflète.

**Ce tri ne remplace pas le Batch**, il s'y ajoute : les deux réductions se
composent.

---

## Ce que je recommande, en une ligne

Lancer les 33 sujets **en Batch, sous le protocole figé** — ~9 $ au lieu de
~18 $, sans échéance à respecter. Le comptage est corrigé, le tri est en place,
et la prochaine passe rendra des chiffres exacts au lieu d'estimations.

---

# 7. La campagne réelle — 2026-08-12

L'estimation de ~9 $ était juste. Le chiffrage ci-dessous vient du journal,
appel par appel, pour la signature `0e934c2afcf24a4b` (672 appels : 336
exercices × 2 phases, sur 38 documents et 2 199 questions).

| phase | appels | prompt | sortie | coût lot | coût direct |
|---|--:|--:|--:|--:|--:|
| pré-filtrage | 336 | 1 200 493 | 78 580 | 1,66 $ | 3,33 $ |
| étiquetage | 336 | 5 057 630 | 314 383 | 7,55 $ | 15,10 $ |
| **total** | **672** | **6 258 123** | **392 963** | **9,21 $** | **18,43 $** |

## Le cache a coûté de l'argent

C'est le résultat le plus net de la campagne, et il contredit le §6 :

| | jetons | effet |
|---|--:|--:|
| écritures en cache (1,25×) | 4 686 543 | **−1,17 $** |
| lectures en cache (0,1×) | 200 577 | +0,18 $ |
| | | **bilan −0,99 $** |

**75 % du prompt a été écrit en cache et 4 % relu.** Le tri par combinaison de
sections, qui fonctionnait en synchrone, ne sert plus : 336 exercices se
répartissent en **172 combinaisons distinctes**, et les tranches de 10 imposées
par le plafond de grammaires (voir ci-dessous) cassent ce qui restait de
contiguïté. Une écriture en cache jamais relue est un surcoût de 25 %, point.

**À faire avant la prochaine campagne : conditionner `cache_control` au mode.**
En lot, le retirer. Économie attendue : ~1 $ sur 9, soit 11 %.

## Le plafond qui n'existe qu'en lot

Le premier lot d'étiquetage a échoué à **237 sur 260** : *« Grammar compilation
rate limit exceeded : 20 compilations per minute »*. Chaque requête
d'étiquetage porte un schéma d'outil différent — `schema_etiquettes` construit
ses enums à partir des notions candidates et des identifiants de questions de
l'exercice — et le mode strict compile une grammaire par schéma distinct.

Le pré-filtrage partage **un seul** schéma : 260 requêtes, zéro échec. Ce
plafond est invisible en synchrone, où les appels s'espacent d'eux-mêmes.
Correctif : soumission par tranches de 10, séquentielles. Zéro échec ensuite.
Les requêtes en erreur ne sont pas facturées.

## Ce que mes erreurs ont coûté

Deux fautes d'opération, chiffrées plutôt que résumées :

- **je n'ai pas arrêté le premier processus avant d'en relancer un second.**
  Après l'échec du lot, la boucle principale est repartie en appels directs :
  **32 appels d'étiquetage au plein tarif** au lieu du tarif lot, soit
  **≈ 0,72 $** de surcoût. Un garde-fou l'interdit désormais — en mode `--batch`,
  une clé absente du journal est comptée en `manquants` et signalée, jamais
  rejouée en direct ;
- **j'ai purgé l'enregistrement d'un lot de 10 encore en vol**, resoumis
  ensuite : **≈ 0,23 $**.

Total de la casse : **≈ 0,95 $ sur 9,21 $**, soit 10 %. J'avais d'abord annoncé
« environ 190 appels synchrones » : c'était faux, le compte de clés sur lequel
je m'appuyais mélangeait les signatures de plusieurs passes de diagnostic.

## Où en est le budget

Construction et prototype (rapport initial) : 7,80 $. Campagne complète :
9,21 $. **Total du projet : ≈ 17 $** pour un référentiel de 182 notions
confronté à 2 199 questions, soit **0,0042 $ la question** — stable par rapport
aux 0,0040 $ du prototype, ce qui confirme que le coût est linéaire au corpus.
