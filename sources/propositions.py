import httpx
import asyncio
import unicodedata
import re
import html

SOURCE_URL = "https://www.nosdeputes.fr"

HEADERS = {
    "User-Agent": "PoliticianAPI/1.0 (contact@example.com) python-httpx"
}

def _slugify(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"\s+", "-", name)
    return name

def _strip_html(text: str) -> str:
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return text.strip()

async def _fetch_all_results(client, name: str, object_name: str, max_results: int = None) -> list:
    """Pagine l'API nosdeputes jusqu'à épuisement ou max_results atteint."""
    all_results = []
    page = 1
    while True:
        try:
            resp = await client.get(
                f"{SOURCE_URL}/recherche/{name.replace(' ', '+')}",
                params={"format": "json", "object_name": object_name, "page": page}
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            results = data.get("results", [])
            if not results:
                break
            all_results.extend(results)
            if max_results and len(all_results) >= max_results:
                all_results = all_results[:max_results]
                break
            if len(results) < 10:
                break
            page += 1
        except Exception:
            break
    return all_results

async def _fetch_proposition_detail(client, sem, url: str):
    async with sem:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            texte = resp.json().get("texteloi", {})
            if not texte:
                return None
            return {
                "titre":       texte.get("titre"),
                "type":        texte.get("type"),
                "date":        texte.get("date"),
                "signataires": texte.get("signataires"),
                "url_an":      texte.get("source"),
                "url":         texte.get("url_nosdeputes"),
            }
        except Exception:
            return None

async def _fetch_amendement_detail(client, sem, url: str):
    async with sem:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            amend = resp.json().get("amendement", {})
            if not amend:
                return None
            return {
                "sujet":       amend.get("sujet"),
                "sort":        amend.get("sort"),
                "date":        amend.get("date"),
                "signataires": amend.get("signataires"),
                "texte":       _strip_html(amend.get("texte")),
                "expose":      _strip_html(amend.get("expose")),
                "groupe":      amend.get("auteur_groupe_acronyme"),
                "url_an":      amend.get("source"),
                "url":         amend.get("url_nosdeputes"),
            }
        except Exception:
            return None

async def get_propositions_info(name: str) -> dict:
    slug = _slugify(name)
    sem = asyncio.Semaphore(8)  # max 8 requêtes détail en parallèle

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:

            # Récupération de toutes les pages en parallèle
            # Amendements limités à 50 les plus récents (trop volumineux sinon)
            props_results, amend_results = await asyncio.gather(
                _fetch_all_results(client, name, "Texteloi"),
                _fetch_all_results(client, name, "Amendement", max_results=50),
            )

            # Détails propositions en parallèle
            prop_urls = [r.get("document_url") for r in props_results if r.get("document_url")]
            amend_urls = [r.get("document_url") for r in amend_results if r.get("document_url")]

            props_details, amend_details = await asyncio.gather(
                asyncio.gather(*[_fetch_proposition_detail(client, sem, u) for u in prop_urls]),
                asyncio.gather(*[_fetch_amendement_detail(client, sem, u) for u in amend_urls]),
            )

            propositions = [p for p in props_details if p]
            amendements  = [a for a in amend_details if a]

            return {
                "trouve":       True,
                "propositions": propositions,
                "amendements":  amendements,
                "source_url":   f"{SOURCE_URL}/{slug}",
            }

    except Exception as e:
        return {
            "trouve":       False,
            "erreur":       str(e),
            "propositions": [],
            "amendements":  [],
            "source_url":   SOURCE_URL,
        }
