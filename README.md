# Annales — référentiel de notions attribuables

Étiqueter les questions de sujets de concours contre un référentiel de notions
construit depuis le programme officiel, pour produire un **ordre de priorité de
révision** : ce qui tombe le plus, ce qui ne tombe jamais, et où le référentiel
lui-même est à sa limite.

Appliqué ici aux annales d'informatique des ENS (MPI et MP option info,
2017–2025). La chaîne ne connaît rien de l'informatique : elle prend un
programme officiel et un corpus, et vaut pour toute matière qui a les deux.

---

## La chaîne

```mermaid
flowchart TB
    subgraph orch ["Orchestration — VPS"]
        direction LR
        MINIO[("MinIO<br/>programmes · corpus · sorties")]
        N8N["n8n<br/>2 workflows"]
        API["Service HTTP<br/>FastAPI · tâches de fond"]
        PG[("PostgreSQL<br/>annales")]
        MINIO -->|"s3:ObjectCreated"| N8N
        N8N -->|"POST /construire /extraire<br/>/etiqueter /mesurer /importer"| API
        API -->|"descend, exécute, reverse"| MINIO
        API --> PG
    end

    subgraph chaine ["Chaîne de traitement"]
        direction TB
        PROG["Programme officiel<br/>(.md)"]
        REF["Référentiel<br/>182 notions typées"]
        SUJ["Sujets bruts<br/>(.md)"]
        COR["Corpus extrait<br/>338 exercices · 2 199 questions"]
        ETQ["Étiquetage<br/>protocole figé · API Batch"]
        MES["Mesures<br/>ventilations · tableau de bord"]

        PROG -->|"etage0 construire"| REF
        SUJ -->|"etage1 extraire"| COR
        REF --> ETQ
        COR --> ETQ
        ETQ -->|"etage3"| MES
        MES -->|"etage4"| BASE["Base de données"]
        COR -.->|"etage0 confronter"| REF
    end

    orch -.->|"pilote"| chaine
```

Le trait pointillé de `confronter` vers le référentiel est la boucle de retour :
le corpus révèle des notions que le programme ne nomme pas. Dix des 182 notions
viennent de là, admises seulement si attestées dans **au moins deux fichiers
distincts**.

---

## Installation

```bash
git clone git@github.com:Yanou10/annales.git && cd annales
python -m venv .venv && . .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install '.[service,dev]'
cp .env.example .env                               # y mettre la clé Anthropic
pytest -q                                          # 121 tests
```

Quatre commandes sont installées : `etage0`, `etage1`, `etage3`, `etage4`, plus
`annales-import`.

---


## Structure

| dossier | rôle |
|---|---|
| [`etage0/`](etage0/) | programme officiel → référentiel ; registre de règles à sévérité, renvois typés, confrontation au corpus |
| [`etage1/`](etage1/) | sujets bruts → exercices et questions ; segmentation par titres, déduplication par condensat |
| [`etage3/`](etage3/) | étiquetage contre le référentiel ; protocole vérifié, mode Batch |
| [`etage4/`](etage4/) | ventilations et tableau de bord HTML autonome |
| [`service/`](service/) | API HTTP, import PostgreSQL, image Docker |
| [`n8n/`](n8n/) | les deux workflows d'orchestration |
| [`tests/`](tests/) | 121 tests |

Chaque défaut corrigé a laissé un test qui le rejoue. Les commentaires du code
disent *pourquoi* une règle existe, avec le cas qui l'a rendue nécessaire — une
section de programme perdue en silence, 30 % du texte non extrait, un plafond de
compilation de grammaires qui n'apparaît qu'en mode Batch.
