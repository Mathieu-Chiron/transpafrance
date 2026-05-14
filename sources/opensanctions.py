import httpx
import os

OS_API  = "https://api.opensanctions.org"
HEADERS = {"User-Agent": "PoliticianAPI/1.0 (contact@example.com)"}

DATASET_LABELS = {
    "eu_fsf":               "Liste de sanctions UE",
    "fr_tresor_gels_avoir": "Gel d'avoirs — Trésor français",
    "un_sc_sanctions":      "Sanctions Conseil de sécurité ONU",
    "eu_eeas_sanctions":    "Sanctions SEAE (UE)",
}


async def get_opensanctions_info(name: str, qid: str | None = None) -> dict:
    api_key = os.getenv("OPENSANCTIONS_API_KEY", "")
    headers = {**HEADERS}
    if api_key:
        headers["Authorization"] = f"ApiKey {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            entity    = None
            entity_id = None

            # 1. Recherche via QID Wikidata (plus précis)
            if qid:
                resp = await client.get(f"{OS_API}/entities/{qid}")
                if resp.status_code == 200:
                    entity    = resp.json()
                    entity_id = qid

            # 2. Fallback : recherche par nom
            if not entity:
                resp = await client.get(f"{OS_API}/search/default", params={
                    "q":      name,
                    "schema": "Person",
                    "limit":  3,
                })
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        entity    = results[0]
                        entity_id = entity.get("id")

            if not entity:
                return {"trouve": False, "affaires": [], "source_url": None}

            datasets   = entity.get("datasets", [])
            is_target  = entity.get("target", False)
            affaires   = []

            if is_target and datasets:
                for ds in datasets:
                    label = DATASET_LABELS.get(ds)
                    if not label:
                        continue  # ignorer les datasets hors périmètre France/EU
                    affaires.append({
                        "description": f"Inscrit sur : {label}",
                        "source":      "opensanctions",
                        "type":        "sanction",
                        "date":        None,
                        "statut":      "sanction active",
                        "url":         f"https://www.opensanctions.org/entities/{entity_id}/",
                    })

            return {
                "trouve":     len(affaires) > 0,
                "entity_id":  entity_id,
                "is_target":  is_target,
                "datasets":   datasets,
                "affaires":   affaires,
                "source_url": f"https://www.opensanctions.org/entities/{entity_id}/" if entity_id else None,
            }

    except Exception as e:
        return {"trouve": False, "erreur": str(e), "affaires": [], "source_url": None}
