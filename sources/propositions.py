import httpx
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
    """Supprime les balises HTML et décode les entités."""
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return text.strip()

async def get_propositions_info(name: str) -> dict:
    slug = _slugify(name)

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:

            # 1. Propositions et rapports de loi
            props_resp = await client.get(
                f"{SOURCE_URL}/recherche/{name.replace(' ', '+')}",
                params={"format": "json", "object_name": "Texteloi"}
            )

            propositions = []
            if props_resp.status_code == 200:
                results = props_resp.json().get("results", [])
                for r in results[:8]:
                    url = r.get("document_url", "")
                    if not url:
                        continue
                    detail_resp = await client.get(url)
                    if detail_resp.status_code != 200:
                        continue
                    texte = detail_resp.json().get("texteloi", {})
                    if texte:
                        propositions.append({
                            "titre":       texte.get("titre"),
                            "type":        texte.get("type"),
                            "date":        texte.get("date"),
                            "signataires": texte.get("signataires"),
                            "contenu":     texte.get("contenu"),
                            "url_an":      texte.get("source"),
                            "url":         texte.get("url_nosdeputes"),
                            "source":      SOURCE_URL,
                        })

            # 2. Amendements
            amend_resp = await client.get(
                f"{SOURCE_URL}/recherche/{name.replace(' ', '+')}",
                params={"format": "json", "object_name": "Amendement"}
            )

            amendements = []
            if amend_resp.status_code == 200:
                results = amend_resp.json().get("results", [])
                for r in results[:10]:
                    url = r.get("document_url", "")
                    if not url:
                        continue
                    detail_resp = await client.get(url)
                    if detail_resp.status_code != 200:
                        continue
                    amend = detail_resp.json().get("amendement", {})
                    if amend:
                        amendements.append({
                            "sujet":       amend.get("sujet"),
                            "sort":        amend.get("sort"),
                            "date":        amend.get("date"),
                            "signataires": amend.get("signataires"),
                            "texte":       _strip_html(amend.get("texte")),
                            "expose":      _strip_html(amend.get("expose")),
                            "groupe":      amend.get("auteur_groupe_acronyme"),
                            "url_an":      amend.get("source"),
                            "url":         amend.get("url_nosdeputes"),
                            "source":      SOURCE_URL,
                        })

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
