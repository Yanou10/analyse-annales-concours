# Workflow n8n — traiter un sujet déposé

Un sujet `.md` arrive dans le seau MinIO `corpus` → le workflow l'extrait,
l'étiquette en Batch, en tire la distribution, et s'arrête net si une étape
échoue.

[`pipeline.json`](pipeline.json) — 26 nœuds, importable tel quel.

## Importer

1. n8n → **Workflows** → **Import from File** → `n8n/pipeline.json`
2. **Save**, puis basculer l'interrupteur sur **Active**. Sans activation,
   seule l'URL de test répond, et pour un seul appel.
3. Relever l'URL de production du webhook sur le nœud « Réception du dépôt » :

```
https://<ton-domaine>/webhook/traiter
```

Le workflow appelle `http://annales-service:8000` sur le réseau `stack_default`.
Rien à configurer : ni identifiant, ni clé. Le service porte déjà la clé
Anthropic dans son environnement, et il n'est pas exposé à l'extérieur.

## Brancher la notification MinIO

Sur le bucket `corpus`, événement `s3:ObjectCreated:*` vers l'URL de production.

```bash
mc alias set stack http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"

# 1. déclarer la cible webhook (redémarre MinIO)
mc admin config set stack notify_webhook:n8n \
    endpoint="https://<ton-domaine>/webhook/traiter" \
    queue_limit="100"
mc admin service restart stack

# 2. abonner le bucket
mc event add stack/corpus arn:minio:sqs::n8n:webhook \
    --event put --suffix .md

mc event list stack/corpus          # vérification
```

Le `--suffix .md` évite de déclencher sur autre chose ; le workflow refuse de
toute façon ce qui ne finit pas par `.md`.

**Par la console MinIO** : *Events* → *Add Event Destination* → *Webhook*,
puis *Buckets → corpus → Events → Subscribe*.

## Charge utile acceptée

Le nœud « Normaliser l'événement » accepte les deux formes :

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

```bash
curl -X POST https://<ton-domaine>/webhook/traiter \
     -H 'content-type: application/json' \
     -d '{"cle":"2024_InfoA.md"}'
```

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
borne d'itérations est atteinte. La borne s'appuie sur `$runIndex`, le compteur
de passages du nœud dans l'exécution courante — pas d'état à trimballer dans
les items.

| étape | borne | durée maximale |
|---|--:|--:|
| extraction | 20 tours | 10 min |
| **étiquetage** | **360 tours** | **3 h** |
| mesure | 20 tours | 10 min |

Trois heures pour l'étiquetage parce qu'un lot Batch met des dizaines de
minutes : une borne courte tuerait une campagne qui se déroule normalement.

## En cas d'échec

« Composer le rapport d'échec » lit la tâche **courante** — celle de l'étape
qui vient d'échouer — et remonte l'étape, la cause, l'état, le code de retour
et les 4 000 derniers caractères de `stderr`. Puis « Arrêter en erreur »
marque l'exécution comme échouée.

Le workflow ne continue jamais sur une étape ratée : mesurer un corpus
incomplet est pire que s'arrêter.

Pour être prévenu : **Settings → Error Workflow** sur ce workflow, pointant un
second workflow avec ton canal (Slack, e-mail, Telegram). C'est le mécanisme
natif de n8n, et il évite de mettre une credential dans ce fichier-ci. Les deux
nœuds terminaux « Notifier la réussite » et « Notifier l'absence de
référentiel » sont là pour y accrocher la même chose côté succès.

## Écriture en base — la limite à connaître

**Il n'existe pas d'endpoint HTTP pour l'import.** `annales-import` est une
commande, et n8n ne peut pas l'exécuter dans le conteneur du service sans accès
au socket Docker.

Le nœud « Enregistrer la passe en base » est donc **désactivé à l'import**. Il
n'écrit qu'une ligne dans `passes` — la seule table dont le workflow ait les
données — et il exige une credential Postgres, qui ne peut pas voyager dans ce
JSON. Pour l'activer : ouvrir le nœud, choisir une credential Postgres pointant
la base `annales`, et le réactiver.

Le chargement complet — `documents`, `exercices`, `questions`, `notions`,
`etiquettes` — reste à faire à la main :

```bash
docker compose exec annales-service annales-import \
  --corpus /travail/corpus --referentiel /travail/referentiel/genere/sections \
  --etiquettes /travail/passe --passe <nom-de-la-passe>
```

Le compte rendu de fin rappelle cette commande avec le nom de la passe.

## Préalable : un référentiel

Le workflow interroge `/sante` et s'arrête sur « Notifier l'absence de
référentiel » s'il n'y en a aucun — c'est l'état d'une instance neuve, pas une
panne. Le créer d'abord :

```bash
curl -X POST http://annales-service:8000/construire \
     -H 'content-type: application/json' \
     -d '{"programme":"spe777_annexe_1373646.md"}'
```

puis suivre la tâche jusqu'à lire son empreinte dans `resultat.empreinte`.

## Ce que le workflow ne fait pas

- **La confrontation** (`POST /confronter`) n'est pas dans l'enchaînement : elle
  exige un `sondes.yaml` écrit à la main sous le préfixe du référentiel, et
  elle relève d'un travail d'instruction, pas d'un déclenchement sur dépôt.
- **Un seul sujet par exécution.** Un dépôt = une exécution = un lot. Pour
  traiter un corpus entier d'un coup, appeler `/extraire` puis `/etiqueter`
  directement avec la liste complète : l'étiquetage tire son intérêt du
  regroupement par combinaison de sections, qui n'opère qu'à l'intérieur d'un
  même appel.
