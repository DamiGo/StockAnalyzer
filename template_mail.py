from datetime import datetime
import pandas as pd

class RapportHTML:
    @staticmethod
    def generer(opportunites):
        """Génère le rapport HTML avec des styles en ligne pour une meilleure compatibilité email"""
        # Styles de base pour le corps et le conteneur
        body_style = "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f8fafc; color: #1e293b; line-height: 1.5;"
        container_style = "max-width: 1200px; margin: 0 auto; padding: 2rem;"

        # Style pour l'en-tête
        header_style = "background: linear-gradient(135deg, #0f172a, #1e293b); color: white; padding: 2.5rem 2rem; margin-bottom: 2.5rem; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);"
        header_title_style = "margin: 0 0 1rem 0; font-size: 1.875rem; font-weight: 600;"
        header_text_style = "margin: 0; opacity: 0.9; font-size: 1.125rem;"

        # Styles pour le tableau
        table_style = "width: 100%; border-collapse: separate; border-spacing: 0; background-color: white; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1); border-radius: 12px; overflow: hidden; margin-bottom: 2rem;"
        th_style = "background-color: #1e293b; color: white; padding: 1rem; text-align: left; font-weight: 500; font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em;"
        td_style = "padding: 1rem; border-bottom: 1px solid #e2e8f0; color: #1e293b; font-size: 0.9375rem;"

        # Styles spécifiques pour certaines colonnes
        ticker_style = td_style + " font-weight: 600; color: #3b82f6;"
        gain_style = td_style + " font-weight: 600; color: #22c55e;"
        negative_gain_style = td_style + " font-weight: 600; color: #ef4444;"
        score_style = td_style + " font-weight: 500;"
        signals_style = td_style + " color: #64748b; font-size: 0.875rem;"
        link_style = "color: #3b82f6; text-decoration: none; font-weight: 600;"

        # Création du DataFrame avec les nouvelles colonnes
        df = pd.DataFrame(opportunites)

        # Ajouter une colonne avec le nom et le lien
        df['Action_Nom_Lien'] = df.apply(
            lambda row: f"<a href='{row.get('lien_cotation', '#')}' style='{link_style}' target='_blank'>{row.get('nom', row['ticker'])} ({row['ticker']})</a>",
            axis=1
        )

        df = df[[
            'Action_Nom_Lien', 'prix_actuel', 'prix_achat_cible', 'prix_vente_cible', 'gain_potentiel',
            'score_opportunite', 'rsi', 'signaux'
        ]].rename(columns={
            'Action_Nom_Lien': 'Action',
            'prix_actuel': 'Prix Actuel (€)',
            'prix_achat_cible': 'Prix Achat (€)',
            'prix_vente_cible': 'Prix Vente (€)',
            'gain_potentiel': 'Gain Potentiel (%)',
            'score_opportunite': 'Score',
            'rsi': 'RSI',
            'signaux': 'Signaux Positifs'
        })

        # Formatage des nombres
        for col in ['Prix Actuel (€)', 'Prix Achat (€)', 'Prix Vente (€)']:
            df[col] = df[col].apply(lambda x: f'{x:,.2f}'.replace(',', ' '))

        # Création des textes formatés avec couleurs conditionnelles pour le gain potentiel
        gain_potentiel_original = [opp['gain_potentiel'] for opp in opportunites]
        df['Gain_Style'] = [gain_style if g > 0 else negative_gain_style for g in gain_potentiel_original]
        df['Gain Potentiel (%)'] = [f'+{g:.1f}%' if g > 0 else f'{g:.1f}%' for g in gain_potentiel_original]

        df['Score'] = df['Score'].apply(lambda x: f'{x:.2f}')
        df['RSI'] = df['RSI'].apply(lambda x: f'{x:.1f}')

        # Génération du HTML avec styles en ligne
        header_cells = []
        for col in df.columns[:-1]:  # Exclure la colonne Gain_Style
            header_cells.append(f'<th style="{th_style}">{col}</th>')
        header_row = '<tr>' + ''.join(header_cells) + '</tr>'

        rows = []
        for _, row in df.iterrows():
            cells = []
            for i, col in enumerate(df.columns[:-1]):  # Exclure la colonne Gain_Style
                value = row[col]
                if i == 0:  # Action avec nom et lien
                    cells.append(f'<td style="{ticker_style}">{value}</td>')
                elif col == 'Gain Potentiel (%)':  # Gain Potentiel avec style conditionnel
                    cells.append(f'<td style="{row["Gain_Style"]}">{value}</td>')
                elif col == 'Score':  # Score
                    cells.append(f'<td style="{score_style}">{value}</td>')
                elif col == 'Signaux Positifs':  # Signaux
                    cells.append(f'<td style="{signals_style}">{value}</td>')
                else:
                    cells.append(f'<td style="{td_style}">{value}</td>')
            rows.append('<tr>' + ''.join(cells) + '</tr>')

        table_html = f'<table style="{table_style}">{header_row}{"".join(rows)}</table>'

        return f"""
        <!DOCTYPE html>
        <html lang="fr">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="{body_style}">
                <div style="{container_style}">
                    <div style="{header_style}">
                        <h1 style="{header_title_style}">Analyse des actions européennes - {datetime.now().strftime('%d/%m/%Y')}</h1>
                        <p style="{header_text_style}">Top opportunités d'investissement identifiées en Europe</p>
                    </div>
                    {table_html}
                    <div style="font-size: 0.85rem; color: #64748b; margin-top: 2rem; text-align: center;">
                        <p>Cette analyse est générée automatiquement par un algorithme et ne constitue pas une recommandation d'investissement.</p>
                        <p>Cliquez sur le nom d'une action pour voir sa cotation en temps réel.</p>
                    </div>
                </div>
            </body>
        </html>
        """
