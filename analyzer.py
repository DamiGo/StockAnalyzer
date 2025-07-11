# analyse_sbf120.py

import os
import yfinance as yf
import pandas as pd
import numpy as np
import concurrent.futures
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, HtmlContent
import yaml
import random
from datetime import datetime
import logging
import sys
from template_mail import RapportHTML
# Utilisation de curl_cffi pour contourner les limitations de Yahoo Finance
# cf. https://github.com/ranaroussi/yfinance/issues/2422#issuecomment-2840774505
from curl_cffi import requests
# Patch to ensure cookies are handled correctly when using curl_cffi
import yfinance_cookie_patch

# Configuration du logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler('sbf120_analysis.log')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False

# Chargement de la configuration externe
CONFIG_FILE = 'config.yaml'
try:
    with open(CONFIG_FILE, 'r') as f:
        cfg = yaml.safe_load(f)
except Exception as e:
    logger.error(f"Erreur lors du chargement du fichier de configuration: {e}")
    cfg = {}

# Liste de proxies HTTP pour contourner d'éventuels blocages
PROXIES = cfg.get('proxies', [
    "http://proxy1.example.com:8080",
    "http://proxy2.example.com:8080",
    "http://proxy3.example.com:8080",
])
# Possibilité de désactiver complètement l'utilisation des proxies
USE_PROXIES = cfg.get('use_proxies', True)

# Session HTTP global impersonant Chrome pour contourner les blocages
SESSION = requests.Session(impersonate="chrome")
yfinance_cookie_patch.patch_yfdata_cookie_basic()


def set_random_proxy():
    """Choisit un proxy aléatoirement et le définit pour les requêtes"""
    if not USE_PROXIES:
        # Remove any proxy environment variables that might be set globally
        for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            os.environ.pop(var, None)
        SESSION.proxies.clear()
        return None

    proxy = random.choice(PROXIES)
    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    # Mise à jour de la session globale
    SESSION.proxies.update({"http": proxy, "https": proxy})
    return proxy

# Configuration SendGrid et emails
email_cfg = cfg.get('email', {}) if isinstance(cfg, dict) else {}
SENDGRID_API_KEY = email_cfg.get('api_key', 'xxx')
FROM_EMAIL = email_cfg.get('from', 'xxx')
TO_EMAIL = email_cfg.get('to', 'xxx')

# Chargement des seuils d'analyse
threshold_cfg = cfg.get('thresholds', {}) if isinstance(cfg, dict) else {}
RSI_LOWER = threshold_cfg.get('rsi_lower', 30)
RSI_UPPER = threshold_cfg.get('rsi_upper', 70)
MM_NEUTRAL_RATIO = threshold_cfg.get('mm_neutral_ratio', 0.02)
BOLLINGER_THRESHOLD = threshold_cfg.get('bollinger_threshold', 0.05)
PEG_MAX = threshold_cfg.get('peg_max', 1)
MIN_OPPORTUNITY_SCORE = threshold_cfg.get('min_opportunity_score', 0.5)

class IndicateursBoursiers:
    @staticmethod
    def calculer_rsi(prix, periode=14):
        """Calcule le RSI pour une série de prix"""
        variations = prix.pct_change()
        gains = variations.clip(lower=0)
        pertes = -variations.clip(upper=0)
        avg_gain = gains.rolling(window=periode, min_periods=1).mean()
        avg_perte = pertes.rolling(window=periode, min_periods=1).mean()
        rs = avg_gain / avg_perte
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculer_macd(prix, periode_courte=12, periode_longue=26, signal_periode=9):
        """Calcule le MACD et sa ligne de signal"""
        exp_courte = prix.ewm(span=periode_courte, adjust=False).mean()
        exp_longue = prix.ewm(span=periode_longue, adjust=False).mean()
        macd = exp_courte - exp_longue
        signal = macd.ewm(span=signal_periode, adjust=False).mean()
        return macd, signal

    @staticmethod
    def calculer_moyennes_mobiles(prix, periodes=(20, 50, 200)):
        """Calcule les moyennes mobiles pour les périodes spécifiées"""
        return {p: prix.rolling(window=p, min_periods=1).mean() for p in periodes}

    @staticmethod
    def calculer_bollinger_bands(prix, periode=20, ecart_type=2):
        """Calcule les bandes de Bollinger pour une série de prix"""
        moyenne_mobile = prix.rolling(window=periode).mean()
        std = prix.rolling(window=periode).std()
        bande_sup = moyenne_mobile + (std * ecart_type)
        bande_inf = moyenne_mobile - (std * ecart_type)
        return moyenne_mobile, bande_sup, bande_inf

    @staticmethod
    def calculer_ratio_peg(ticker):
        """Calcule le ratio PEG (Price/Earnings to Growth) pour un ticker avec gestion améliorée des erreurs"""
        try:
            proxy = set_random_proxy()
            if proxy:
                logger.info(f"Proxy utilisé pour {ticker}: {proxy}")
            stock = yf.Ticker(ticker, session=SESSION)
            # Récupérer les données financières
            info = stock.info

            # Vérifier si les données nécessaires sont disponibles
            if 'forwardPE' not in info:
                logger.warning(f"Données forwardPE non disponibles pour {ticker}")
                return None

            pe = info.get('forwardPE')

            # Essayer plusieurs sources pour la croissance des bénéfices
            growth = None

            # Option 1: utiliser earningsGrowth s'il existe
            if 'earningsGrowth' in info and info['earningsGrowth'] is not None:
                growth = info['earningsGrowth'] * 100  # Convertir en pourcentage

            # Option 2: calculer à partir de trailingEps et forwardEps
            elif 'trailingEps' in info and 'forwardEps' in info:
                trailing_eps = info.get('trailingEps')
                forward_eps = info.get('forwardEps')
                if trailing_eps and forward_eps and trailing_eps > 0:
                    # Calculer la croissance des bénéfices manuellement
                    growth = ((forward_eps - trailing_eps) / trailing_eps) * 100

            # Option 3: utiliser d'autres métriques de croissance si disponibles
            elif 'revenueGrowth' in info and info['revenueGrowth'] is not None:
                # Utiliser la croissance des revenus comme approximation
                growth = info['revenueGrowth'] * 100
                logger.info(f"Utilisation de revenueGrowth au lieu de earningsGrowth pour {ticker}")

            # Si aucune donnée de croissance n'est disponible ou si la croissance est négative/nulle
            if growth is None or growth <= 0:
                logger.warning(f"Données de croissance non disponibles ou négatives pour {ticker}")
                return None

            peg = pe / growth
            return peg
        except Exception as e:
            logger.error(f"Erreur lors du calcul du ratio PEG pour {ticker}: {str(e)}")
            return None

    @staticmethod
    def calculer_price_to_book(ticker):
        """Récupère le ratio Price to Book pour un ticker"""
        try:
            proxy = set_random_proxy()
            if proxy:
                logger.info(f"Proxy utilisé pour {ticker}: {proxy}")
            stock = yf.Ticker(ticker, session=SESSION)
            info = stock.info

            pb = info.get('priceToBook')
            if pb is None:
                logger.warning(f"Donnée priceToBook non disponible pour {ticker}")
            return pb
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du Price to Book pour {ticker}: {e}")
            return None

    @staticmethod
    def calculer_ro_e(ticker):
        """Récupère le Return on Equity (en pourcentage) pour un ticker"""
        try:
            proxy = set_random_proxy()
            if proxy:
                logger.info(f"Proxy utilisé pour {ticker}: {proxy}")
            stock = yf.Ticker(ticker, session=SESSION)
            info = stock.info

            roe = info.get('returnOnEquity')
            if roe is None:
                logger.warning(f"Donnée returnOnEquity non disponible pour {ticker}")
                return None
            return roe * 100  # convertir en pourcentage
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du ROE pour {ticker}: {e}")
            return None

class AnalyseAction:
    def __init__(self, ticker):
        self.ticker = ticker
        self.indicateurs = IndicateursBoursiers()

    def _telecharger_donnees(self):
        """Télécharge les données historiques de l'action"""
        try:
            proxy = set_random_proxy()
            if proxy:
                logger.info(f"Proxy utilisé pour {self.ticker}: {proxy}")
            action = yf.Ticker(self.ticker, session=SESSION)
            historique = action.history(period='1y')
            if historique.empty:
                logger.warning(f"Aucune donnée récupérée pour {self.ticker}")
            else:
                logger.info(f"{len(historique)} lignes téléchargées pour {self.ticker}")
            return historique
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement des données pour {self.ticker}: {e}", exc_info=True)
            return None

    def calculer_prix_achat_cible(self, historique, mm):
        """Calcule le prix d'achat cible en fonction des moyennes mobiles"""
        try:
            dernier_prix = historique['Close'].iloc[-1]
            mm20 = mm[20].iloc[-1]
            mm50 = mm[50].iloc[-1]

            if np.isnan(mm20) or np.isnan(mm50):
                logger.warning(f"Moyennes mobiles NaN pour {self.ticker}")
                return None

            zone_neutre = (mm20 + mm50) / 2
            volatilite = historique['Close'].tail(20).std()

            seuil_haut = mm20 * (1 + MM_NEUTRAL_RATIO)
            seuil_bas = mm20 * (1 - MM_NEUTRAL_RATIO)

            if dernier_prix > seuil_haut:
                prix_achat = min(dernier_prix * (1 - MM_NEUTRAL_RATIO), zone_neutre)
            elif seuil_bas <= dernier_prix <= seuil_haut:
                prix_achat = dernier_prix
            else:
                prix_achat = max(dernier_prix * (1 - MM_NEUTRAL_RATIO), zone_neutre - volatilite)

            if prix_achat <= 0 or np.isnan(prix_achat):
                logger.warning(f"Prix d'achat invalide pour {self.ticker}")
                return None

            return prix_achat

        except Exception as e:
            logger.error(f"Erreur dans le calcul du prix d'achat cible pour {self.ticker}: {e}")
            return None

    def calculer_prix_vente_cible(self, historique):
        """Calcule le prix cible de vente basé sur les tendances avec validation"""
        try:
            dernier_prix = historique['Close'].iloc[-1]

            # Vérification des données suffisantes pour les moyennes mobiles
            if len(historique) < 252:  # Un an de trading
                logger.warning(f"Données insuffisantes pour {self.ticker}")
                return None

            tendance_3m = historique['Close'].tail(90).mean()
            tendance_6m = historique['Close'].tail(180).mean()
            tendance_12m = historique['Close'].tail(252).mean()

            # Vérification des NaN dans les tendances
            if np.isnan(tendance_3m) or np.isnan(tendance_6m) or np.isnan(tendance_12m):
                logger.warning(f"Tendances NaN pour {self.ticker}")
                return None

            prix_cible = (tendance_3m * 0.5 + tendance_6m * 0.3 + tendance_12m * 0.2)

            # Calcul de la volatilité sur les 30 derniers jours pour plus de stabilité
            volatilite = historique['Close'].tail(30).pct_change().std()
            if np.isnan(volatilite):
                logger.warning(f"Volatilité NaN pour {self.ticker}")
                return None

            prix_final = prix_cible * (1 + volatilite)

            # Vérification finale du prix cible
            if prix_final <= dernier_prix:
                logger.warning(f"Prix cible inférieur au prix actuel pour {self.ticker}")
                return None

            return prix_final

        except Exception as e:
            logger.error(f"Erreur dans le calcul du prix de vente cible pour {self.ticker}: {e}")
            return None

    def analyser(self):
        """Analyse complète d'une action avec indicateurs supplémentaires"""
        # Liste des tickers pour lesquels on ne calcule pas le ratio PEG
        TICKERS_SANS_PEG = ["FDJ.PA", "NOKIA.HE", "ABI.BR"]

        try:
            # Récupération des données historiques
            historique = self._telecharger_donnees()
            if historique is None or len(historique) < 100:
                logger.warning(f"Données insuffisantes pour {self.ticker}")
                return None

            prix_cloture = historique['Close']
            dernier_prix = prix_cloture.iloc[-1]

            # Calcul des indicateurs techniques de base
            rsi = self.indicateurs.calculer_rsi(prix_cloture).iloc[-1]
            macd, signal = self.indicateurs.calculer_macd(prix_cloture)
            mm = self.indicateurs.calculer_moyennes_mobiles(prix_cloture)

            # Calcul des bandes de Bollinger
            mm_bollinger, bande_sup, bande_inf = self.indicateurs.calculer_bollinger_bands(prix_cloture)

            # Calcul du ratio PEG (en évitant certains tickers problématiques)
            if self.ticker in TICKERS_SANS_PEG:
                ratio_peg = None
                logger.info(f"Calcul du PEG ignoré pour {self.ticker} (dans liste d'exclusion)")
            else:
                try:
                    ratio_peg = self.indicateurs.calculer_ratio_peg(self.ticker)
                except Exception as e:
                    logger.warning(f"Erreur lors du calcul du ratio PEG pour {self.ticker}: {e}")
                    ratio_peg = None

            # Récupération d'indicateurs fondamentaux complémentaires
            price_to_book = self.indicateurs.calculer_price_to_book(self.ticker)
            roe = self.indicateurs.calculer_ro_e(self.ticker)

            # Calcul des prix cibles
            prix_achat_cible = self.calculer_prix_achat_cible(historique, mm)
            prix_vente_cible = self.calculer_prix_vente_cible(historique)

            # Vérification des prix cibles
            if prix_achat_cible is None or prix_vente_cible is None:
                logger.info(f"Prix cibles non calculables pour {self.ticker}")
                return None

            # Calcul du gain potentiel
            gain_potentiel = ((prix_vente_cible - prix_achat_cible) / prix_achat_cible) * 100

            # Analyse des signaux techniques avec gestion d'erreurs
            try:
                signaux = self._analyser_signaux(
                    macd, signal, mm, rsi, prix_cloture,
                    bande_inf, bande_sup, ratio_peg,
                    price_to_book, roe
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'analyse des signaux pour {self.ticker}: {e}")
                # Créer un dictionnaire de signaux par défaut en cas d'erreur
                signaux = {
                    'MACD': False, 'MM_20_50': False, 'MM_50_200': False,
                    'RSI': False, 'Tendance': False, 'Bollinger': False,
                    'PEG': False, 'PriceBook': False, 'ROE': False
                }

            # Vérification de la présence de tous les signaux attendus
            expected_signals = {
                'MACD', 'MM_20_50', 'MM_50_200', 'RSI',
                'Tendance', 'Bollinger', 'PEG',
                'PriceBook', 'ROE'
            }
            for signal_name in expected_signals:
                if signal_name not in signaux:
                    logger.warning(f"Signal manquant: {signal_name} pour {self.ticker}")
                    signaux[signal_name] = False

            # Calcul du score d'opportunité
            nombre_total_signaux = len(expected_signals)
            signaux_positifs = sum(1 for v in signaux.values() if v)
            score_opportunite = signaux_positifs / nombre_total_signaux

            # Log du score pour debug
            logger.info(f"Score d'opportunité pour {self.ticker}: {score_opportunite} ({signaux_positifs}/{nombre_total_signaux})")

            # Filtrage des opportunités intéressantes
            if score_opportunite <= MIN_OPPORTUNITY_SCORE or gain_potentiel <= 0:
                logger.info(f"Score trop faible ou gain insuffisant pour {self.ticker}: score={score_opportunite}, gain={gain_potentiel}%")
                return None

            # Création du résultat avec les indicateurs de base
            try:
                resultat = self._formater_resultat(
                    dernier_prix, prix_achat_cible, prix_vente_cible, gain_potentiel,
                    score_opportunite, rsi, signaux
                )
            except Exception as e:
                logger.error(f"Erreur lors du formatage des résultats pour {self.ticker}: {e}")
                return None

            # Ajout des indicateurs supplémentaires si le résultat existe
            if resultat:
                # Ajout du ratio PEG s'il a pu être calculé
                if ratio_peg is not None:
                    resultat['ratio_peg'] = round(ratio_peg, 2)
                else:
                    resultat['ratio_peg'] = None

                # Ajout du Price to Book et du ROE
                resultat['price_to_book'] = round(price_to_book, 2) if price_to_book is not None else None
                resultat['roe'] = round(roe, 1) if roe is not None else None

                # Calcul et ajout de la position dans les bandes de Bollinger
                try:
                    resultat['bollinger_position'] = self._calculer_position_bollinger(
                        dernier_prix, bande_inf.iloc[-1], bande_sup.iloc[-1]
                    )
                except Exception as e:
                    logger.warning(f"Erreur lors du calcul de la position Bollinger pour {self.ticker}: {e}")
                    resultat['bollinger_position'] = None

                # Ajout d'informations supplémentaires utiles
                resultat['volatilite'] = round(historique['Close'].tail(30).pct_change().std() * 100, 2)
                resultat['volume_moyen'] = int(historique['Volume'].tail(30).mean()) if 'Volume' in historique else None

            # Retour du résultat final
            return resultat

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse de {self.ticker}: {e}", exc_info=True)
            return None

    def _analyser_signaux(
        self, macd, signal, mm, rsi, prix_cloture,
        bande_inf, bande_sup, ratio_peg, price_to_book, roe
    ):
        """Analyse les signaux techniques avec les indicateurs supplémentaires"""
        try:
            # Signaux existants
            # Vérifier si nous avons suffisamment de données pour calculer la tendance
            if len(mm[20]) < 5:
                logger.warning(f"Pas assez de données de tendance pour {self.ticker}")
                tendance = False
            else:
                tendance = bool(mm[20].iloc[-1] > mm[20].iloc[-5])

            # Vérifier tous les signaux et les convertir explicitement en booléens
            macd_signal = bool(macd.iloc[-1] > signal.iloc[-1])
            mm_20_50 = bool(mm[20].iloc[-1] > mm[50].iloc[-1])
            mm_50_200 = bool(mm[50].iloc[-1] > mm[200].iloc[-1])
            rsi_ok = bool(RSI_LOWER < rsi < RSI_UPPER)

            # Nouveaux signaux
            # Signal Bollinger : prix proche de la bande inférieure (potentiel d'achat)
            dernier_prix = prix_cloture.iloc[-1]
            if np.isnan(bande_inf.iloc[-1]):
                bollinger_signal = False
            else:
                # Signal positif si le prix est proche de la bande inférieure
                bollinger_signal = bool(dernier_prix < (bande_inf.iloc[-1] * (1 + BOLLINGER_THRESHOLD)))

            # Signal PEG : ratio PEG inférieur à 1 est généralement considéré comme bon
            if ratio_peg is None:
                peg_signal = False
            else:
                peg_signal = bool(0 < ratio_peg < PEG_MAX)

            # Signal Price to Book : valeur inférieure à 1.5 considérée comme intéressante
            if price_to_book is None:
                pb_signal = False
            else:
                pb_signal = bool(price_to_book < 1.5)

            # Signal ROE : supérieur à 10 %
            if roe is None:
                roe_signal = False
            else:
                roe_signal = bool(roe > 10)

            # Créer le dictionnaire de signaux avec des booléens explicites
            signaux = {
                'MACD': macd_signal,
                'MM_20_50': mm_20_50,
                'MM_50_200': mm_50_200,
                'RSI': rsi_ok,
                'Tendance': tendance,
                'Bollinger': bollinger_signal,
                'PEG': peg_signal,
                'PriceBook': pb_signal,
                'ROE': roe_signal,
            }

            # Journaliser les signaux pour debug
            logger.info(f"Signaux pour {self.ticker}: {signaux}")

            return signaux
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse des signaux pour {self.ticker}: {e}")
            # En cas d'erreur, retourner tous les signaux à False
            return {
                'MACD': False,
                'MM_20_50': False,
                'MM_50_200': False,
                'RSI': False,
                'Tendance': False,
                'Bollinger': False,
                'PEG': False,
                'PriceBook': False,
                'ROE': False
            }
    @staticmethod
    def obtenir_nom_entreprise(ticker):
        """Récupère le nom complet de l'entreprise à partir du ticker"""
        try:
            proxy = set_random_proxy()
            if proxy:
                logger.info(f"Proxy utilisé pour {ticker}: {proxy}")
            action = yf.Ticker(ticker, session=SESSION)
            info = action.info
            if 'longName' in info:
                return info['longName']
            elif 'shortName' in info:
                return info['shortName']
            else:
                return ticker  # Retourne le ticker si le nom n'est pas disponible
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du nom pour {ticker}: {e}")
            return ticker  # Retourne le ticker en cas d'erreur

    @staticmethod
    def generer_lien_cotation(ticker):
        """Génère un lien vers la page Yahoo Finance pour le ticker"""
        # Encodage du ticker pour l'URL si nécessaire
        import urllib.parse
        ticker_encode = urllib.parse.quote(ticker)
        return f"https://finance.yahoo.com/quote/{ticker_encode}"

    def _formater_resultat(self, prix_actuel, prix_achat_cible, prix_vente_cible, gain_potentiel,
                          score_opportunite, rsi, signaux):
        """Formate le résultat de l'analyse avec validation des données"""

        # Vérification des valeurs numériques
        if (not isinstance(prix_actuel, (int, float)) or
            not isinstance(prix_achat_cible, (int, float)) or
            not isinstance(prix_vente_cible, (int, float)) or
            not isinstance(gain_potentiel, (int, float)) or
            not isinstance(score_opportunite, (int, float)) or
            not isinstance(rsi, (int, float))):
            logger.warning(f"Valeurs non numériques détectées pour {self.ticker}")
            return None

        # Vérification des NaN
        if (np.isnan(prix_actuel) or np.isnan(prix_achat_cible) or
            np.isnan(prix_vente_cible) or np.isnan(gain_potentiel) or
            np.isnan(score_opportunite) or np.isnan(rsi)):
            logger.warning(f"Valeurs NaN détectées pour {self.ticker}")
            return None

        # Vérification des valeurs négatives ou nulles
        if prix_actuel <= 0 or prix_achat_cible <= 0 or prix_vente_cible <= 0:
            logger.warning(f"Prix négatifs ou nuls détectés pour {self.ticker}")
            return None

        # Vérification de la cohérence des prix
        if prix_vente_cible < prix_achat_cible:
            logger.warning(f"Prix de vente inférieur au prix d'achat pour {self.ticker}")
            return None

        # Vérification de la plage du RSI (0-100)
        if rsi < 0 or rsi > 100:
            logger.warning(f"RSI hors plage pour {self.ticker}: {rsi}")
            return None

        # Vérification du score d'opportunité (0-1)
        if score_opportunite < 0 or score_opportunite > 1:
            logger.warning(f"Score d'opportunité hors plage pour {self.ticker}: {score_opportunite}")
            return None

        # Vérification du gain potentiel
        if gain_potentiel <= 0 or gain_potentiel > 200:  # limite arbitraire de 200%
            logger.warning(f"Gain potentiel suspect pour {self.ticker}: {gain_potentiel}%")
            return None

        # Obtenir le nom et le lien
        nom_entreprise = AnalyseAction.obtenir_nom_entreprise(self.ticker)
        lien_cotation = AnalyseAction.generer_lien_cotation(self.ticker)

        # Si toutes les vérifications sont passées, renvoyer le résultat
        return {
            'ticker': self.ticker,
            'nom': nom_entreprise,
            'lien_cotation': lien_cotation,
            'prix_actuel': round(prix_actuel, 2),
            'prix_achat_cible': round(prix_achat_cible, 2),
            'prix_vente_cible': round(prix_vente_cible, 2),
            'gain_potentiel': round(gain_potentiel, 2),
            'score_opportunite': round(score_opportunite, 3),
            'rsi': round(rsi, 1),
            'signaux': ', '.join([k for k, v in signaux.items() if v])
        }

    def _calculer_position_bollinger(self, prix, bande_inf, bande_sup):
        """Calcule la position relative du prix par rapport aux bandes de Bollinger (0-100%)"""
        try:
            if np.isnan(bande_inf) or np.isnan(bande_sup) or bande_sup <= bande_inf:
                return None

            # Position en pourcentage (0% = bande inf, 100% = bande sup)
            position = (prix - bande_inf) / (bande_sup - bande_inf) * 100
            return round(position, 2)
        except Exception as e:
            logger.error(f"Erreur lors du calcul de la position Bollinger: {e}")
            return None

def analyse_sbf_120():
    """Analyse de toutes les actions du SBF 120 en parallèle avec validation des résultats"""

    tickers_europe = [
        # SBF 120 (France) - votre liste actuelle
        "AC.PA", "ADP.PA", "AF.PA", "AI.PA", "AIR.PA", "ALO.PA", "ATE.PA", "AMUN.PA",
        "APAM.AS", "MT.AS", "ARG.PA", "AKE.PA", "ATO.PA", "CS.PA", "0RSP.L", "BEN.PA",
        "BB.PA", "BIM.PA", "BNP.PA", "BOL.PA", "EN.PA", "BVI.PA", "CAP.PA", "CARM.PA",
        "CA.PA", "CLARI.PA", "COFA.PA", "COV.PA", "ACA.PA", "BN.PA", "AM.PA", "DSY.PA",
        "DBG.PA", "EDEN.PA", "FGR.PA", "ELIOR.PA", "ELIS.PA", "EMEIS.PA", "ENGI.PA",
        "ERA.PA", "EL.PA", "ES.PA", "RF.PA", "ERF.PA", "ENX.PA", "FDJ.PA", "FRVIA.PA",
        "GFC.PA", "GET.PA", "GTT.PA", "RMS.PA", "ICAD.PA", "IDL.PA", "NK.PA", "ITP.PA",
        "IPN.PA", "IPS.PA", "DEC.PA", "KER.PA", "LI.PA", "OR.PA", "LR.PA", "MC.PA",
        "MAU.PA", "MEDCL.PA", "MERY.PA", "MRN.PA", "MMT.PA", "ML.PA", "NEOEN.PA",
        "NEX.PA", "NXI.PA", "OPM.PA", "ORA.PA", "RI.PA", "PLNW.PA", "PLX.PA", "PUB.PA",
        "RCO.PA", "RNO.PA", "RXL.PA", "RBT.PA", "RUI.PA", "SK.PA", "SAF.PA", "SGO.PA",
        "SAN.PA", "DIM.PA", "SU.PA", "SCR.PA", "SESG.PA", "GLE.PA", "SW.PA", "SOI.PA",
        "SOLB.BR", "SOP.PA", "SPIE.PA", "STLAP.PA", "STMPA.PA", "TE.PA", "TEP.PA", "TFI.PA",
        "HO.PA", "TTE.PA", "TRI.PA", "UBI.PA", "URW.PA", "FR.PA", "VK.PA", "VLA.PA",
        "VIE.PA", "VRLA.PA", "VCT.PA", "DG.PA", "VIRP.PA", "VIRI.PA", "VIV.PA", "VU.PA",
        "MF.PA", "WLN.PA",

        # Allemagne (DAX)
        "ADS.DE", "ALV.DE", "BAYN.DE", "BMW.DE", "MBG.DE", "DBK.DE", "DTE.DE",
        "EOAN.DE", "SAP.DE", "SIE.DE", "VOW3.DE", "DHL.DE", "HEN3.DE", "IFX.DE", "MRK.DE",

        # Pays-Bas (AEX)
        "ASML.AS", "INGA.AS", "PHIA.AS", "WKL.AS", "ADYEN.AS", "HEIA.AS", "KPN.AS",
        "DSMN.AS", "ABN.AS", "AKZA.AS",

        # Espagne (IBEX)
        "SAN.MC", "TEF.MC", "IBE.MC", "BBVA.MC", "ITX.MC", "ELE.MC", "AMS.MC",
        "CABK.MC", "REP.MC", "ACS.MC",

        # Italie (FTSE MIB)
        "ISP.MI", "ENI.MI", "ENEL.MI", "STLAM.MI", "UCG.MI", "TIT.MI", "PRY.MI",
        "G.MI", "BAMI.MI", "MB.MI",

        # Suisse (SMI)
        "NESN.SW", "ROG.SW", "NOVN.SW", "UHR.SW", "ZURN.SW", "SIKA.SW", "LONN.SW",
        "CFR.SW", "GEBN.SW", "SREN.SW",

        # Royaume-Uni (FTSE 100)
        "GSK.L", "AZN.L", "BP.L", "ULVR.L", "HSBA.L", "RIO.L", "LSEG.L",
        "REL.L", "SHEL.L", "BHP.L",

        # Suède (OMX Stockholm)
        "ERIC-B.ST", "VOLV-B.ST", "SEB-A.ST", "ATCO-A.ST", "SHB-A.ST", "SCA-B.ST",
        "ESSITY-B.ST", "SAND.ST", "ABB.ST", "INVE-B.ST",

        # Finlande (OMX Helsinki)
        "NOKIA.HE", "STERV.HE", "SAMPO.HE", "UPM.HE", "FORTUM.HE", "ORNBV.HE",
        "KESKOB.HE", "NESTE.HE", "KNEBV.HE", "ELISA.HE",

        # Belgique (BEL 20)
        "ABI.BR", "KBC.BR", "COLR.BR", "UCB.BR", "GLPG.BR",

        # Danemark (OMX Copenhagen)
        "NOVO-B.CO", "DSV.CO", "MAERSK-B.CO", "CARL-B.CO", "COLO-B.CO"
    ]

    resultats = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(AnalyseAction(ticker).analyser): ticker
                  for ticker in tickers_europe}

        for future in concurrent.futures.as_completed(futures):
            try:
                resultat = future.result()
                if resultat:
                    # Vérification supplémentaire des résultats
                    if all(isinstance(v, (int, float, str)) for v in resultat.values()):
                        resultats.append(resultat)
                    else:
                        logger.warning(f"Résultat invalide détecté et ignoré")
            except Exception as e:
                logger.error(f"Erreur lors de l'analyse: {e}")
                continue

    # Tri et filtrage final des résultats
    resultats_valides = [r for r in resultats if r and r['gain_potentiel'] > 0]
    return sorted(resultats_valides, key=lambda x: x['gain_potentiel'], reverse=True)

def envoyer_email(opportunites):
    """Envoie le rapport par email via SendGrid"""
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        corps_html = RapportHTML.generer(opportunites[:10])

        # S'assurer que le contenu HTML est correctement encodé
        message = Mail(
            from_email=Email(FROM_EMAIL),
            to_emails=To(TO_EMAIL),
            subject=f"Analyse SBF 120 - {datetime.now().strftime('%d/%m/%Y')}")

        # Utilisation explicite de HtmlContent pour s'assurer que le contenu est traité comme HTML
        message.content = HtmlContent(corps_html)

        # Ajout de logs pour vérification
        logger.info("Contenu HTML généré. Premiers caractères :")
        logger.info(corps_html[:500])  # Log des premiers caractères pour vérification

        response = sg.send(message)
        logger.info(f"Email envoyé avec succès (status: {response.status_code})")

        # Log supplémentaire pour vérifier la réponse complète
        if response.status_code != 202:  # 202 est le code de succès attendu
            logger.warning(f"Code de statut inattendu: {response.status_code}")

    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email: {e}", exc_info=True)
        # Log plus détaillé de l'erreur si elle se produit
        if hasattr(e, 'body'):
            logger.error(f"Détails de l'erreur SendGrid: {e.body}")

def tache_journaliere():
    """Exécute l'analyse quotidienne"""
    try:
        logger.info("Démarrage de l'analyse journalière")
        opportunites = analyse_sbf_120()

        if opportunites:
            logger.info(f"Analyse terminée, {len(opportunites)} opportunités trouvées")
            envoyer_email(opportunites)
        else:
            logger.warning("Aucune opportunité trouvée")

    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de la tâche journalière: {e}", exc_info=True)

def main():
    """Fonction principale"""
    logger.info("Démarrage du programme")
    try:
        # Exécution immédiate
        tache_journaliere()

        # Programmation de la tâche quotidienne
        #schedule.every().day.at("18:30").do(tache_journaliere)
        #logger.info("Tâche programmée pour 18:30")

        # Boucle principale
        #while True:
        #    schedule.run_pending()
        #    time.sleep(60)

    except Exception as e:
        logger.error(f"Erreur dans la boucle principale: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
