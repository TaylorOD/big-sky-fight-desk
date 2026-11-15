from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


def fetch_excerpt(url, allowed):
    """Read a bounded HTML excerpt. Every redirect must stay on the source allowlist."""
    with httpx.Client(timeout=15, follow_redirects=False, headers={"User-Agent": "BigSkyFightDesk/1.0 (source verification)"}) as client:
        for _ in range(4):
            if not allowed(url):
                raise ValueError("Source redirects outside the permitted sites.")
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", ""):
                    raise ValueError("This source is not an HTML page.")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 1_000_000:
                        raise ValueError("Source page is too large.")
                soup = BeautifulSoup(bytes(data), "html.parser")
                for node in soup(["script", "style", "nav", "header", "footer", "noscript"]):
                    node.decompose()
                main = soup.find("main") or soup.find("article") or soup.body or soup
                text = " ".join(main.stripped_strings)
                if len(text) < 150:
                    raise ValueError("Not enough source text could be read.")
                return text[:16000]
        raise ValueError("Too many source redirects.")


def attach_excerpts(research, allowed):
    # Only the cited pages belong in the evidence set, not every search result.
    from concurrent.futures import ThreadPoolExecutor
    sources = research["sources"][:8]
    def read(source):
        source = dict(source)
        try:
            source["excerpt"] = fetch_excerpt(source["url"], allowed)
        except (httpx.HTTPError, ValueError):
            source["excerpt"] = ""
            source["access_note"] = "Direct source text could not be retrieved. Search citations alone are not enough to establish a result."
        return source
    with ThreadPoolExecutor(max_workers=4) as pool:
        research["sources"] = list(pool.map(read, sources))
    if sum(bool(s["excerpt"]) for s in research["sources"]) < 2:
        raise ValueError("Could not read at least two source pages. Try a topic with accessible venue or local reporting pages.")
    return research
