import httpx
import os
from dotenv import load_dotenv

load_dotenv()

SOURCE_URL = "https://newsapi.org"
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

MOTS_CLES_AFFAIRES = [
    "condamné", "condamnation", "mise en examen", "mis en examen",
    "jugement", "procès", "affaire", "soupçon", "enquête judiciaire",
    "garde à vue", "perquisition", "corruption", "détournement",
    "fraude", "escroquerie", "abus de bien social"
]

async def get_news_info(name: str) -> dict:
    if not NEWSAPI_KEY:
        return {
            "trouve":     False,
            "note":       "Ajoutez NEWSAPI_KEY dans votre fichier .env pour activer cette source (gratuit sur newsapi.org)",
            "affaires":   [],
            "actualites": [],
            "source_url": SOURCE_URL,
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:

            actu_resp = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        f'"{name}"',
                    "language": "fr",
                    "sortBy":   "publishedAt",
                    "pageSize": 10,
                    "apiKey":   NEWSAPI_KEY,
                }
            )

            articles_bruts = []
            if actu_resp.status_code == 200:
                articles_bruts = actu_resp.json().get("articles", [])

            actualites = []
            affaires   = []

            for art in articles_bruts:
                titre       = (art.get("title") or "").lower()
                description = (art.get("description") or "").lower()
                contenu     = titre + " " + description

                article_formate = {
                    "titre":       art.get("title"),
                    "description": art.get("description"),
                    "source":      art.get("source", {}).get("name"),
                    "date":        art.get("publishedAt", "")[:10],
                    "url":         art.get("url"),
                }

                if any(mot in contenu for mot in MOTS_CLES_AFFAIRES):
                    affaires.append(article_formate)
                else:
                    actualites.append(article_formate)

            return {
                "trouve":     True,
                "actualites": actualites,
                "affaires":   affaires,
                "source_url": SOURCE_URL,
            }

    except Exception as e:
        return {"trouve": False, "erreur": str(e), "affaires": [], "actualites": [], "source_url": SOURCE_URL}
