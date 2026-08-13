# outils/ — scripts d'opération, conservés en l'état

Ces scripts ont été écrits au fil de l'eau entre le 10 et le 11 août 2026 dans
un dossier temporaire de session, et recopiés ici **le 12 août 2026 sans être
nettoyés**. Plusieurs contiennent des chemins absolus, des constantes en dur et
des listes de fichiers figées à l'échantillon de six sujets.

Ils sont conservés parce qu'ils sont la seule trace exécutable de la moitié des
opérations qui ont amené `referentiel/genere/` à son état courant. Un script
daté et illisible vaut mieux qu'un script disparu — mais aucun n'est une
interface : **ne pas les rejouer sans les relire**.

## Ce qui a été promu et ne doit plus être joué d'ici

| Script | Remplacé par |
|---|---|
| `confrontation.py`, `confrontation2.py`, `sonde_large.py`, `reinstruction.py` | `etage0 confronter` + `referentiel/sondes.yaml` |
| `analyse_renvois.py` | `etage0 renvois` |
| `test_contrat.py` | `tests/test_contrat_section_4_3.py` |

## Ce qui reste sans équivalent versionné

| Script | Ce qu'il a fait | Rejouable ? |
|---|---|---|
| `migrer_renvois.py` | migration des 164 notions vers les renvois typés, `voir_slug` récupérés depuis le journal | non — migration à sens unique, déjà appliquée |
| `injecter_corpus.py` | rédaction et injection de 8 notions issues de la confrontation | non — la rédaction est humaine par construction |
| `reecrire_etalon.py` | alignement de 12 identifiants de l'étalon | non — déjà appliqué |
| `rembobiner_injection.py` | annulation d'une injection pour la rejouer | garde-fou, à relire avant usage |
| `repetition_injection.py` | répétition d'`injecter` sur copie, sans réseau | garde-fou, utile avant toute injection |
| `diagnostic.py` | cibles mortes, faux positif d'appariement, non-appariés de l'étalon | oui, mais chemins en dur |

## Sauvegardes

`sauvegarde-avant-renvois/`, `sauvegarde-etalon/`, `sauvegarde-etalon-2/` sont
des copies de `referentiel/` prises avant trois opérations destructrices. Elles
étaient elles aussi dans le dossier temporaire.
