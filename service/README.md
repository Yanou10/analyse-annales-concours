# Service HTTP — n8n orchestre, Python calcule

Le service expose les quatre étages. Il ne contient aucune logique métier : il
valide des chemins, lance les commandes en sous-processus et rend l'état des
tâches. Une passe lancée par HTTP est la même qu'une passe lancée à la main.

**Tout appel est asynchrone.** Il rend un identifiant tout de suite ; l'état se
lit ensuite sur `/taches/{id}`. Un étiquetage dure des minutes : une requête
synchrone expirerait chez l'orchestrateur, et un client qui réessaie relancerait
des appels payants.

Adresse interne : `http://annales-service:8000`. Aucun port publié.

## Approvisionner le volume — à faire avant tout

**Le référentiel n'est pas dans l'image.** C'est de la matière produite : la
figer dans une image obligerait à reconstruire à chaque notion corrigée, et
ferait diverger l'image de ce qu'on mesure. Il vit dans `/travail`, avec le
corpus, le journal des appels et les passes.

```bash
docker compose cp referentiel annales-service:/travail/referentiel
docker compose cp .etage0/journal.jsonl annales-service:/travail/journal/journal.jsonl
```

Le journal porte les appels déjà payés : le déposer évite de repayer une
campagne. Tant que le référentiel manque, le service démarre et `/sante` répond
`"etat": "referentiel_absent"` avec le chemin attendu — jamais « 0 notion »,
qui se lirait comme une mesure.

## Endpoints

| méthode | chemin | commande lancée |
|---|---|---|
| `GET` | `/sante` | — (lecture directe) |
| `POST` | `/extraire` | `etage1 extraire … --sortie …` |
| `POST` | `/confronter` | `etage0 confronter …` |
| `POST` | `/etiqueter` | `etage3 [--modele] etiqueter … --sortie … [--batch]` |
| `POST` | `/mesurer` | `etage4 [--referentiel] [--sans-entete] <sous-commande> …` |
| `GET` | `/taches/{id}` | — |
| `GET` | `/taches` | — |

### `GET /sante`

```bash
curl -s http://annales-service:8000/sante | jq
```

Rend l'empreinte du référentiel, la **signature de protocole** que l'étage 3
utilisera, et si `ANTHROPIC_API_KEY` est présente — jamais sa valeur.

### `POST /extraire`

```bash
curl -s -X POST http://annales-service:8000/extraire \
  -H 'content-type: application/json' \
  -d '{"fichiers":["sujets/2024_InfoA.md","sujets/2024_InfoC.md"],"sortie":"corpus"}'
```

### `POST /confronter`

```bash
curl -s -X POST http://annales-service:8000/confronter \
  -H 'content-type: application/json' \
  -d '{"corpus":["corpus"],"minimum":2,"sortie":"rapports/confrontation.json"}'
```

Déterministe, aucun appel de modèle.

### `POST /etiqueter`

```bash
curl -s -X POST http://annales-service:8000/etiqueter \
  -H 'content-type: application/json' \
  -d '{"corpus":["corpus"],"sortie":"passe-39","batch":true,"tranche_lot":10}'
```

Refusé en 503 si la clé est absente, plutôt que d'accepter une tâche qui
échouera après la mise en file. `"dry_run": true` montre les prompts sans rien
appeler et ne demande pas de clé.

### `POST /mesurer`

```bash
curl -s -X POST http://annales-service:8000/mesurer \
  -H 'content-type: application/json' \
  -d '{"sous_commande":"distribution","passes":["passe-39"]}'

curl -s -X POST http://annales-service:8000/mesurer \
  -H 'content-type: application/json' \
  -d '{"sous_commande":"dashboard","passes":["passe-39"],"sortie":"tableau-de-bord.html"}'

curl -s -X POST http://annales-service:8000/mesurer \
  -H 'content-type: application/json' \
  -d '{"sous_commande":"dispersion","passes":["passe-39","dispersion-39B"]}'
```

Sous-commandes à une passe : `distribution`, `fichier`, `section`, `filiere`,
`annee`, `genre`, `langage`, `exercice`, `zero`, `top`, `croisement`, `tout`,
`dashboard`. À deux passes : `dispersion`, `comparer`. Un nom inconnu est
refusé en 400 avec la liste.

## Suivre une tâche

```bash
ID=$(curl -s -X POST http://annales-service:8000/etiqueter \
      -H 'content-type: application/json' \
      -d '{"corpus":["corpus"],"sortie":"passe-39","batch":true}' | jq -r .tache)

until [ "$(curl -s http://annales-service:8000/taches/$ID | jq -r .etat)" \
        != "en_cours" ]; do sleep 20; done

curl -s http://annales-service:8000/taches/$ID | jq '{etat, code_retour, duree_s}'
curl -s http://annales-service:8000/taches/$ID | jq -r .stderr | tail -40
```

États : `en_attente`, `en_cours`, `fini`, `echec`, `interrompu`. Le dernier
signale une tâche que le redémarrage du service a coupée — jamais une tâche
qu'on croit encore vivante.

`GET /taches?etat=echec&limite=20` filtre la liste.

## Garanties

- **Une seule tâche lourde à la fois.** L'étiquetage passe par une file à un
  exécutant unique. Deux passes concurrentes sur le même corpus paieraient deux
  fois les mêmes appels : le journal des étages ne dédoublonne qu'après la
  réponse du modèle.
- **La clé ne vient que de l'environnement.** Elle n'est acceptée dans aucun
  corps de requête, et `/sante` n'en dit que la présence.
- **Aucun chemin hors de `/travail`.** La vérification porte sur le chemin
  résolu, pas sur la chaîne : filtrer `..` par motif laisse passer les liens
  symboliques.
- **L'état survit au redémarrage.** Un fichier JSON par tâche dans
  `/travail/taches`, écrit par `rename` atomique.
- **Journalisation JSON sur stdout**, uvicorn compris : `docker logs annales-service | jq`.

## Import en base

Le schéma de référence est dans [`schema.sql`](schema.sql). L'import vérifie
que la base réelle lui correspond **avant** d'écrire, et refuse en nommant les
écarts plutôt que d'échouer à la 1 800ᵉ ligne.

**À lancer en premier, avant tout import.** Le schéma du VPS est antérieur à
`exercices.rang` : la commande nomme cet écart et tous les autres, plutôt que
de laisser deviner.

```bash
docker compose exec annales-service annales-import --verifier-seulement
# écart attendu sur une base existante :
#   exercices : colonnes absentes rang
# correctif :
#   ALTER TABLE exercices ADD COLUMN IF NOT EXISTS rang INTEGER;

docker compose exec annales-service annales-import --creer-schema --verifier-seulement

docker compose exec annales-service annales-import \
  --corpus /travail/corpus \
  --referentiel /travail/referentiel/genere/sections \
  --etiquettes /travail/passe-39 --passe passe-39 \
  --protocole /app/config/mesure.yaml
```

Idempotent et rejouable : tout passe dans une transaction, et les trois
contraintes du schéma portent une décision, pas seulement de l'intégrité —
`documents.empreinte` UNIQUE est la déduplication par condensat remontée en
base, `etiquettes` en clé `(question_id, notion_id, passe)` laisse coexister
plusieurs passes du même corpus, et `passes.protocole` en JSONB rattache chaque
mesure à sa configuration.

## Construction

```bash
docker build -f service/Dockerfile -t annales-service .
docker compose -f docker-compose.yml -f service/docker-compose.yml up -d
```

La construction appelle `--help` sur les quatre commandes et sur l'import : si
le paquet est incomplet, elle échoue là, pas en production.
