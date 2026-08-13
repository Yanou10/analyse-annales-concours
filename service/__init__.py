"""Service HTTP qui expose la chaîne aux orchestrateurs.

n8n orchestre, Python calcule. Le service ne contient AUCUNE logique métier :
il valide des chemins, lance les commandes des quatre étages en sous-processus
et rend l'état des tâches. Toute règle de mesure reste là où elle est déjà —
dans `etage0`, `etage1`, `etage3`, `etage4` — pour qu'une passe lancée par HTTP
et une passe lancée à la main soient la même passe.
"""

VERSION = "1.0.0"
