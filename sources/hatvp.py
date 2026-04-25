import httpx
from typing import Optional

SOURCE_URL = "https://www.hatvp.fr"

async def get_hatvp_info(name: str) -> dict:
    """
    HATVP ne propose pas d'API REST.
    Les données sont en open data CSV sur data.gouv.fr
    On retourne le lien direct vers la fiche de recherche.
    """
    try:
        # Construction de l'URL de recherche sur le site HATVP
        nom_encode = name.replace(" ", "+")
        url_recherche = f"{SOURCE_URL}/consulter-les-declarations/?s={nom_encode}"

        return {
            "trouve":   True,
            "note":     "HATVP ne propose pas d'API. Consultez directement la fiche via l'URL source.",
            "declarations": [],
            "source_url": url_recherche,
        }

    except Exception as e:
        return {"trouve": False, "erreur": str(e), "source_url": SOURCE_URL}
