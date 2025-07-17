import os
from datetime import datetime, timedelta
import pandas as pd
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CACHE_DIR = os.path.join(BASE_DIR, 'cache')
MAX_AGE = timedelta(hours=24)

logger = logging.getLogger(__name__)


def _cache_path(ticker: str, period: str) -> str:
    ticker_safe = ticker.replace('/', '_').replace('\\', '_').replace('.', '_')
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{ticker_safe}_{period}.csv")


def load_cached_data(ticker: str, period: str = '1y', max_age: timedelta = MAX_AGE):
    """Load cached data if it exists and is recent enough."""
    path = _cache_path(ticker, period)
    if os.path.exists(path):
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        if datetime.now() - mtime < max_age:
            try:
                logger.info(f"Chargement des données en cache pour {ticker}")
                return pd.read_csv(path, index_col=0, parse_dates=True)
            except Exception as e:
                logger.warning(f"Impossible de lire le cache pour {ticker}: {e}")
    return None


def save_to_cache(ticker: str, period: str, df: pd.DataFrame):
    """Save downloaded data to cache."""
    path = _cache_path(ticker, period)
    try:
        df.to_csv(path)
        logger.info(f"Données enregistrées dans le cache pour {ticker}")
    except Exception as e:
        logger.warning(f"Impossible d'enregistrer le cache pour {ticker}: {e}")

