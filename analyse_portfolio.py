# analyse_portfolio.py
import yaml
import yfinance as yf
from datetime import datetime, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

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

    def load_config(self, config_file='config.yaml'):
        """Charge la configuration depuis le fichier YAML."""
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)

    def get_stock_analysis(self, symbol, purchase_info, periods):
        """Analyse une action et retourne ses variations sur différentes périodes."""
        try:
            stock = yf.Ticker(symbol)
            end_date = datetime.now()

            purchase_date = datetime.strptime(purchase_info['purchase_date'], '%Y-%m-%d')
            max_period = max(periods)
            start_date = min(purchase_date, end_date - timedelta(days=max_period))

            # Utiliser period="2d" pour s'assurer d'avoir les données les plus récentes pour la variation sur 1 jour
            hist_recent = stock.history(period="2d")

            # Récupérer l'historique complet pour les autres périodes
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                print(f"Pas de données historiques pour {symbol}")
                return None

            current_price = hist['Close'][-1]
            purchase_price = purchase_info['purchase_price']

            analysis = {
                'current_price': current_price,
                'purchase_price': purchase_price,
                'purchase_date': purchase_date,
                'quantity': purchase_info['quantity'],
                'variations': {},
                'total_value': current_price * purchase_info['quantity'],
                'total_cost': purchase_price * purchase_info['quantity'],
                'total_gain_loss': (current_price - purchase_price) * purchase_info['quantity'],
                'purchase_variation': ((current_price - purchase_price) / purchase_price) * 100
            }

            # Calculer explicitement la variation sur 1 jour
            if len(hist_recent) >= 2:
                yesterday_price = hist_recent['Close'][-2]
                today_price = hist_recent['Close'][-1]
                daily_variation = ((today_price - yesterday_price) / yesterday_price) * 100
                analysis['variations'][1] = daily_variation
            else:
                print(f"Impossible de calculer la variation quotidienne pour {symbol}, données insuffisantes")
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
                    print(f"Période {period} jours non disponible pour {symbol}")
                    analysis['variations'][period] = 0.0  # Valeur par défaut

            return analysis
        except Exception as e:
            print(f"Erreur lors de l'analyse de {symbol}: {str(e)}")
            return None

    def get_recommendation(self, variations, purchase_variation):
        """Génère une recommandation basée sur les variations."""
        recent_var = variations.get(1, 0)
        mid_var = variations.get(90, 0)
        long_var = variations.get(180, 0)

        if purchase_variation < -20:
            if mid_var > 10:
                return "RENFORCER - Position en perte mais tendance positive récente"
            else:
                return "SURVEILLER - Position en perte significative"
        elif purchase_variation > 50:
            if recent_var < -5:
                return "VENDRE - Forte plus-value et tendance baissière récente"
            else:
                return "GARDER - Excellente performance, surveiller les signes de renversement"
        elif long_var < -20 and mid_var < -10:
            return "RENFORCER - La baisse importante pourrait représenter une opportunité"
        elif long_var > 30 and recent_var > 5:
            return "VENDRE - La hausse importante suggère une prise de bénéfices"
        elif -10 <= mid_var <= 10:
            return "GARDER - Le titre montre une stabilité relative"
        else:
            return "SURVEILLER - Comportement incertain"

    def analyze_portfolio(self):
        """Analyse l'ensemble du portefeuille."""
        config = self.load_config()
        portfolio_data = []
        periods = [1, 90, 180]

        print("\nAnalyse du portefeuille...")
        for stock in config['portfolio']:
            print(f"\nAnalyse de {stock['symbol']}...")
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
                    'recommendation': self.get_recommendation(
                        analysis['variations'],
                        analysis['purchase_variation']
                    )
                }
                portfolio_data.append(stock_data)
                print(f"✓ {stock['symbol']} analysé avec succès")
            else:
                print(f"✗ Impossible d'analyser {stock['symbol']}")

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
                <h1 style="font-size: 36px; font-weight: 700; margin-bottom: 10px;">Rapport de Portefeuille</h1>
                <p style="font-size: 16px; opacity: 0.9;">Généré le {datetime.now().strftime('%d %B %Y à %H:%M').lower()}</p>
            </div>

            <div style="{summary_style}">
                <div style="{summary_item_style}">
                    <div style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 12px; font-weight: 600;">
                        Valeur Totale
                    </div>
                    <div style="font-size: 32px; font-weight: 700; line-height: 1.2;">
                        {self.utils.format_money(total_portfolio_value)}
                    </div>
                </div>

                <div style="{summary_item_style}">
                    <div style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 12px; font-weight: 600;">
                        Coût Total
                    </div>
                    <div style="font-size: 32px; font-weight: 700; line-height: 1.2;">
                        {self.utils.format_money(total_portfolio_cost)}
                    </div>
                </div>

                <div style="{summary_item_style}">
                    <div style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 12px; font-weight: 600;">
                        Gain/Perte Total
                    </div>
                    <div style="font-size: 32px; font-weight: 700; line-height: 1.2; color: {self.utils.get_color_for_value(total_portfolio_gain)}">
                        {self.utils.format_money(total_portfolio_gain)}
                    </div>
                </div>

                <div style="{summary_item_style}">
                    <div style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; margin-bottom: 12px; font-weight: 600;">
                        Performance Globale
                    </div>
                    <div style="font-size: 32px; font-weight: 700; line-height: 1.2; color: {self.utils.get_color_for_value(total_portfolio_return)}">
                        {self.utils.format_percentage(total_portfolio_return)}
                    </div>
                </div>
            </div>

            {self._generate_portfolio_table(portfolio_data)}

            <div style="margin-top: 40px; padding: 25px; background: white; border-radius: 12px; font-size: 13px; color: #666; text-align: center; border: 1px solid #e0e4e8; line-height: 1.6;">
                <p>Ce rapport est généré automatiquement à partir des données de marché en temps réel.</p>
                <p>Les recommandations sont basées sur l'analyse technique et ne constituent pas des conseils en investissement.</p>
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
            font-size: 13px;
            letter-spacing: 0.5px;
            padding: 20px 16px;
            text-align: left;
            border-bottom: 2px solid #e9ecef;
        """

        td_style = """
            padding: 16px;
            border-bottom: 1px solid #e9ecef;
            font-size: 15px;
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
                        <th style="{th_style} text-align: center;">Recommandation</th>
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

            # Style pour la recommandation
            def get_recommendation_style(rec):
                base = """
                    font-weight: 600;
                    padding: 8px 16px;
                    border-radius: 6px;
                    text-transform: uppercase;
                    font-size: 12px;
                    letter-spacing: 0.5px;
                    display: inline-block;
                """
                if "RENFORCER" in rec:
                    return base + """
                        background-color: #dcfce7;
                        color: #059669;
                        border: 1px solid #a7f3d0;
                    """
                elif "VENDRE" in rec:
                    return base + """
                        background-color: #fee2e2;
                        color: #dc2626;
                        border: 1px solid #fecaca;
                    """
                return base + """
                    background-color: #e0f2fe;
                    color: #0284c7;
                    border: 1px solid #bae6fd;
                """

            html += f"""
                <tr style="border-bottom: 1px solid #e9ecef;">
                    <td style="{td_style}">
                        <div style="font-weight: 600; color: #1a1a1a; font-size: 15px;">{stock['name']}</div>
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
                        <div style="{get_recommendation_style(stock['recommendation'])}">
                            {stock['recommendation'].split(' - ')[0]}
                        </div>
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
                    <div class="recommendation {'buy' if 'RENFORCER' in stock['recommendation'] else 'sell' if 'VENDRE' in stock['recommendation'] else 'hold'}">
                        {stock['recommendation'].split(' - ')[0]}
                    </div>
                </td>
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
        print(f"Erreur lors de l'envoi de l'email: {str(e)}")
        return False

def main():
    try:
        print("Initialisation de l'analyse...")
        utils = PortfolioUtils()
        analyzer = PortfolioAnalyzer(utils)
        report_generator = HTMLReportGenerator(utils)

        portfolio_data, config = analyzer.analyze_portfolio()

        if not portfolio_data:
            print("\nErreur: Aucune donnée de portefeuille n'a pu être récupérée!")
            return

        print("\nGénération du rapport...")
        html_report = report_generator.generate_html_report(portfolio_data)

        print("\nEnvoi du rapport par email...")
        success = send_email(
            config['email']['from'],
            config['email']['to'],
            "Rapport quotidien de portefeuille",
            html_report,
            config['email']['api_key']
        )

        if success:
            print("\n✓ Rapport envoyé avec succès!")
        else:
            print("\n✗ Échec de l'envoi du rapport")

    except Exception as e:
        print(f"\nUne erreur est survenue: {str(e)}")
        raise

if __name__ == "__main__":
    main()
