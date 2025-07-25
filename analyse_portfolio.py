# analyse_portfolio.py
import os
import yaml
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import random
import logging
from curl_cffi import requests
import yfinance_cookie_patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuration du logging pour tracer les problèmes de récupération de données
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(os.path.join(BASE_DIR, 'portfolio_analysis.log'))
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False

# Chargement de la configuration globale et des proxies
CONFIG_FILE = os.path.join(BASE_DIR, 'config.yaml')
try:
    with open(CONFIG_FILE, 'r') as f:
        CFG = yaml.safe_load(f)
except Exception as e:
    logger.error("Erreur lors du chargement du fichier de configuration: %s", e)
    CFG = {}

# Liste de proxies HTTP similaire à celle utilisée dans analyzer.py
PROXIES = CFG.get('proxies', [
    "http://proxy1.example.com:8080",
    "http://proxy2.example.com:8080",
    "http://proxy3.example.com:8080",
])
# Possibilité de désactiver complètement l'utilisation des proxies
USE_PROXIES = CFG.get('use_proxies', True)

# Session HTTP global avec impersonation Chrome
SESSION = requests.Session(impersonate="chrome")
yfinance_cookie_patch.patch_yfdata_cookie_basic()


def set_random_proxy():
    """Choisit un proxy aléatoirement et le définit pour les requêtes."""
    if not USE_PROXIES:
        # Nettoyer complètement les variables d'environnement pouvant indiquer
        # l'utilisation d'un proxy
        for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            os.environ.pop(var, None)
        SESSION.proxies.clear()
        logger.info("Utilisation des proxies désactivée")
        return None

    proxy = random.choice(PROXIES)
    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    SESSION.proxies.update({"http": proxy, "https": proxy})
    logger.info(f"Proxy choisi: {proxy}")
    return proxy

class PortfolioUtils:
    @staticmethod
    def format_money(amount):
        """Formate un montant en euros avec séparateur de milliers."""
        return f"{amount:,.2f} €".replace(',', ' ')

    @staticmethod
    def format_percentage(value):
        """Formate un pourcentage avec 2 décimales."""
        return f"{value:+.2f}%"

    @staticmethod
    def get_color_for_value(value):
        """Retourne une couleur en fonction de la valeur."""
        if value > 0:
            return "#059669"  # Vert
        elif value < 0:
            return "#dc2626"  # Rouge
        return "#1a1a1a"     # Noir (neutre)

class PortfolioAnalyzer:
    def __init__(self, utils=None):
        self.utils = utils or PortfolioUtils()

    def calculer_tendance(self, historique):
        """Retourne True si la tendance est haussière, False sinon."""
        try:
            mm20 = historique['Close'].rolling(window=20).mean()
            if len(mm20) < 5:
                logger.warning("Pas assez de données de tendance")
                return False
            return bool(mm20.iloc[-1] > mm20.iloc[-5])
        except Exception as e:
            logger.error("Erreur lors du calcul de la tendance: %s", e)
            return False

    def calculer_prix_vente_cible(self, historique):
        """Calcule un prix de vente conseillé selon la méthode d'analyzer.py.
        Retourne un tuple (prix, raison) où raison décrit la cause si le prix
        ne peut pas être calculé."""
        try:
            if len(historique) < 252:
                msg = "Données insuffisantes pour calculer le prix de vente"
                logger.warning(msg)
                return None, msg

            tendance_3m = historique['Close'].tail(90).mean()
            tendance_6m = historique['Close'].tail(180).mean()
            tendance_12m = historique['Close'].tail(252).mean()

            if any(pd.isna(x) for x in [tendance_3m, tendance_6m, tendance_12m]):
                msg = "Tendances NaN rencontrées pour le prix de vente"
                logger.warning(msg)
                return None, msg

            prix_cible = (tendance_3m * 0.5 + tendance_6m * 0.3 + tendance_12m * 0.2)
            volatilite = historique['Close'].tail(30).pct_change().std()
            if pd.isna(volatilite):
                msg = "Volatilité NaN pour le prix de vente"
                logger.warning(msg)
                return None, msg

            dernier_prix = historique['Close'].iloc[-1]
            prix_final = prix_cible * (1 + volatilite)
            if prix_final <= dernier_prix:
                msg = "Prix final inférieur ou égal au cours actuel"
                return None, msg

            return float(prix_final), None
        except Exception as e:
            msg = f"Erreur lors du calcul du prix de vente: {e}"
            logger.error(msg)
            return None, msg

    def calculer_stop_loss(self, prix_achat, historique):
        """Calcule le stop loss en suivant les règles d'analyzer.py."""
        try:
            base_stop = prix_achat * (1 - CFG.get('stop_loss_percent', 5) / 100)
            support = historique['Close'].rolling(window=20).min().iloc[-1]
            if support > base_stop:
                return float(support * 0.995)
            return float(base_stop)
        except Exception as e:
            logger.warning("Erreur lors du calcul du stop loss: %s", e)
            return float(base_stop)

    def load_config(self, config_file='config.yaml'):
        """Charge la configuration depuis le fichier YAML."""
        if not os.path.isabs(config_file):
            config_file = os.path.join(BASE_DIR, config_file)
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)

    def get_stock_analysis(self, symbol, purchase_info, periods):
        """Analyse une action et retourne ses variations sur différentes périodes."""
        try:
            proxy = set_random_proxy()
            if proxy:
                logger.info(f"Proxy utilisé pour {symbol}: {proxy}")
            stock = yf.Ticker(symbol, session=SESSION)
            end_date = datetime.now()

            purchase_date = datetime.strptime(purchase_info['purchase_date'], '%Y-%m-%d')
            max_period = max(periods)
            start_date = min(purchase_date, end_date - timedelta(days=max_period))

            logger.info(f"Téléchargement des données récentes pour {symbol}")
            try:
                hist_recent = stock.history(period="2d")
                logger.info(f"{len(hist_recent)} lignes reçues pour les données récentes de {symbol}")
            except Exception as e:
                logger.error(f"Erreur lors du téléchargement des données récentes pour {symbol}: {e}", exc_info=True)
                return None

            logger.info(f"Téléchargement de l'historique complet pour {symbol} de {start_date.date()} à {end_date.date()}")
            try:
                hist = stock.history(start=start_date, end=end_date)
                logger.info(f"{len(hist)} lignes reçues pour l'historique complet de {symbol}")
            except Exception as e:
                logger.error(f"Erreur lors du téléchargement de l'historique pour {symbol}: {e}", exc_info=True)
                return None

            if hist.empty:
                logger.warning(f"Pas de données historiques pour {symbol}")
                return None
            
            current_price = hist['Close'].iloc[-1]
            purchase_price = purchase_info['purchase_price']

            tendance_bool = self.calculer_tendance(hist)
            tendance = "Haussi\u00e8re" if tendance_bool else "Baissi\u00e8re"
            prix_vente, raison_vente = self.calculer_prix_vente_cible(hist)
            stop_loss = self.calculer_stop_loss(purchase_price, hist)

            analysis = {
                'current_price': current_price,
                'purchase_price': purchase_price,
                'purchase_date': purchase_date,
                'quantity': purchase_info['quantity'],
                'variations': {},
                'total_value': current_price * purchase_info['quantity'],
                'total_cost': purchase_price * purchase_info['quantity'],
                'total_gain_loss': (current_price - purchase_price) * purchase_info['quantity'],
                'purchase_variation': ((current_price - purchase_price) / purchase_price) * 100,
                'trend': tendance,
                'sell_price': prix_vente,
                'sell_price_reason': raison_vente,
                'stop_loss': stop_loss
            }

            # Calculer explicitement la variation sur 1 jour
            if len(hist_recent) >= 2:
                yesterday_price = hist_recent['Close'].iloc[-2]
                today_price = hist_recent['Close'].iloc[-1]
                daily_variation = ((today_price - yesterday_price) / yesterday_price) * 100
                analysis['variations'][1] = daily_variation
            else:
                msg = f"Impossible de calculer la variation quotidienne pour {symbol}, données insuffisantes"
                logger.warning(msg)
                analysis['variations'][1] = 0.0  # Valeur par défaut

            # Calculer les autres périodes
            for period in periods:
                if period == 1:
                    continue  # Déjà traité ci-dessus
                if len(hist) >= period:
                    old_price = hist['Close'].iloc[-period]
                    variation = ((current_price - old_price) / old_price) * 100
                    analysis['variations'][period] = variation
                else:
                    logger.warning("Période %d jours non disponible pour %s", period, symbol)
                    analysis['variations'][period] = 0.0  # Valeur par défaut

            return analysis
        except Exception as e:
            logger.error("Erreur lors de l'analyse de %s: %s", symbol, str(e))
            return None


    def analyze_portfolio(self):
        """Analyse l'ensemble du portefeuille."""
        config = self.load_config()
        portfolio_data = []
        periods = [1, 90, 180]

        logger.info("Analyse du portefeuille...")
        for stock in config['portfolio']:
            logger.info("Analyse de %s...", stock['symbol'])
            purchase_info = {
                'purchase_price': stock['purchase_price'],
                'purchase_date': stock['purchase_date'],
                'quantity': stock['quantity']
            }

            analysis = self.get_stock_analysis(stock['symbol'], purchase_info, periods)
            if analysis:
                stock_data = {
                    'symbol': stock['symbol'],
                    'name': stock['name'],
                    'current_price': analysis['current_price'],
                    'purchase_price': analysis['purchase_price'],
                    'purchase_date': analysis['purchase_date'],
                    'quantity': analysis['quantity'],
                    'variations': analysis['variations'],
                    'total_value': analysis['total_value'],
                    'total_cost': analysis['total_cost'],
                    'total_gain_loss': analysis['total_gain_loss'],
                    'purchase_variation': analysis['purchase_variation'],
                    'trend': analysis['trend'],
                    'sell_price': analysis['sell_price'],
                    'sell_price_reason': analysis['sell_price_reason'],
                    'stop_loss': analysis['stop_loss'],
                }
                portfolio_data.append(stock_data)
                logger.info("%s analysé avec succès", stock['symbol'])
            else:
                msg = f"Impossible d'analyser {stock['symbol']}"
                logger.warning(msg)

        return portfolio_data, config

class HTMLReportGenerator:
    def __init__(self, utils=None):
        self.utils = utils or PortfolioUtils()

    def generate_html_report(self, portfolio_data):
        """Génère le rapport HTML avec styles inline."""
        if not portfolio_data:
            return self._generate_empty_report()

        total_portfolio_value = sum(stock['total_value'] for stock in portfolio_data)
        total_portfolio_cost = sum(stock['total_cost'] for stock in portfolio_data)
        total_portfolio_gain = total_portfolio_value - total_portfolio_cost
        total_portfolio_return = (total_portfolio_gain / total_portfolio_cost * 100) if total_portfolio_cost > 0 else 0.0

        container_style = """
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1100px;
            margin: 0 auto;
            padding: 40px 20px;
            background-color: #f1f3f5;
        """

        header_style = """
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 35px;
            border-radius: 12px;
            margin-bottom: 30px;
            text-align: center;
        """

        summary_style = """
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        """

        summary_item_style = """
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            border: 1px solid #e0e4e8;
        """

        return f"""
        <div style="{container_style}">
            <div style="{header_style}">
                <h1 style="font-size: 24px; font-weight: 700; margin-bottom: 6px;">Rapport de Portefeuille</h1>
                <p style="font-size: 16px; opacity: 0.9;">Généré le {datetime.now().strftime('%d %B %Y à %H:%M').lower()}</p>
            </div>

            <div style="{summary_style}">
                <div style="{summary_item_style}">
                    <div style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 12px; font-weight: 600;">
                        Valeur Totale
                    </div>
                    <div style="font-size: 24px; font-weight: 700; line-height: 1.2; white-space: nowrap;">
                        {self.utils.format_money(total_portfolio_value)}
                    </div>
                </div>

                <div style="{summary_item_style}">
                    <div style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 12px; font-weight: 600;">
                        Coût Total
                    </div>
                    <div style="font-size: 24px; font-weight: 700; line-height: 1.2; white-space: nowrap;">
                        {self.utils.format_money(total_portfolio_cost)}
                    </div>
                </div>

                <div style="{summary_item_style}">
                    <div style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 12px; font-weight: 600;">
                        Gain/Perte Total
                    </div>
                    <div style="font-size: 24px; font-weight: 700; line-height: 1.2; color: {self.utils.get_color_for_value(total_portfolio_gain)}; white-space: nowrap;">
                        {self.utils.format_money(total_portfolio_gain)}
                    </div>
                </div>

                <div style="{summary_item_style}">
                    <div style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 12px; font-weight: 600;">
                        Performance Globale
                    </div>
                    <div style="font-size: 24px; font-weight: 700; line-height: 1.2; color: {self.utils.get_color_for_value(total_portfolio_return)}; white-space: nowrap;">
                        {self.utils.format_percentage(total_portfolio_return)}
                    </div>
                </div>
            </div>

            {self._generate_portfolio_table(portfolio_data)}

            <div style="margin-top: 40px; padding: 25px; background: white; border-radius: 12px; font-size: 13px; color: #666; text-align: center; border: 1px solid #e0e4e8; line-height: 1.6;">
                <p>Ce rapport est généré automatiquement à partir des données de marché en temps réel.</p>
                <p>Les tendances sont basées sur l'analyse technique et ne constituent pas des conseils en investissement.</p>
            </div>
        </div>
        """

    def _generate_empty_report(self):
        return """
        <div class="container">
            <div class="header">
                <h1>Rapport de Portefeuille</h1>
                <p>Aucune donnée disponible</p>
            </div>
        </div>
        """

    def _generate_portfolio_table(self, portfolio_data):
        """Génère le tableau des actions du portefeuille."""
        table_style = """
            width: 100%;
            border-collapse: collapse;
            margin: 30px 0;
            background: white;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
            border-radius: 12px;
            border: 1px solid #e0e4e8;
        """

        th_style = """
            background: linear-gradient(to bottom, #f8f9fa, #f1f3f5);
            color: #2c3e50;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 0.5px;
            padding: 20px 16px;
            text-align: left;
            border-bottom: 2px solid #e9ecef;
        """

        td_style = """
            padding: 16px;
            border-bottom: 1px solid #e9ecef;
            font-size: 14px;
            vertical-align: middle;
        """

        variation_base_style = """
            font-weight: 600;
            padding: 8px 12px;
            border-radius: 6px;
            display: inline-block;
            min-width: 95px;
            text-align: right;
            font-family: monospace;
            font-size: 13px;
        """

        html = f"""
            <table style="{table_style}">
                <thead>
                    <tr>
                        <th style="{th_style}">Action</th>
                        <th style="{th_style} text-align: right;">Prix Actuel</th>
                        <th style="{th_style} text-align: right;">1J</th>
                        <th style="{th_style} text-align: right;">3M</th>
                        <th style="{th_style} text-align: right;">6M</th>
                        <th style="{th_style} text-align: right;">Depuis Achat</th>
                        <th style="{th_style} text-align: right;">Gain/Perte</th>
                        <th style="{th_style} text-align: center;">Tendance</th>
                        <th style="{th_style} text-align: right;">Cible Vente</th>
                        <th style="{th_style} text-align: right;">Stop Loss</th>
                    </tr>
                </thead>
                <tbody>
        """

        for stock in portfolio_data:
            var_1d = stock['variations'].get(1, 0)
            var_3m = stock['variations'].get(90, 0)
            var_6m = stock['variations'].get(180, 0)

            # Définir les styles de variation en fonction des valeurs
            def get_variation_style(value):
                base = variation_base_style
                if value > 0:
                    return base + """
                        color: #059669;
                        background-color: #ecfdf5;
                        border: 1px solid #a7f3d0;
                    """
                elif value < 0:
                    return base + """
                        color: #dc2626;
                        background-color: #fef2f2;
                        border: 1px solid #fecaca;
                    """
                return base + """
                    color: #0284c7;
                    background-color: #f0f9ff;
                    border: 1px solid #bae6fd;
                """

            # Style pour la tendance haussière ou baissière
            def get_trend_style(trend):
                base = """
                    font-weight: 600;
                    padding: 8px 16px;
                    border-radius: 6px;
                    text-transform: uppercase;
                    font-size: 12px;
                    letter-spacing: 0.5px;
                    display: inline-block;
                """
                if trend.lower().startswith('haussi'):
                    return base + """
                        background-color: #dcfce7;
                        color: #059669;
                        border: 1px solid #a7f3d0;
                    """
                else:
                    return base + """
                        background-color: #fee2e2;
                        color: #dc2626;
                        border: 1px solid #fecaca;
                    """

            html += f"""
                <tr style="border-bottom: 1px solid #e9ecef;">
                    <td style="{td_style}">
                        <div style="font-weight: 600; color: #1a1a1a; font-size: 14px;">{stock['name']}</div>
                        <div style="color: #666; font-size: 13px;">{stock['symbol']}</div>
                    </td>
                    <td style="{td_style} text-align: right; font-family: monospace;">{self.utils.format_money(stock['current_price'])}</td>
                    <td style="{td_style}">
                        <div style="{get_variation_style(var_1d)}">{self.utils.format_percentage(var_1d)}</div>
                    </td>
                    <td style="{td_style}">
                        <div style="{get_variation_style(var_3m)}">{self.utils.format_percentage(var_3m)}</div>
                    </td>
                    <td style="{td_style}">
                        <div style="{get_variation_style(var_6m)}">{self.utils.format_percentage(var_6m)}</div>
                    </td>
                    <td style="{td_style}">
                        <div style="{get_variation_style(stock['purchase_variation'])}">{self.utils.format_percentage(stock['purchase_variation'])}</div>
                    </td>
                    <td style="{td_style} text-align: right; font-family: monospace; {self.utils.get_color_for_value(stock['total_gain_loss'])}">
                        {self.utils.format_money(stock['total_gain_loss'])}
                    </td>
                    <td style="{td_style} text-align: center;">
                        <div style="{get_trend_style(stock['trend'])}">
                            {stock['trend']}
                        </div>
                    </td>
                    <td style="{td_style} text-align: right; font-family: monospace;">
                        {self.utils.format_money(stock['sell_price']) if stock['sell_price'] is not None else stock.get('sell_price_reason', 'N/A')}
                    </td>
                    <td style="{td_style} text-align: right; font-family: monospace;">
                        {self.utils.format_money(stock['stop_loss'])}
                    </td>
                </tr>
            """

        html += """
                </tbody>
            </table>
        """
        return html

    def _generate_stock_row(self, stock, var_1d, var_3m, var_6m):
        """Génère une ligne du tableau pour une action."""
        return f"""
            <tr>
                <td>
                    <div class="stock-info">
                        <span class="stock-name">{stock['name']}</span>
                        <span class="stock-symbol">{stock['symbol']}</span>
                    </div>
                </td>
                <td class="value-cell">{self.utils.format_money(stock['current_price'])}</td>
                <td>
                    <div class="variation {'positive' if var_1d > 0 else 'negative' if var_1d < 0 else 'neutral'}">
                        {self.utils.format_percentage(var_1d)}
                    </div>
                </td>
                <td>
                    <div class="variation {'positive' if var_3m > 0 else 'negative' if var_3m < 0 else 'neutral'}">
                        {self.utils.format_percentage(var_3m)}
                    </div>
                </td>
                <td>
                    <div class="variation {'positive' if var_6m > 0 else 'negative' if var_6m < 0 else 'neutral'}">
                        {self.utils.format_percentage(var_6m)}
                    </div>
                </td>
                <td>
                    <div class="variation {'positive' if stock['purchase_variation'] > 0 else 'negative' if stock['purchase_variation'] < 0 else 'neutral'}">
                        {self.utils.format_percentage(stock['purchase_variation'])}
                    </div>
                </td>
                <td class="value-cell" style="color: {self.utils.get_color_for_value(stock['total_gain_loss'])}">
                    {self.utils.format_money(stock['total_gain_loss'])}
                </td>
                <td style="text-align: center">
                    <div class="trend {stock['trend'].lower()}">{stock['trend']}</div>
                </td>
                <td class="value-cell">{self.utils.format_money(stock['sell_price']) if stock['sell_price'] is not None else stock.get('sell_price_reason', 'N/A')}</td>
                <td class="value-cell">{self.utils.format_money(stock['stop_loss'])}</td>
            </tr>
        """

def send_email(from_email, to_email, subject, html_content, api_key):
    """Envoie le rapport par email via SendGrid."""
    try:
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )

        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        return True
    except Exception as e:
        logger.error("Erreur lors de l'envoi de l'email: %s", str(e))
        return False

def main():
    try:
        logger.info("Initialisation de l'analyse...")
        utils = PortfolioUtils()
        analyzer = PortfolioAnalyzer(utils)
        report_generator = HTMLReportGenerator(utils)

        portfolio_data, config = analyzer.analyze_portfolio()

        if not portfolio_data:
            logger.error("Aucune donnée de portefeuille n'a pu être récupérée !")
            return

        logger.info("Génération du rapport...")
        html_report = report_generator.generate_html_report(portfolio_data)

        logger.info("Envoi du rapport par email...")
        success = send_email(
            config['email']['from'],
            config['email']['to'],
            "Rapport quotidien de portefeuille",
            html_report,
            config['email']['api_key']
        )

        if success:
            logger.info("Rapport envoyé avec succès")
        else:
            logger.error("Échec de l'envoi du rapport")

    except Exception as e:
        logger.error("Une erreur est survenue: %s", str(e))
        raise

if __name__ == "__main__":
    main()
