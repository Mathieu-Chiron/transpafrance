import httpx
import re
import unicodedata
import json
import time

SOURCE_URL = "https://www.hatvp.fr"
_DECLARANTS_CACHE: list = []
_DECLARANTS_TS: float = 0.0
_DECLARANTS_TTL = 86400  # 24h


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


async def _get_declarants() -> list:
    global _DECLARANTS_CACHE, _DECLARANTS_TS
    if _DECLARANTS_CACHE and (time.time() - _DECLARANTS_TS) < _DECLARANTS_TTL:
        return _DECLARANTS_CACHE
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.hatvp.fr/wordpress/wp-content/themes/hatvp/data/infoDeclarant.js"
            )
            if resp.status_code != 200:
                return _DECLARANTS_CACHE
            raw = resp.text.replace("var data_source2 = ", "").rstrip("; \n")
            _DECLARANTS_CACHE = json.loads(raw)
            _DECLARANTS_TS = time.time()
    except Exception:
        pass
    return _DECLARANTS_CACHE


async def get_hatvp_info(name: str) -> dict:
    try:
        declarants = await _get_declarants()

        parts = _norm(name).split()

        best = None
        for d in declarants:
            nom_norm = _norm(d.get("nom", ""))
            if all(p in nom_norm for p in parts):
                best = d
                break

        if best:
            url_fiche = f"{SOURCE_URL}/fiche-nominative/?declarant={best['id']}"
        else:
            url_fiche = f"{SOURCE_URL}/consulter-les-declarations/?s={name.replace(' ', '+')}"

        return {
            "trouve":       best is not None,
            "declarant_id": best["id"] if best else None,
            "note":         "HATVP — Haute Autorité pour la transparence de la vie publique",
            "declarations": [],
            "source_url":   url_fiche,
        }

    except Exception as e:
        return {"trouve": False, "erreur": str(e), "source_url": SOURCE_URL}
