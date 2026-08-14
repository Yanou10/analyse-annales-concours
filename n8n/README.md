# Workflows n8n

Deux workflows, deux buckets, deux webhooks. **Aucune credential à configurer** :
ils ne parlent qu'au service, qui porte déjà la clé Anthropic, l'accès MinIO et
`DATABASE_URL` dans son environnement.

| fichier | déclencheur | webhook | ce qu'il fait |
|---|---|---|---|
| [`referentiel.json`](referentiel.json) | dépôt dans `programmes` | `/programme` | construit le référentiel — **16 nœuds** |
| [`pipeline.json`](pipeline.json) | dépôt dans `corpus` | `/traiter` | extrait, étiquette, mesure, importe — **30 nœuds** |

## Ordre de mise en service

**Le programme d'abord, le corpus ensuite.** Le workflow principal interroge
`/sante` et sort par « Notifier l'absence de référentiel » s'il n'y en a aucun :
sans premier maillon, tout dépôt dans `corpus` s'arrête là.

1. importer les deux workflows, les activer ;
2. brancher les deux cibles MinIO (ci-dessous) ;
3. déposer un programme officiel dans `programmes` → un référentiel apparaît
   sous `sorties/referentiels/<empreinte>/` ;
4. **regarder ce référentiel** avant d'aller plus loin ;
5. déposer les sujets dans `corpus`.

## Importer

n8n → **Workflows** → **Import from File**, une fois par fichier. **Save**, puis
basculer sur **Active** : sans activation, seule l'URL de test répond, et pour
un seul appel.

Les URL de production se lisent sur les nœuds de réception :

```
https://<ton-domaine>/webhook/programme
https://<ton-domaine>/webhook/traiter
```

## Brancher MinIO — deux cibles, pas une

**Une cible `notify_webhook` porte une seule URL.** Deux buckets abonnés au même
ARN postent donc au même endroit : impossible de router `programmes` vers
`/programme` et `corpus` vers `/traiter` avec une cible unique. Il en faut
**deux**, chacune avec son endpoint, et chaque bucket s'abonne à la sienne.

**`mc admin config set` ignore SILENCIEUSEMENT `enable=on`.** La cible est
créée, l'endpoint enregistré, et aucun événement ne part — sans message
d'erreur. L'activation doit passer par l'environnement du conteneur MinIO :

```yaml
# docker-compose.yml, service minio
environment:
  MINIO_NOTIFY_WEBHOOK_ENABLE_n8n: "on"
  MINIO_NOTIFY_WEBHOOK_ENDPOINT_n8n: "https://<ton-domaine>/webhook/traiter"
  MINIO_NOTIFY_WEBHOOK_ENABLE_n8n_programme: "on"
  MINIO_NOTIFY_WEBHOOK_ENDPOINT_n8n_programme: "https://<ton-domaine>/webhook/programme"
```

Redémarrer MinIO, puis abonner les buckets :

```bash
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

# --- abonnements
mc event add local/corpus     arn:minio:sqs::n8n:webhook           --event put --suffix .md
mc event add local/programmes arn:minio:sqs::n8n_programme:webhook --event put --suffix .md

mc event list local/corpus
mc event list local/programmes
```

> ⚠ `mc event add local/programmes arn:minio:sqs::n8n:webhook` — l'ARN sans
> suffixe — enverrait les dépôts de programmes au workflow des **sujets**, qui
> les refuserait après coup. C'est l'ARN qui distingue, pas le bucket.

Vérifier que les deux cibles sont montées :

```bash
mc admin info local --json | jq '.info.sqsARN'
# ["arn:minio:sqs::n8n:webhook", "arn:minio:sqs::n8n_programme:webhook"]
```

**Par la console** : *Events* → *Add Event Destination* → *Webhook*, deux fois
avec deux identifiants distincts, puis *Buckets → … → Events → Subscribe*.

---

# Workflow 1 — construire un référentiel

Dépôt dans `programmes` → `POST /construire` → attente → compte rendu avec
l'empreinte.

## Le garde-fou de dépense

**Une construction coûte environ 3 $ en appels Opus sur 44 sections.** Le
workflow refuse donc de reconstruire si un référentiel a déjà été produit depuis
ce programme, et sort par « Notifier la dépense évitée ».

Le rapprochement se fait sur la **clé de l'objet**, inscrite dans `origine.json`
par le service. C'est la seule information dont dispose le workflow : il ne
télécharge pas le fichier et ne peut donc pas en calculer l'empreinte de
contenu.

**Conséquence à connaître : redéposer un programme _corrigé_ sous le même nom
est bloqué aussi.** C'est le bon défaut à 3 $ l'appel. Pour passer outre :

```bash
curl -X POST https://<ton-domaine>/webhook/programme \
     -H 'content-type: application/json' \
     -d '{"cle":"programme-officiel.md","forcer":true}'
```

## Borne

40 tours de 30 s, soit **20 minutes**. La construction est un appel Opus sur
44 sections : plus lente que les étapes du workflow principal.

## Ce que rend le compte rendu

`empreinte`, `notions`, `signature_etiquetage`, `prefixe`, `duree_s`,
`avertissements_granularite`, et surtout **`sujets_en_attente`** : le workflow
liste `corpus/` par `GET /objets?seau=corpus` et dit combien de sujets y dorment
déjà.

Le contrôle final de l'étage 0 **ne bloque plus la publication**. Il rapporte
tout — défauts d'**intégrité** comme avertissements de **granularité** — mais le
référentiel est publié dans tous les cas, et les constats sont recensés dans
`manifest.yaml` sous `anomalies`.

Le compte rendu remonte les deux catégories depuis `stderr`, dans
`defauts_integrite` et `avertissements_granularite`, et bascule `resultat` en
« réussi avec réserves » dès qu'un défaut d'intégrité subsiste. Rien n'est
masqué : seule la conséquence a changé.

Bloquer arrêtait toute la chaîne aval — un référentiel construit intégralement
restait non publié pour deux renvois d'une section d'annexes, et l'étiquetage
sortait aussitôt par « absence de référentiel ». Le comportement bloquant reste
accessible par `etage0 construire --strict`, pour quand la purge des annexes
sera écrite.

**Il n'enchaîne pas.** Les sujets déposés *avant* la construction n'ont
déclenché aucun événement exploitable, et l'étiquetage se paie : le référentiel
qui vient d'être construit mérite d'être regardé avant qu'on mesure 2 000
questions contre lui. Le compte rendu dit quoi faire ensuite, il ne le fait pas.

---

# Workflow 2 — traiter un sujet déposé

Dépôt dans `corpus` → `/extraire` → `/etiqueter` en Batch → `/mesurer` →
`/importer`.

## Charge utile acceptée

```jsonc
// notification MinIO
{"Records": [{"s3": {"object": {"key": "2024_InfoA.md"}}}]}

// appel manuel
{"cle": "2024_InfoA.md"}
{"cle": "2024_InfoA.md", "lot": "mpi-2024", "passe": "essai-1",
 "referentiel": "fd7678c6ed6a32b5"}
```

La clé S3 est décodée : MinIO encode les espaces en `+`, et un sujet nommé
`2024 InfoA.md` arriverait sinon sous un nom que le service ne trouve pas.

Sans `lot` ni `passe`, ils sont dérivés du nom du fichier, la passe étant
horodatée. Sans `referentiel`, le workflow prend le premier que `/sante`
annonce disponible.

## Le motif d'attente

Le service rend un identifiant et travaille en fond. Après chaque lancement :

```
Lancer X → Attendre X (30 s) → Vérifier X (GET /taches/{id})
              ↑                        ↓
              │                  X terminée ?  ──oui──→ étape suivante
              │                        │non
              └──non─── X irrécupérable ?  ──oui──→ Composer le rapport d'échec
```

Le webhook **répond immédiatement** (`onReceived`) : MinIO n'attend pas la fin
d'une campagne de plusieurs heures.

`X irrécupérable ?` est vrai si l'état est `echec` ou `interrompu`, **ou** si la
borne est atteinte. La borne s'appuie sur `$runIndex`, le compteur de passages
du nœud dans l'exécution courante — pas d'état à trimballer dans les items.

| workflow | étape | borne | durée |
|---|---|--:|--:|
| référentiel | construction | 40 tours | 20 min |
| principal | extraction | 20 tours | 10 min |
| principal | **étiquetage** | **360 tours** | **3 h** |
| principal | mesure | 20 tours | 10 min |
| principal | import en base | 20 tours | 10 min |

Trois heures pour l'étiquetage parce qu'un lot Batch met des dizaines de
minutes : une borne courte tuerait une campagne qui se déroule normalement.

## Écriture en base

`POST /importer` lance `annales-import` en tâche de fond, même motif d'attente.
`DATABASE_URL` vient de l'environnement du service et n'est jamais acceptée dans
un corps de requête.

L'import est idempotent : rejouer le workflow sur le même sujet ne duplique
rien. `documents.empreinte` est unique, et les étiquettes portent la clé
`(question_id, notion_id, passe)` — deux passes du même corpus coexistent au
lieu de s'écraser.

Avant la première exécution, contrôler le schéma :

```bash
curl -s -X POST http://annales-service:8000/importer \
     -H 'content-type: application/json' \
     -d '{"verifier_seulement": true}'
```

Sur une base antérieure à `exercices.rang`, la commande nomme l'écart ;
correctif : `ALTER TABLE exercices ADD COLUMN IF NOT EXISTS rang INTEGER;`.

---

## En cas d'échec

« Composer le rapport d'échec » lit la tâche **courante** — celle de l'étape qui
vient d'échouer — et remonte l'étape, la cause, l'état, le code de retour et les
4 000 derniers caractères de `stderr`. Puis « Arrêter en erreur » marque
l'exécution comme échouée.

Aucun des deux workflows ne continue sur une étape ratée : mesurer un corpus
incomplet est pire que s'arrêter.

Pour être prévenu : **Settings → Error Workflow** sur chaque workflow, pointant
un troisième workflow avec ton canal (Slack, e-mail, Telegram). C'est le
mécanisme natif de n8n, et il garde les credentials hors de ces fichiers. Les
nœuds terminaux « Notifier la réussite », « Notifier la dépense évitée » et
« Notifier l'absence de référentiel » sont là pour y accrocher la même chose.

## Ce que les workflows ne font pas

- **La confrontation** (`POST /confronter`) n'est dans aucun des deux : elle
  exige un `sondes.yaml` écrit à la main sous le préfixe du référentiel, et
  relève d'un travail d'instruction, pas d'un déclenchement sur dépôt.
- **Un seul sujet par exécution.** Un dépôt = une exécution = un lot. Pour un
  corpus entier d'un coup, appeler `/extraire` puis `/etiqueter` avec la liste
  complète : le regroupement par combinaison de sections, qui fait l'économie
  de cache, n'opère qu'à l'intérieur d'un même appel.
- **Le passage du référentiel au corpus reste manuel**, par choix.
