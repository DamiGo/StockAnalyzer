#!/usr/bin/env python3
"""Lance l'analyse d'une action passée en argument et affiche le détail des indicateurs."""

import sys
import analyzer


def main():
    if len(sys.argv) < 2:
        print("Usage: python evaluate_stock.py <TICKER>")
        sys.exit(1)

    ticker = sys.argv[1]

    # Désactiver l'utilisation des proxies pour une exécution simple
    analyzer.USE_PROXIES = False

    analyse = analyzer.AnalyseAction(ticker)
    resultat = analyse.analyser()

    if resultat is None:
        print(f"Analyse impossible pour {ticker}")
        sys.exit(1)

    # Affichage structuré des résultats
    print(f"Résultats pour {ticker}:")
    for cle, valeur in resultat.items():
        if cle == "indicateurs":
            print("Indicateurs:")
            for nom, val in valeur.items():
                print(f"  - {nom}: {val}")
        else:
            print(f"{cle}: {val}")


if __name__ == "__main__":
    main()
