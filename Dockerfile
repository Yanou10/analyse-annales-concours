FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ETAGE0_RACINE=/app

WORKDIR /app

COPY pyproject.toml ./
COPY etage0 ./etage0
COPY etage1 ./etage1
COPY etage3 ./etage3
COPY etage4 ./etage4
RUN pip install --no-cache-dir .

# Le programme, les profils et les sorties sont montés en volume : l'image ne
# contient aucune donnée de matière, pour rester réutilisable telle quelle.
# `config/` fait exception : le protocole de mesure DOIT voyager avec l'image,
# sinon une passe peut tourner sans lui.
COPY profils ./profils
COPY config ./config

RUN useradd --create-home --uid 1000 etage0 && chown -R etage0 /app
USER etage0

ENTRYPOINT ["etage0"]
CMD ["--help"]
