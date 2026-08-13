"""Étage 1 — sujets bruts (.md) → exercices et questions structurés.

L'extraction précédente segmentait par expression régulière sur « Question N »
et perdait environ 30 % du texte. Étiqueter sur cette base produirait des
chiffres faux qu'on prendrait pour des défauts du référentiel.
"""

from .extraction import Document, Exercice, Question, extraire, extraire_corpus

__all__ = ["Document", "Exercice", "Question", "extraire", "extraire_corpus"]
