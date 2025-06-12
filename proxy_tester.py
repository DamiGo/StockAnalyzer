import base64
import logging
import re
from typing import List

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


URL = "http://free-proxy.cz/en/proxylist/country/all/https/date/all"
HEADERS = {"User-Agent": "Mozilla/5.0"}
TEST_URL = "https://httpbin.org/ip"


def fetch_proxies() -> List[str]:
    """Return a list of proxies ("ip:port") from free-proxy.cz."""
    logger.info("Fetching proxy list from %s", URL)
    response = requests.get(URL, headers=HEADERS, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    proxies = []

    rows = soup.select("table#proxy_list tbody tr")
    for row in rows:
        script_ip = row.select_one("td:nth-child(1) script")
        port_cell = row.select_one("td:nth-child(2)")
        if not script_ip or not port_cell:
            continue

        match = re.search(r'Base64.decode\("([A-Za-z0-9+/=]+)"\)', script_ip.text)
        if not match:
            continue

        ip = base64.b64decode(match.group(1)).decode("utf-8")
        port = port_cell.text.strip()
        proxies.append(f"{ip}:{port}")

    logger.info("Found %d proxies", len(proxies))
    return proxies


def test_proxy(proxy: str) -> bool:
    """Return True if the HTTPS proxy works."""
    proxies = {"https": f"https://{proxy}"}
    try:
        requests.get(TEST_URL, proxies=proxies, timeout=5)
        return True
    except Exception as exc:
        logger.debug("Proxy %s failed: %s", proxy, exc)
        return False


def main():
    proxies = fetch_proxies()
    ok, ko = [], []
    for proxy in proxies:
        if test_proxy(proxy):
            logger.info("[OK] %s", proxy)
            ok.append(proxy)
        else:
            logger.info("[KO] %s", proxy)
            ko.append(proxy)

    print("\n=== Working proxies ===")
    for p in ok:
        print(p)
    print("\n=== Failed proxies ===")
    for p in ko:
        print(p)


if __name__ == "__main__":
    main()
