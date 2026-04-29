import httpx
from sources.bord_politique import get_bord_politique
from typing import Optional

SOURCE_URL = "https://fr.wikipedia.org"

HEADERS = {
    "User-Agent": "PoliticianAPI/1.0 (contact@example.com) python-httpx"
}

async def get_wikipedia_info(name: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:

            search_resp = await client.get(
                "https://fr.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": name,
                    "format": "json",
                    "srlimit": 1,
                }
            )
            results = search_resp.json().get("query", {}).get("search", [])

            if not results:
                return {"trouve": False, "source_url": SOURCE_URL}

            page_title = results[0]["title"]

            summary_resp = await client.get(
                f"https://fr.wikipedia.org/api/rest_v1/page/summary/{page_title.replace(' ', '_')}"
            )
            summary_data = summary_resp.json()

            wikidata = await _get_wikidata_info(client, page_title)

            return {
                "trouve":         True,
                "nom":            summary_data.get("title"),
                "resume":         summary_data.get("extract"),
                "photo":          summary_data.get("thumbnail", {}).get("source"),
                "parti":          wikidata.get("parti"),
                "bord_politique": get_bord_politique(wikidata.get("parti") or summary_data.get("parti")),
                "naissance":      wikidata.get("naissance"),
                "source_url":     summary_data.get("content_urls", {}).get("desktop", {}).get("page", SOURCE_URL),
            }

    except Exception as e:
        return {"trouve": False, "erreur": str(e), "source_url": SOURCE_URL}


async def _get_wikidata_info(client: httpx.AsyncClient, page_title: str) -> dict:
    try:
        resp = await client.get(
            "https://fr.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": page_title,
                "prop": "pageprops",
                "format": "json",
            }
        )
        pages = resp.json().get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        wikidata_id = page.get("pageprops", {}).get("wikibase_item")

        if not wikidata_id:
            return {}

        wd_resp = await client.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbgetentities",
                "ids": wikidata_id,
                "languages": "fr",
                "props": "claims",
                "format": "json",
            }
        )
        claims = wd_resp.json().get("entities", {}).get(wikidata_id, {}).get("claims", {})

        # Récupération des IDs
        parti_id = _extract_wikidata_id(claims, "P102")
        bord_id  = _extract_wikidata_id(claims, "P1387")

        # Résolution des labels en français
        ids_a_resoudre = [i for i in [parti_id, bord_id] if i]
        labels = {}
        if ids_a_resoudre:
            labels_resp = await client.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(ids_a_resoudre),
                    "languages": "fr",
                    "props": "labels",
                    "format": "json",
                }
            )
            entities = labels_resp.json().get("entities", {})
            for qid, entity in entities.items():
                label = entity.get("labels", {}).get("fr", {}).get("value")
                if label:
                    labels[qid] = label

        return {
            "parti":          labels.get(parti_id, parti_id),
            "bord_politique": labels.get(bord_id, bord_id),
            "naissance":      _extract_wikidata_date(claims, "P569"),
        }
    except Exception:
        return {}


def _extract_wikidata_date(claims: dict, prop: str) -> Optional[str]:
    try:
        val = claims[prop][0]["mainsnak"]["datavalue"]["value"]["time"]
        return val[1:11]
    except (KeyError, IndexError):
        return None


def _extract_wikidata_id(claims: dict, prop: str) -> Optional[str]:
    try:
        return claims[prop][0]["mainsnak"]["datavalue"]["value"]["id"]
    except (KeyError, IndexError):
        return None
