import httpx
import asyncio

SOURCE_URL = "https://www.data.gouv.fr/datasets/repertoire-national-des-elus-1"

RESSOURCES = {
    "Sénateur":                 "b78f8945-509f-4609-a4a7-3048b8370479",
    "Député":                   "1ac42ff4-1336-44f8-a221-832039dbc142",
    "Maire":                    "2876a346-d50c-4911-934e-19ee07b0e503",
    "Député européen":          "70957bb0-f19f-40c5-b97b-90b3d4d71f9e",
    "Conseiller régional":      "430e13f9-834b-4411-a1a8-da0b4b6e715c",
    "Conseiller départemental": "601ef073-d986-4582-8e1a-ed14dc857fba",
}

BASE_URL = "https://tabular-api.data.gouv.fr/api/resources/{}/data/"

def _extraire_prenom_nom(name: str) -> tuple:
    """Retourne (prenom, nom) : 'Jerome Buisson' -> ('Jerome', 'BUISSON')"""
    parts = name.strip().split(" ")
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:]).upper()
    return "", name.upper()

async def _chercher(client, label: str, ressource_id: str, prenom: str, nom: str) -> list:
    try:
        params = {"Nom de l'élu__exact": nom}
        if prenom:
            params["Prénom de l'élu__exact"] = prenom
        resp = await client.get(BASE_URL.format(ressource_id), params=params)
        if resp.status_code != 200:
            return []
        rows = resp.json().get("data", [])
        return [(label, row) for row in rows]
    except Exception:
        return []

async def get_rne_info(name: str) -> dict:
    prenom, nom = _extraire_prenom_nom(name)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resultats = await asyncio.gather(*[
                _chercher(client, label, rid, prenom, nom)
                for label, rid in RESSOURCES.items()
            ])

            tous = [item for groupe in resultats for item in groupe]

            mandats = []
            premier = None
            for label, row in tous:
                if premier is None:
                    premier = row
                mandats.append({
                    "type":        label,
                    "departement": row.get("Libellé du département"),
                    "debut":       row.get("Date de début du mandat"),
                    "source":      SOURCE_URL,
                })

            return {
                "trouve":         len(mandats) > 0,
                "nom_officiel":   (premier.get("Prénom de l'élu", "") + " " + premier.get("Nom de l'élu", "")).strip() if premier else None,
                "date_naissance": premier.get("Date de naissance") if premier else None,
                "profession":     premier.get("Libellé de la catégorie socio-professionnelle") if premier else None,
                "mandats":        mandats,
                "cumul_mandats":  len(mandats) > 1,
                "nombre_mandats": len(mandats),
                "source_url":     SOURCE_URL,
            }

    except Exception as e:
        return {
            "trouve":         False,
            "erreur":         str(e),
            "mandats":        [],
            "source_url":     SOURCE_URL,
        }
