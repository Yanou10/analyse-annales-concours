# Service HTTP — n8n orchestre, Python calcule, MinIO porte la matière

Le service expose les quatre étages. Il ne contient aucune logique métier : il
valide des clés d'objet, descend ce qu'il faut dans un espace jetable, lance la
commande de l'étage, remonte les sorties et détruit l'espace. Une passe lancée
par HTTP est la même qu'une passe lancée à la main.

**Le référentiel n'est pas un préalable.** C'est une donnée d'entrée que
`POST /construire` produit depuis un programme officiel. Plusieurs référentiels
coexistent, chacun identifié par son empreinte. Une instance neuve répond
`"etat": "referentiel_absent"` — c'est un état légitime, pas une panne.

**Tout appel est asynchrone.** Il rend un identifiant tout de suite ; l'état se
lit sur `/taches/{id}`. Un étiquetage dure des minutes : une requête synchrone
expirerait chez l'orchestrateur, et un client qui réessaie relancerait des
appels payants.

Adresse interne : `http://annales-service:8000`. Aucun port publié.

## Les trois seaux

| seau | contient | déposé par |
|---|---|---|
| `programmes` | les programmes officiels (`.md`) | toi |
| `corpus` | les sujets bruts (`.md`) | toi |
| `sorties` | tout ce que la chaîne produit | le service |

Arborescence de `sorties` :

```
referentiels/<empreinte>/sections/*.yaml
referentiels/<empreinte>/{manifest.yaml,exclusions.json,origine.json,sondes.yaml}
corpus/<lot>/*.json
etiquettes/<passe>/{etiquettes.json,passe.json}
confrontations/<lot>__<empreinte>.json
mesures/<passe>/tableau-de-bord.html
```

`sondes.yaml` se dépose à la main sous le préfixe du référentiel : les sondes
se réfèrent aux notions de **ce** référentiel-là.

`passe.json` voyage avec chaque passe — signature, empreinte du référentiel,
protocole complet. Une passe qui ne sait plus contre quoi elle a été mesurée
n'est comparable à rien.

## Endpoints

| méthode | chemin | commande |
|---|---|---|
| `GET` | `/sante` | — |
| `GET` | `/referentiels` | — |
| `POST` | `/construire` | `etage0 construire` **lourde** |
| `POST` | `/extraire` | `etage1 extraire` |
| `POST` | `/confronter` | `etage0 confronter` |
| `POST` | `/etiqueter` | `etage3 etiqueter` **lourde** |
| `POST` | `/mesurer` | `etage4 <sous-commande>` |
| `POST` | `/importer` | `annales-import` |
| `GET` | `/taches/{id}` · `/taches` | — |

### Une chaîne complète

```bash
S=http://annales-service:8000

# 0. état d'une instance neuve
curl -s $S/sante | jq '{etat, referentiels}'

# 1. construire un référentiel depuis un programme officiel
curl -s -X POST $S/construire -H 'content-type: application/json' \
  -d '{"programme":"spe777_annexe_1373646.md"}'
# → l'empreinte apparaît dans le résultat de la tâche
REF=$(curl -s $S/taches/<id> | jq -r .resultat.empreinte)

# 2. extraire les sujets
curl -s -X POST $S/extraire -H 'content-type: application/json' \
  -d '{"sujets":["2024_InfoA.md","2024_InfoC.md"],"lot":"mpi-2024"}'

# 3. confronter (déterministe, aucun appel de modèle)
curl -s -X POST $S/confronter -H 'content-type: application/json' \
  -d "{\"lot\":\"mpi-2024\",\"referentiel\":\"$REF\"}"

# 4. étiqueter
curl -s -X POST $S/etiqueter -H 'content-type: application/json' \
  -d "{\"lot\":\"mpi-2024\",\"referentiel\":\"$REF\",\"passe\":\"p1\",\"batch\":true,\"tranche_lot\":10}"

# 5. mesurer
curl -s -X POST $S/mesurer -H 'content-type: application/json' \
  -d "{\"sous_commande\":\"distribution\",\"passes\":[\"p1\"],\"referentiel\":\"$REF\"}"

curl -s -X POST $S/mesurer -H 'content-type: application/json' \
  -d "{\"sous_commande\":\"dashboard\",\"passes\":[\"p1\"],\"referentiel\":\"$REF\"}"
```

### Suivre une tâche

```bash
until [ "$(curl -s $S/taches/$ID | jq -r .etat)" != "en_cours" ]; do sleep 20; done
curl -s $S/taches/$ID | jq '{etat, code_retour, duree_s, resultat}'
curl -s $S/taches/$ID | jq -r .stderr | tail -40
```

États : `en_attente`, `en_cours`, `fini`, `echec`, `interrompu`. Le dernier
signale une tâche que le redémarrage du service a coupée — jamais une tâche
qu'on croit encore vivante.

## Garanties

- **L'empreinte du référentiel entre dans la signature**, par `--graine`. La
  signature de l'étage 3 ne couvre pas le contenu des notions : sans la graine,
  deux passes menées sur des référentiels différents partageraient leurs clés
  de journal et se réutiliseraient l'une l'autre.
- **Le journal reste local et segmenté par signature** :
  `/travail/journal/<signature>.jsonl`. C'est la reprise sur appels déjà payés,
  elle doit être rapide ; et deux campagnes sur des référentiels différents
  n'ont rien à partager.
- **L'espace de travail est détruit quoi qu'il arrive** — échec de préparation,
  commande en erreur, exception de reversement ou succès. `finally`, pas
  bonne volonté.
- **Rien n'est reversé si la commande a échoué.** Une sortie partielle déposée
  dans le seau se lirait comme un résultat.
- **Une seule tâche lourde à la fois** (construction, étiquetage). Deux passes
  concurrentes paieraient deux fois les mêmes appels : le journal ne
  dédoublonne qu'après la réponse du modèle.
- **La clé ne vient que de l'environnement**, jamais d'un corps de requête, et
  `/sante` n'en dit que la présence.
- **Une clé d'objet n'est pas un chemin.** Elle est validée, puis le chemin
  local obtenu est vérifié après résolution — MinIO accepte parfaitement un
  objet nommé `../../etc/passwd`.
- **Journalisation JSON sur stdout**, uvicorn compris : `docker logs … | jq`.

## Import en base — `POST /importer`

`annales-import` tourne en tâche de fond comme le reste, et se suit par
`/taches/{id}`.

```bash
# contrôle du schéma seul : ni passe ni référentiel requis, rien n'est écrit
curl -s -X POST $S/importer -H 'content-type: application/json' \n     -d '{"verifier_seulement": true}'

# première mise en place : applique service/schema.sql puis contrôle
curl -s -X POST $S/importer -H 'content-type: application/json' \n     -d '{"verifier_seulement": true, "creer_schema": true}'

# import d'une passe
curl -s -X POST $S/importer -H 'content-type: application/json' \n     -d '{"passe":"p1","referentiel":"<empreinte>"}'
```

**`DATABASE_URL` vient de l'environnement du service et n'est jamais acceptée
dans le corps de la requête** — une URL de connexion porte un mot de passe, et
un corps HTTP finit dans les journaux de l'orchestrateur. C'est la même règle
que pour la clé Anthropic. Absente, l'endpoint refuse en 503.

Le service descend de MinIO la passe, son corpus et son référentiel, puis lance
la commande. **Le protocole écrit dans `passes.protocole` vient de
`passe.json`**, pas de l'image : c'est la configuration sous laquelle la passe a
réellement été mesurée. Lui substituer le `config/mesure.yaml` courant ferait
mentir la base au premier changement de protocole.

Une passe sans son `passe.json` est refusée en 409 (`passe_incomplete`) : elle
ne saurait plus dire sous quel protocole elle a été mesurée.

Schéma de référence dans [`schema.sql`](schema.sql). Sur une base antérieure,
un écart est attendu et la commande le nomme :

```
exercices : colonnes absentes rang
ALTER TABLE exercices ADD COLUMN IF NOT EXISTS rang INTEGER;
```

Idempotent et rejouable, tout dans une transaction.

## Construction et déploiement

```bash
docker build -f service/Dockerfile -t annales-service .
docker compose -f docker-compose.yml -f service/docker-compose.yml up -d
```

La construction appelle `--help` sur les quatre étages et sur l'import : si le
paquet est incomplet, elle échoue là, pas en production.

Variables attendues : `ANTHROPIC_API_KEY`, `MINIO_ACCESS_KEY` /
`MINIO_SECRET_KEY` (ou `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`),
`DATABASE_URL`. Les seaux sont créés au besoin.
