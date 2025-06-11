import os
import subprocess
import logging
import sys
import importlib

# Configuration
REPO_URL = os.environ.get('REPO_URL', 'https://github.com/DamiGo/StockAnalyzer.git')
REPO_DIR = os.environ.get('REPO_DIR', os.path.expanduser('~/StockAnalyzer'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def _backup_config():
    """Return the current config.yaml content if it exists."""
    cfg_path = os.path.join(REPO_DIR, 'config.yaml')
    if os.path.isfile(cfg_path):
        logging.info('Backing up local config.yaml')
        with open(cfg_path, 'rb') as f:
            return f.read()
    return None


def _restore_config(data):
    """Restore the saved config.yaml content if provided."""
    if data is None:
        return
    cfg_path = os.path.join(REPO_DIR, 'config.yaml')
    logging.info('Restoring local config.yaml')
    with open(cfg_path, 'wb') as f:
        f.write(data)


def update_repo():
    """Clone or update the repository without overwriting config.yaml."""
    backup = _backup_config()
    if not os.path.isdir(REPO_DIR):
        logging.info('Cloning repository %s into %s', REPO_URL, REPO_DIR)
        subprocess.run(['git', 'clone', REPO_URL, REPO_DIR], check=True)
    else:
        logging.info('Pulling latest changes in %s', REPO_DIR)
        subprocess.run(['git', '-C', REPO_DIR, 'pull'], check=True)
    _restore_config(backup)

_portfolio_ran = False


def run_portfolio_report():
    """Run the daily portfolio report exactly once."""
    global _portfolio_ran
    if _portfolio_ran:
        logging.info('Portfolio report already executed; skipping.')
        return

    try:
        sys.path.insert(0, REPO_DIR)
        module = importlib.import_module('analyse_portfolio')

        if hasattr(module, 'rapport_quotidien'):
            module.rapport_quotidien()
        elif hasattr(module, 'main'):
            module.main()
        else:
            subprocess.run([
                'python',
                os.path.join(REPO_DIR, 'analyse_portfolio.py')
            ], check=True)

        _portfolio_ran = True
    except ModuleNotFoundError:
        logging.warning('Module analyse_portfolio not found; skipping portfolio report.')
    except Exception as exc:
        logging.error('Erreur lors du rapport du portefeuille: %s', exc)

def run_stock_analysis():
    """Run the stock analysis function."""
    try:
        sys.path.insert(0, REPO_DIR)
        from analyzer import tache_journaliere
        tache_journaliere()
    except Exception as exc:
        logging.error('Erreur lors de l\'analyse des actions: %s', exc)

def main():
    update_repo()
    run_portfolio_report()
    run_stock_analysis()

if __name__ == '__main__':
    main()
