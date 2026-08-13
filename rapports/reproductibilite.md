# État des lieux — reproductibilité sans Claude Code

*Établi le 2026-08-12, en lecture seule. Aucun fichier de matière modifié.*

**Verdict : non.** La *chaîne de traitement* est reproductible ; l'*état actuel du
référentiel et de l'étalon* ne l'est pas. Quelqu'un qui récupère ce dossier
aujourd'hui peut relancer l'étiquetage et retrouver les mesures ; il ne peut pas
reconstruire `referentiel/genere/` depuis le programme officiel — quatre des dix
opérations qui l'ont amené à son état courant n'existent que dans un dossier
temporaire de session, ou n'existent nulle part.

---

## 1. Ce qui est reproductible — le code versionné

| Paquet | Modules | Sous-commandes | Entrée → sortie |
|---|---|---|---|
| `etage0` | 8 | `segmenter` `construire` `injecter` `etalon` `renvois` `exclusions` | programme officiel → `referentiel/genere/` |
| `etage1` | 2 | `extraire` `verifier` | `*.md` bruts → `corpus/*.json` |
| `etage3` | 3 | `etiqueter` `dispersion` | `corpus/` + référentiel → `etiquettes.json` + mesures |
| `tests` | 6 fichiers | `pytest` | 79 tests, verts |

S'y ajoutent `config/mesure.yaml` (protocole figé, vérifié à l'exécution par
`verifier_protocole` — la passe refuse de démarrer si la configuration diverge),
`profils/informatique-mpi.yaml`, `pyproject.toml`, `Dockerfile`,
`docker-compose.yml`, et le journal `.etage0/journal.jsonl` qui permet de rejouer
une passe hors ligne.

C'est la partie solide, et elle est substantielle : **l'étiquetage complet des
6 fichiers est reproductible d'une seule commande**, protocole vérifié et
signature à l'appui. C'est vérifié, pas supposé : la passe complète a été rejouée
depuis le journal avec une clé API factice et a rendu des résultats identiques
au bit près.

---

## 2. Ce qui ne l'est pas — 1 060 lignes dans un dossier volatile

Douze scripts vivent dans le scratchpad de session
(`…/Temp/claude/…/bc93137a-…/scratchpad/`). Ce dossier est **propre à cette
session et destiné à être supprimé**. Rien ne les sauvegarde.

| Script | Lignes | Ce qu'il a fait | Rejouable ? |
|---|---:|---|---|
| `injecter_corpus.py` | 246 | a créé 8 des 182 notions (confrontation du corpus) | **non — perte franche** |
| `migrer_renvois.py` | 100 | a converti 164 notions aux renvois typés, en récupérant les `voir_slug` perdus depuis le journal | **non — perte franche** |
| `repetition_injection.py` | 116 | répétition de `injecter` sur copie, sans réseau | à promouvoir (garde-fou) |
| `test_contrat.py` | 97 | reproduction de l'échec §4.3 | remplacé par `tests/` — jetable |
| `confrontation2.py` | 89 | recherche d'attestations dans question + corrigé + préambule | **non — méthode non consignée** |
| `confrontation.py` | 86 | harnais de confrontation v1 | superseded par v2 |
| `diagnostic.py` | 81 | cibles mortes, faux positif d'appariement, non-appariés de l'étalon | à promouvoir |
| `reinstruction.py` | 60 | a créé les 2 dernières notions sur l'extraction réparée | **non — perte franche** |
| `analyse_renvois.py` | 59 | mesure de résolution des renvois | recouvert par `etage0 renvois` |
| `reecrire_etalon.py` | 59 | a réécrit 12 identifiants de l'étalon (39 occurrences) | **non — perte franche** |
| `rembobiner_injection.py` | 39 | annulation d'une injection pour la rejouer | à promouvoir (garde-fou) |
| `sonde_large.py` | 28 | élargissement des motifs de sonde | jetable |

Cinq d'entre eux ont **écrit dans la matière** (`referentiel/genere/`,
`referentiel/etalon/`). Leur disparition ne casse rien aujourd'hui, mais elle
rend l'état actuel inexplicable : on ne pourra plus dire *comment* ces
10 notions ont été obtenues, ni rejouer la confrontation sur les 33 sujets
restants avec la même méthode.

---

## 3. Ce qui ne l'est pas — les opérations sans fichier du tout

Plus grave, parce qu'il n'y a rien à sauvegarder : des modifications faites en
`python -c`, en heredoc, ou directement à l'éditeur sur les YAML.

| Opération | Effet sur la matière | Trace restante |
|---|---|---|
| Réécriture n°2 de l'étalon | 8 identifiants, 18 occurrences | aucune |
| Repointage des 2 renvois morts | 2 notions | aucune |
| Correction de coquille `…_sequelle` → `…_sequentiel` | 1 slug | aucune |
| Conversion des 2 renvois de section en renvois de notion | 2 notions | aucune |
| Déplacement de `complexite_pb.etablir_borne_inferieure` | 1 notion | aucune |
| Ventilations de l'étage 4 (par fichier, par section, notions à zéro, top 20, croisement notion × filière) | — | les chiffres, pas leur calcul |
| Calculs du rapport de coûts | — | `rapports/couts.md`, pas le script |

Le dernier point mérite d'être nommé : **il n'existe pas d'étage 4.** Les mesures
sont calculées dans `etage3/cli.py::_rendre_mesures`, et toutes les ventilations
que tu as demandées ont été produites à la volée. Le jour où on veut la même
ventilation sur 39 sujets, elle est à réécrire.

---

## 4. Trois défauts structurels

**a. Aucun dépôt git.** `referentiel/genere/` a été muté dix fois en place sans
historique. Les seules sauvegardes (`sauvegarde-avant-renvois`,
`sauvegarde-etalon`, `sauvegarde-etalon-2`) sont dans le scratchpad, donc
elles-mêmes volatiles. Le `changelog` du `manifest.yaml` enregistre 4 opérations
sur 10 : la migration des renvois, les deux réécritures de l'étalon et les cinq
retouches du §3 n'y figurent pas. C'est exactement le défaut que le registre de
règles a corrigé au niveau de l'unité — une correction silencieuse vaut une
section perdue en silence — mais il subsiste au niveau du dépôt.

**b. Le paquet n'installe que l'étage 0.** `pyproject.toml` déclare
`include = ["etage0*"]` et un seul script `etage0`. Après `pip install .`,
`etage1` et `etage3` **ne sont pas installés** et n'ont pas de point d'entrée :
ils ne fonctionnent qu'en `python -m etage1.cli` depuis le répertoire source. Le
`Dockerfile` ne copie que `COPY etage0 ./etage0` — l'image ne sait ni extraire ni
étiqueter. Un tiers qui suit le README obtient un tiers du pipeline.

**c. La documentation est périmée et partielle.** `README-etage0.md` (113 lignes)
ne couvre que l'étage 0, recommande encore `--fournisseur ollama` (abandonné), et
ne mentionne ni `config/mesure.yaml`, ni la signature de protocole, ni la mesure
de reproductibilité. Aucun document ne donne la **séquence** des commandes. Les
14 dossiers de sortie (`etiquettes-r0a`, `mesure-dA`, `passe-lot3`…) ne sont
documentés nulle part : leurs noms sont le seul indice de ce qu'ils contiennent.

---

## 5. Chiffrage

Sur les 10 opérations qui ont amené `referentiel/genere/` de 164 à 182 notions
et à son état de renvois courant :

- **3** passent par une commande versionnée (`etage0 injecter`) — mais leur
  *contenu* venait de scripts scratchpad ;
- **2** viennent d'un script scratchpad qui écrit directement ;
- **5** n'ont aucune trace exécutable.

Autrement dit : **1 opération sur 10 est intégralement rejouable.** À l'inverse,
sur la chaîne de production (extraire → étiqueter → mesurer), **tout est
rejouable**, y compris hors ligne depuis le journal.

La ligne de partage est nette et instructive : ce qui a été fait *en régime* est
reproductible, ce qui a été fait *en réparation* ne l'est pas. Or c'est la
réparation qui a produit la valeur.

---

## 6. Ce qu'il faudrait promouvoir

Par ordre d'urgence décroissante.

1. **`git init` + premier commit, aujourd'hui.** Sans cela, tout le reste est
   du sable. Coût : une minute.
2. **Copier les 12 scripts du scratchpad dans `outils/`**, avant leur
   suppression. Même sans les nettoyer : un script daté et illisible vaut mieux
   qu'un script disparu.
3. **Corriger le paquet** — `include = ["etage0*", "etage1*", "etage3*"]`, trois
   `project.scripts`, trois `COPY` dans le `Dockerfile`. Coût : cinq minutes,
   et c'est la différence entre « ça marche chez moi » et « ça marche ».
4. **Un `SEQUENCE.md`** de vingt lignes donnant l'ordre des commandes du
   programme officiel jusqu'aux mesures, avec les dossiers de sortie attendus.
5. **Un vrai `etage4`**, extrait de `_rendre_mesures`, avec les ventilations en
   sous-commandes. C'est le seul point qui demande une vraie séance de travail,
   et il devient bloquant au moment de traiter les 39 sujets.
6. **Promouvoir la confrontation en `etage0 confronter`** — c'est la méthode qui
   a produit 10 notions sur 182, et elle devra tourner sur les 33 sujets
   restants. La laisser mourir avec le scratchpad, c'est s'engager à la
   réinventer.

Sont légitimement à usage unique et n'ont pas à être promus :
`test_contrat.py` (couvert par `tests/`), `sonde_large.py`,
`confrontation.py` (v1), `analyse_renvois.py` (recouvert par `etage0 renvois`),
et les deux réécritures d'étalon — une fois les identifiants alignés, elles ne
se rejouent pas.
