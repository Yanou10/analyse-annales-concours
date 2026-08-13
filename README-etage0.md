# Étage 0 — programme officiel → référentiel de notions attribuables

Produit le référentiel au lieu de le rédiger à la main, pour qu'il soit
reproductible, versionné, et rejouable sur une autre matière.

```
programme.md ──[segmentation déterministe]──▶ unités candidates
                                                   │
                          critère d'admission ──▶ [appel LLM, mode outil]
                                                   │
                                    ▼──────────────┴──────────────▼
                        référentiel/genere/sections/*.yaml   refus.json
                                    manifest.yaml       exclusions.json
```

## Ordre d'exécution — le déterministe d'abord

L'échec précédent du projet était un bug d'étage déterministe qui a contaminé
2 011 étiquettes en aval. La segmentation se valide **avant** de dépenser le
premier euro.

```bash
cp .env.example .env          # renseigner ETAGE0_PROGRAMME

# 1. Déterministe, aucun appel réseau. À lire à l'œil.
etage0 segmenter
etage0 segmenter --detail | less
etage0 segmenter --sortie-json unites.json

# 2. Les prompts exacts, toujours sans appeler.
etage0 construire --dry-run
etage0 construire --dry-run --section 4.5

# 3. Passe locale gratuite, pour stabiliser les prompts.
docker compose --profile local up -d ollama
etage0 construire --fournisseur ollama

# 4. Passe payante, mesurée contre l'étalon écrit à la main.
etage0 construire --fournisseur anthropic --etalon referentiel/v1/sections

# 5. Classement des mentions restrictives -> exclusions.json
etage0 exclusions
```

## Ce que fait la segmentation, et pourquoi

Trois propriétés du corpus dictent l'implémentation. Chacune a été trouvée en
lisant la sortie, pas en la supposant.

| Propriété | Conséquence |
|---|---|
| L'unité de décision est la ligne **logique** de tableau, étalée sur plusieurs lignes markdown | Reconstruction par accord des **deux** colonnes. Sur la seule colonne gauche, §3.4 se découpe en 3 entrées là où il n'y en a qu'une, et §4.3 en fusionne 3 en une seule. |
| L'action à admettre est souvent dans la colonne *Commentaires*, pas *Notions* | Les deux colonnes voyagent ensemble jusqu'au modèle. §3.4 en est le cas d'école : la colonne Notions n'est que du vocabulaire, l'action (« représenter par matrice ou par listes d'adjacence ») est dans le commentaire. |
| Les niveaux de titre sont incohérents (`# 4`, `# 4.3`, `### 4.5`) | Le chemin de section se reconstruit depuis la **numérotation**, jamais depuis le niveau. |

Limite assumée : le markdown coupe parfois au milieu d'un mot (« Paradigme im »
+ « pératif »). On recolle avec une espace plutôt que de deviner — une
heuristique sans lexique produirait autant d'erreurs qu'elle en corrige, et le
modèle lit sans peine à travers l'artefact.

Sortie actuelle sur le programme MPI : **44 sections, 232 unités candidates**
(105 lignes de tableau, 83 puces d'annexe, 20 « Mise en œuvre », 24 prose),
19 unités écartées et journalisées.

## Décisions d'API

- **`claude-opus-5`**, `thinking: adaptive`, `effort` réglable. Pas de
  `temperature` / `top_p` / `budget_tokens` : ce modèle les rejette en 400.
- **Mode outil, schéma `strict`.** Jamais de JSON demandé en prose. Les
  contraintes que le mode strict ne supporte pas (cardinalités, longueurs) sont
  absentes du schéma envoyé et vérifiées dans `contrats.valider_decisions` —
  une violation purge l'entrée de journal et n'est jamais écrite au référentiel.
- **Cache de prompt** sur le préfixe constant (~1 670 jetons ≫ 512, le minimum
  cacheable d'Opus 5). Toute interpolation variable dans ce préfixe le tuerait ;
  le CLI avertit si `cache_read_input_tokens` reste à zéro sur plusieurs appels.
- **Repli serveur sur refus** activé par défaut (`fallbacks: "default"`). Les
  classificateurs de sûreté renvoient un HTTP 200 portant
  `stop_reason: "refusal"` : le code teste `stop_reason` **avant** de lire
  `content`, faute de quoi un refus se manifesterait par une `IndexError`
  trompeuse. Débrayable par `ETAGE0_FALLBACKS=0`.

## Reprise et rejeu

Le journal (`.etage0/journal.jsonl`) indexe chaque appel réussi par une
empreinte qui couvre le contenu des unités, le modèle, le fournisseur, la
version de prompt **et** le critère d'admission. Changer l'un d'eux invalide
l'entrée : réutiliser en silence un résultat obtenu sous un autre prompt serait
mesurer une chose et en publier une autre.

`--rejouer` purge tout. Une section dont le contrat est violé est purgée
individuellement, puis re-tentée au prochain lancement.

## Portabilité à une autre matière

Rien dans `etage0/` ne mentionne l'informatique. Tout le contenu spécifique vit
dans `profils/<matiere>.yaml` : critère d'admission, sections cibles et leurs
périmètres, valeurs de l'axe langage, motifs de mentions restrictives,
exclusions déterministes, cibles de dimensionnement.

Changer de matière = écrire un autre profil et pointer `ETAGE0_PROFIL` dessus.

## Mesure

`--etalon <dossier>` compare la sortie aux sections rédigées à la main et écrit
`comparaison_etalon.json`. Le rappel y est calculé sur les identifiants : c'est
un **plancher**, pas un verdict — un slug différent pour la même action y compte
comme un échec. Lire `manquants` à l'œil avant de conclure.

La validation rapporte, elle ne bloque pas, sur : renvois `voir` morts
(bloquant), identifiants en double (bloquant), libellés ne commençant pas par un
verbe, sections vides, et dépassement des cibles de dimensionnement. Le
dimensionnement se décide sur la mesure du corpus, pas sur un seuil posé
d'avance.
