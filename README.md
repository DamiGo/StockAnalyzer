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
- **`config.yaml`** : configuration du portefeuille, des proxies et informations d'envoi pour `analyse_portfolio.py`. Le fichier contient également un paramètre `use_proxies` pour désactiver les proxies, une section `thresholds` (incluant `rsi_periods` pour les périodes du RSI) pour ajuster les seuils techniques, `signal_weights` pour pondérer l'importance de chaque signal dans `analyzer.py` et `stop_loss_percent` pour définir la perte maximale acceptable.
- **`config.json`** : configuration générale (proxies, clé SendGrid, adresses e‑mail) utilisée par `analyzer.py`.

## Indicateurs boursiers utilisés

Le script `analyzer.py` scanne les principales places boursières européennes en
calculant plusieurs indicateurs. Chacun d'eux génère un signal booléen qui peut
être pondéré dans le fichier `config.yaml` (section `signal_weights`).

- **MACD** : croisement haussier datant de moins de trois jours et validé par
  une tendance générale positive du titre.
- **MM_20_50** : moyenne mobile à 20 jours supérieure à celle à 50 jours.
- **MM_50_200** : moyenne mobile à 50 jours supérieure à celle à 200 jours.
- **RSI** : indicateur calculé sur deux périodes distinctes (par défaut 5 et 14)
  et compris entre `rsi_lower` et `rsi_upper`.
- **Tendance** : orientation haussière de la moyenne mobile 20 jours sur les
  cinq derniers jours.
- **Bollinger** : confirmation d'un rebond depuis la bande inférieure
  (paramètre `bollinger_threshold`).
- **PEG** : ratio Price/Earnings to Growth inférieur à `peg_max`.
- **PriceBook** : ratio Price to Book inférieur à 1,5.
- **ROE** : Return on Equity supérieur à 10 %.
- **Volume** : volumes supérieurs à la moyenne des 10 derniers jours.
- **Momentum** : accélération haussière de la tendance.
- **Breakout** : clôture au-dessus de la résistance récente.
- **BougiesVertes** : au moins trois bougies vertes sur les quatre derniers jours.

Le score d'opportunité est calculé en additionnant les poids des signaux positifs
et en divisant le total par la somme de tous les poids. Les valeurs par défaut
dans `config.yaml` sont :

```yaml
signal_weights:
  MACD: 1.0
  MM_20_50: 1.0
  MM_50_200: 1.0
  RSI: 1.0
  Tendance: 1.0
  Bollinger: 1.0
  PEG: 1.0
  PriceBook: 1.0
  ROE: 1.0
  Volume: 1.0
  Momentum: 1.0
  Breakout: 1.0
  BougiesVertes: 1.0
```

Une action est retenue lorsque son score dépasse `min_opportunity_score`, ce qui
permet de privilégier certains indicateurs en ajustant leurs poids.

## Utilisation des scripts

1. **Configurer les fichiers de configuration**
   - Remplir `config.yaml` avec vos actions, votre clé SendGrid et les adresses e‑mail expéditrice/destinataire. Vous pouvez renseigner une liste de proxies et définir `use_proxies: false` pour les désactiver. Les sections `thresholds` (dont `rsi_periods` pour le RSI) et `signal_weights` permettent respectivement d'ajuster les seuils techniques et la pondération de chaque signal pris en compte par `analyzer.py`. Le paramètre `stop_loss_percent` sert à définir le pourcentage de perte acceptable pour le stop loss.
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

