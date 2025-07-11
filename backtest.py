import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List

from rich.console import Console
from rich.table import Table
from rich.progress import track

import yfinance as yf

from analyzer import AnalyseAction
from cache_utils import load_cached_data, save_to_cache

# Liste des tickers à analyser (repris de analyzer.py)
TICKERS = [
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
    "MF.PA", "WLN.PA", "ADS.DE", "ALV.DE", "BAYN.DE", "BMW.DE", "MBG.DE", "DBK.DE",
    "DTE.DE", "EOAN.DE", "SAP.DE", "SIE.DE", "VOW3.DE", "DHL.DE", "HEN3.DE", "IFX.DE",
    "MRK.DE", "ASML.AS", "INGA.AS", "PHIA.AS", "WKL.AS", "ADYEN.AS", "HEIA.AS", "KPN.AS",
    "DSMN.AS", "ABN.AS", "AKZA.AS", "SAN.MC", "TEF.MC", "IBE.MC", "BBVA.MC", "ITX.MC",
    "ELE.MC", "AMS.MC", "CABK.MC", "REP.MC", "ACS.MC", "ISP.MI", "ENI.MI", "ENEL.MI",
    "STLAM.MI", "UCG.MI", "TIT.MI", "PRY.MI", "G.MI", "BAMI.MI", "MB.MI", "NESN.SW",
    "ROG.SW", "NOVN.SW", "UHR.SW", "ZURN.SW", "SIKA.SW", "LONN.SW", "CFR.SW", "GEBN.SW",
    "SREN.SW", "GSK.L", "AZN.L", "BP.L", "ULVR.L", "HSBA.L", "RIO.L", "LSEG.L", "REL.L",
    "SHEL.L", "BHP.L", "ERIC-B.ST", "VOLV-B.ST", "SEB-A.ST", "ATCO-A.ST", "SHB-A.ST",
    "SCA-B.ST", "ESSITY-B.ST", "SAND.ST", "ABB.ST", "INVE-B.ST", "NOKIA.HE", "STERV.HE",
    "SAMPO.HE", "UPM.HE", "FORTUM.HE", "ORNBV.HE", "KESKOB.HE", "NESTE.HE", "KNEBV.HE",
    "ELISA.HE", "ABI.BR", "KBC.BR", "COLR.BR", "UCB.BR", "GLPG.BR", "NOVO-B.CO",
    "DSV.CO", "MAERSK-B.CO", "CARL-B.CO", "COLO-B.CO"
]

console = Console()

CACHE_PERIOD = "5y"
DATA_CACHE: Dict[str, pd.DataFrame] = {}


def get_data(ticker: str) -> pd.DataFrame:
    if ticker in DATA_CACHE:
        return DATA_CACHE[ticker]
    df = load_cached_data(ticker, CACHE_PERIOD)
    if df is None:
        yf_ticker = yf.Ticker(ticker)
        df = yf_ticker.history(period=CACHE_PERIOD)
        if not df.empty:
            save_to_cache(ticker, CACHE_PERIOD, df)
    DATA_CACHE[ticker] = df
    return df


class BacktestAnalyseAction(AnalyseAction):
    def __init__(self, ticker: str, date: datetime):
        super().__init__(ticker)
        self.date = date

    def _telecharger_donnees(self):
        df = get_data(self.ticker)
        df = df[df.index <= self.date]
        df = df.tail(252)
        return df


def simulate(initial_cash: float = 10000.0):
    start_date = datetime.now() - timedelta(days=365)
    end_date = datetime.now()
    days = pd.bdate_range(start_date, end_date)

    cash = initial_cash
    portfolio: Dict[str, Dict] = {}
    buy_count = 0
    sell_count = 0

    for current_day in track(days, description="Simulation"):
        # Vendre si objectif atteint
        for ticker in list(portfolio.keys()):
            data = get_data(ticker)
            row = data.loc[data.index == current_day]
            if not row.empty:
                price = row["Close"].iloc[0]
                target = portfolio[ticker]["target"]
                if price >= target:
                    qty = portfolio[ticker]["quantity"]
                    cash += qty * target
                    sell_count += qty
                    del portfolio[ticker]

        # Acheter de nouvelles actions
        for ticker in TICKERS:
            if ticker in portfolio:
                continue
            action = BacktestAnalyseAction(ticker, current_day)
            result = action.analyser()
            if not result:
                continue
            buy_price = result["prix_achat_cible"]
            sell_price = result["prix_vente_cible"]
            if buy_price and sell_price and sell_price > buy_price and cash >= buy_price:
                qty = int(cash // buy_price)
                if qty > 0:
                    portfolio[ticker] = {
                        "quantity": qty,
                        "buy": buy_price,
                        "target": sell_price,
                        "date": current_day
                    }
                    cash -= qty * buy_price
                    buy_count += qty

        # Affichage du portefeuille
        table = Table(title=f"{current_day.date()} - Cash: {cash:.2f}")
        table.add_column("Ticker")
        table.add_column("Qty", justify="right")
        table.add_column("Buy", justify="right")
        table.add_column("Target", justify="right")
        for t, info in portfolio.items():
            table.add_row(t, str(info["quantity"]), f"{info['buy']:.2f}", f"{info['target']:.2f}")
        console.print(table)

    # Valorisation finale
    final_value = cash
    for ticker, info in portfolio.items():
        data = get_data(ticker)
        if not data.empty:
            last_price = data[data.index <= end_date]["Close"].iloc[-1]
            final_value += last_price * info["quantity"]

    performance = (final_value - initial_cash) / initial_cash * 100

    console.print("\n[b]Bilan final[/b]")
    console.print(f"Actions achetées: {buy_count}")
    console.print(f"Actions vendues: {sell_count}")
    console.print(f"Valeur finale du portefeuille: {final_value:.2f}")
    console.print(f"Performance: {performance:.2f}%")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backtest simple")
    parser.add_argument("--cash", type=float, default=10000.0, help="Montant initial")
    args = parser.parse_args()
    simulate(args.cash)
