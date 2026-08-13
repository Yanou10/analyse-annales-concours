-- Schéma de la base `annales`. Définition de référence : l'import vérifie que
-- la base réelle lui correspond avant d'écrire quoi que ce soit, et refuse en
-- nommant les écarts plutôt que d'échouer au milieu d'un chargement.
--
-- Trois contraintes portent une décision de conception, pas seulement de
-- l'intégrité :

-- 1. `documents.empreinte` est UNIQUE. C'est la déduplication par condensat
--    remontée au niveau de la base : `2024_InfoF`, identique octet pour octet à
--    `2024_InfoC`, aurait été refusé ici sans qu'aucun code ne s'en mêle.
CREATE TABLE IF NOT EXISTS documents (
    id                  TEXT PRIMARY KEY,
    fichier             TEXT        NOT NULL,
    empreinte           TEXT        NOT NULL UNIQUE,
    filiere             TEXT,
    niveau_exercice     INTEGER,
    caracteres_source   INTEGER,
    caracteres_bruit    INTEGER,
    ratio_extraction    NUMERIC,
    importe_le          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exercices (
    id                      TEXT PRIMARY KEY,
    document_id             TEXT        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    titre                   TEXT,
    niveau                  INTEGER,
    filiere                 TEXT,
    preambule               TEXT,
    corrige_non_attribue    TEXT,
    ligne                   INTEGER,
    rang                    INTEGER
);
-- `rang` désambiguïse les 12 exercices qui partagent leur identifiant (quatre
-- titres se répètent dans leur fichier, `suite-des-questions` sept fois dans
-- 2018_InfoU). Sans lui, l'import les écraserait les uns sur les autres.
CREATE INDEX IF NOT EXISTS exercices_document ON exercices(document_id);

CREATE TABLE IF NOT EXISTS questions (
    id                  TEXT PRIMARY KEY,
    exercice_id         TEXT NOT NULL REFERENCES exercices(id) ON DELETE CASCADE,
    numero              TEXT,
    texte               TEXT,
    solution            TEXT,
    figure_manquante    BOOLEAN,
    ligne               INTEGER
);
CREATE INDEX IF NOT EXISTS questions_exercice ON questions(exercice_id);

CREATE TABLE IF NOT EXISTS notions (
    id          TEXT PRIMARY KEY,
    section_id  TEXT NOT NULL,
    libelle     TEXT,
    definition  TEXT
);
CREATE INDEX IF NOT EXISTS notions_section ON notions(section_id);

-- 3. `protocole` est un JSONB : le contenu intégral de `config/mesure.yaml` au
--    moment de la passe. Chaque mesure reste rattachée à sa configuration, et
--    deux passes ne sont comparables que si leurs protocoles le sont.
CREATE TABLE IF NOT EXISTS passes (
    id          TEXT PRIMARY KEY,
    signature   TEXT,
    source      TEXT,
    protocole   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    cree        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Clé primaire (question_id, notion_id, passe) : plusieurs passes du même
--    corpus coexistent sans s'écraser. C'est ce qui permet de comparer deux
--    protocoles — et c'est aussi ce qui rend l'import rejouable.
CREATE TABLE IF NOT EXISTS etiquettes (
    question_id     TEXT NOT NULL,
    notion_id       TEXT NOT NULL,
    passe           TEXT NOT NULL REFERENCES passes(id) ON DELETE CASCADE,
    justification   TEXT,
    statut          TEXT,
    langage         TEXT,
    PRIMARY KEY (question_id, notion_id, passe)
);
CREATE INDEX IF NOT EXISTS etiquettes_notion ON etiquettes(notion_id, passe);
CREATE INDEX IF NOT EXISTS etiquettes_passe  ON etiquettes(passe);
