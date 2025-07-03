import logging
import re
import sys
from typing import List

import yaml
import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False


HEADERS = {"User-Agent": "Mozilla/5.0"}
FREE_PROXY_LIST_URL = "https://free-proxy-list.net/"
GEONODE_URL = (
    "https://proxylist.geonode.com/api/proxy-list?limit=200&sort_by=lastChecked"
    "&sort_type=desc&protocols=https"
)
SCRAPINGANT_URL = "https://scrapingant.com/free-proxies/"
TEST_URL = "https://httpbin.org/ip"


def _fetch_from_free_proxy_list() -> List[str]:
    """Return proxies from free-proxy-list.net."""
    logger.info("Fetching proxy list from %s", FREE_PROXY_LIST_URL)
    response = requests.get(FREE_PROXY_LIST_URL, headers=HEADERS, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    proxies = []

    for row in soup.select("table#proxylisttable tbody tr"):
        cols = [c.text.strip() for c in row.find_all("td")]
        if len(cols) >= 7 and cols[6].lower() == "yes":
            proxies.append(f"{cols[0]}:{cols[1]}")

    logger.info("Found %d proxies on free-proxy-list.net", len(proxies))
    return proxies


def _fetch_from_geonode() -> List[str]:
    """Return proxies from geonode.com (HTTPS only)."""
    logger.info("Fetching proxy list from geonode")
    response = requests.get(GEONODE_URL, headers=HEADERS, timeout=10)
    response.raise_for_status()

    data = response.json()
    proxies = [f"{p['ip']}:{p['port']}" for p in data.get("data", [])]

    logger.info("Found %d proxies on geonode", len(proxies))
    return proxies


def _fetch_from_scrapingant() -> List[str]:
    """Return proxies from scrapingant.com (HTTPS)."""
    logger.info("Fetching proxy list from scrapingant")
    response = requests.get(SCRAPINGANT_URL, headers=HEADERS, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    proxies = []
    for row in soup.select("table tbody tr"):
        cols = [c.text.strip() for c in row.find_all("td")]
        if len(cols) >= 3 and "https" in cols[2].lower():
            proxies.append(f"{cols[0]}:{cols[1]}")

    logger.info("Found %d proxies on scrapingant", len(proxies))
    return proxies


def fetch_proxies() -> List[str]:
    """Return a combined list of proxies from multiple sources."""
    proxies: List[str] = []
    try:
        proxies.extend(_fetch_from_free_proxy_list())
    except Exception as exc:
        logger.warning("free-proxy-list.net fetch failed: %s", exc)

    try:
        proxies.extend(_fetch_from_geonode())
    except Exception as exc:
        logger.warning("geonode fetch failed: %s", exc)

    try:
        proxies.extend(_fetch_from_scrapingant())
    except Exception as exc:
        logger.warning("scrapingant fetch failed: %s", exc)

    unique_proxies = list(dict.fromkeys(proxies))
    logger.info("Total proxies fetched: %d", len(unique_proxies))
    return unique_proxies


def test_proxy(proxy: str) -> bool:
    """Return True if the HTTPS proxy works."""
    proxies = {"https": f"https://{proxy}"}
    try:
        requests.get(TEST_URL, proxies=proxies, timeout=5)
        return True
    except Exception as exc:
        logger.debug("Proxy %s failed: %s", proxy, exc)
        return False


def update_config(proxies: List[str], config_path: str = "config.yaml") -> None:
    """Update the YAML configuration file with the working proxies."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}

    cfg["proxies"] = proxies

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

    logger.info("Configuration updated with %d proxies", len(proxies))


def main(config_path: str = "config.yaml") -> None:
    """Fetch proxies, test them and update the config file."""
    proxies = fetch_proxies()
    ok, ko = [], []
    for proxy in proxies:
        if test_proxy(proxy):
            logger.info("[OK] %s", proxy)
            ok.append(proxy)
        else:
            logger.info("[KO] %s", proxy)
            ko.append(proxy)

    update_config(ok, config_path)

    print("\n=== Working proxies ===")
    for p in ok:
        print(p)
    print("\n=== Failed proxies ===")
    for p in ko:
        print(p)


if __name__ == "__main__":
    config_arg = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    main(config_arg)
