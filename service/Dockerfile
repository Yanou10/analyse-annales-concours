# Image du service HTTP. Se construit depuis la RACINE du dépôt :
#     docker build -f service/Dockerfile -t annales-service .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SERVICE_RACINE_CODE=/app \
    SERVICE_TRAVAIL=/travail \
    ETAGE0_RACINE=/app \
    ETAGE0_JOURNAL=/travail/journal/journal.jsonl \
    ETAGE0_PROGRAMME=/app/programme/spe777_annexe_1373646.md

# Le référentiel est de la MATIÈRE PRODUITE, pas du code : il vit dans le
# volume. Le figer dans l'image obligerait à reconstruire à chaque notion
# corrigée, et ferait diverger l'image de ce qu'on mesure réellement.
# `ETAGE0_SORTIE` est le dossier parent de `sections/` : c'est par lui que les
# étages 0 et 3 trouvent le référentiel.
ENV SERVICE_REFERENTIEL=/travail/referentiel/genere/sections \
    SERVICE_SONDES=/travail/referentiel/sondes.yaml \
    ETAGE0_SORTIE=/travail/referentiel/genere

WORKDIR /app

COPY pyproject.toml ./
COPY etage0 ./etage0
COPY etage1 ./etage1
COPY etage3 ./etage3
COPY etage4 ./etage4
COPY service ./service
RUN pip install --no-cache-dir '.[service]'

# Configuration et programme officiel : petits, stables, ils voyagent avec
# l'image. Le référentiel, le corpus, le journal et les passes vivent dans le
# volume — l'image ne contient aucune donnée de travail.
COPY profils ./profils
COPY config ./config
COPY spe777_annexe_1373646.md ./programme/spe777_annexe_1373646.md

# La construction ÉCHOUE tout de suite si le paquet est incomplet. C'est le
# défaut qui avait été trouvé sur le paquet précédent : `pip install .`
# réussissait et deux commandes sur quatre n'étaient pas installées. Un
# `--help` par commande le prouve à la construction plutôt qu'en production.
RUN set -eux; \
    for commande in etage0 etage1 etage3 etage4; do \
        "$commande" --help > /dev/null; \
    done; \
    annales-import --help > /dev/null; \
    python -c "import service.main" ; \
    echo "les quatre étages, l'import et le service répondent"

RUN useradd --create-home --uid 1000 annales \
    && mkdir -p /travail \
    && chown -R annales /app /travail
USER annales
VOLUME ["/travail"]

# Aucun EXPOSE : le service est joint par le réseau interne Docker, jamais
# depuis l'extérieur. C'est le reverse proxy qui décide ce qui est publié.
# Pas de `--log-config` : uvicorn n'accepte qu'un fichier .json/.yaml/.ini et
# refuserait /dev/null. C'est `service.journalisation.installer`, appelé à
# l'import de l'application, qui rabat les journaux d'uvicorn sur le format
# JSON — sans quoi la moitié des lignes de `docker logs` n'en serait pas.
CMD ["uvicorn", "service.main:application", "--host", "0.0.0.0", "--port", "8000"]
