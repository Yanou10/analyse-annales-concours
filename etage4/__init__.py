"""Étage 4 — les mesures.

Séparé de l'étage 3 parce qu'une ventilation produite à la volée dans le code
d'étiquetage n'est pas rejouable : sur 3 300 questions, chaque question posée
aux chiffres demanderait de réécrire le calcul. Ici les mesures sont des
sous-commandes, elles lisent un `etiquettes.json` déjà produit, et elles
n'appellent aucun service.
"""
