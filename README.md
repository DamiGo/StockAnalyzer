# StockAnalyzer

Ce projet contient plusieurs scripts Python permettant d'analyser des actions européennes et un portefeuille personnel. Les résultats sont envoyés par e‑mail via SendGrid.

## Prérequis

- Python 3.8 ou plus récent
- Les librairies Python suivantes :
  - `pandas`
  - `numpy`
  - `yfinance`
  - `curl_cffi`  # pour contourner les limitations d'accès de Yahoo Finance
  - `sendgrid`
  - `schedule`
  - `pyyaml`

Installation rapide :

```bash
pip install pandas numpy yfinance curl_cffi sendgrid schedule pyyaml
```

## Structure du projet

- **`analyse_portfolio.py`** : analyse votre portefeuille défini dans `config.yaml` et génère un rapport HTML envoyé par e‑mail.
- **`analyzer.py`** : recherche des opportunités d'achat sur plusieurs places boursières européennes puis envoie un résumé par e‑mail.
- **`daily_update.py`** : met à jour automatiquement le dépôt (pull Git) puis lance `analyse_portfolio.py` et `analyzer.py`.
- **`template_mail.py`** : contient le modèle HTML utilisé pour formater les e‑mails.
- **`config.yaml`** : configuration du portefeuille, des proxies et informations d'envoi pour `analyse_portfolio.py`. Le fichier contient également un paramètre `use_proxies` permettant de désactiver totalement leur utilisation.
- **`config.json`** : configuration générale (proxies, clé SendGrid, adresses e‑mail) utilisée par `analyzer.py`.

## Utilisation des scripts

1. **Configurer les fichiers de configuration**
   - Remplir `config.yaml` avec vos actions, votre clé SendGrid et les adresses e‑mail expéditrice/destinataire. Vous pouvez renseigner une liste de proxies et définir `use_proxies: false` pour les désactiver.
   - Mettre à jour `config.json` avec votre clé SendGrid (si différente), vos proxies éventuels et les adresses e‑mail.

2. **Lancer l'analyse du portefeuille**

```bash
python analyse_portfolio.py
```

3. **Lancer l'analyse du marché**

```bash
python analyzer.py
```

4. **Lancer la mise à jour quotidienne**

```bash
python daily_update.py
```

Cette dernière commande mettra à jour le dépôt depuis son origine puis exécutera successivement `analyse_portfolio.py` et `analyzer.py`.

## Notes supplémentaires

- `template_mail.py` est une librairie et n'est pas destiné à être exécuté directement.
- Les logs des différents scripts sont généralement enregistrés dans des fichiers `.log` ou affichés sur la sortie standard pour faciliter le débogage.
- Pensez à créer une tâche planifiée (cron ou autre) si vous souhaitez automatiser l'exécution quotidienne de `daily_update.py`.
- En cas de problèmes de rate limit avec Yahoo Finance, le code utilise
  `curl_cffi` pour ouvrir une session qui imite un navigateur Chrome et applique
  un patch (`yfinance_cookie_patch.patch_yfdata_cookie_basic`) pour corriger la
  gestion des cookies dans `yfinance`.

