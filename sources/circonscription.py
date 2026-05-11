import httpx
import asyncio

SOURCE_GEO = "https://geo.api.gouv.fr"
SOURCE_RNE = "https://tabular-api.data.gouv.fr/api/resources"

RNE_DEPUTES   = "1ac42ff4-1336-44f8-a221-832039dbc142"
RNE_SENATEURS = "b78f8945-509f-4609-a4a7-3048b8370479"
RNE_MAIRES    = "2876a346-d50c-4911-934e-19ee07b0e503"

async def get_elus_par_code_postal(code_postal: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:

            geo_resp = await client.get(
                f"{SOURCE_GEO}/communes",
                params={
                    "codePostal": code_postal,
                    "fields":     "nom,code,codeDepartement",
                    "format":     "json",
                }
            )

            if geo_resp.status_code != 200 or not geo_resp.json():
                return {"trouve": False, "erreur": "Code postal introuvable"}

            communes     = geo_resp.json()
            commune      = communes[0]
            dept_code    = commune.get("codeDepartement")
            code_commune = commune.get("code")
            nom_commune  = commune.get("nom")

            # Retire le zéro du département dans le code commune
            # ex: "69123" -> "69123" mais "01001" -> "1001"
            code_commune_court = str(int(code_commune)) if code_commune.isdigit() else code_commune

            results = await asyncio.gather(
                _chercher_par_dept(client, RNE_DEPUTES,   dept_code, "Député"),
                _chercher_par_dept(client, RNE_SENATEURS, dept_code, "Sénateur"),
                _chercher_maires(client, code_commune_court, nom_commune),
            )

            deputes   = results[0]
            senateurs = results[1]
            maires    = results[2]

            return {
                "trouve":       True,
                "code_postal":  code_postal,
                "commune":      nom_commune,
                "departement":  dept_code,
                "deputes":      deputes,
                "senateurs":    senateurs,
                "maires":       maires,
                "total":        len(deputes) + len(senateurs) + len(maires),
                "source_url":   SOURCE_RNE,
            }

    except Exception as e:
        return {"trouve": False, "erreur": str(e)}


async def _chercher_par_dept(client, ressource_id: str, dept_code: str, label: str) -> list:
    try:
        resp = await client.get(
            f"{SOURCE_RNE}/{ressource_id}/data/",
            params={
                "Code du département__exact": dept_code,
                "page_size": 30,
            }
        )
        if resp.status_code != 200:
            return []

        elus = []
        for row in resp.json().get("data", []):
            prenom      = row.get("Prénom de l'élu", "") or ""
            nom_famille = row.get("Nom de l'élu", "") or ""
            elus.append({
                "nom":          (prenom + " " + nom_famille).strip(),
                "prenom":       prenom,
                "nom_famille":  nom_famille,
                "type_mandat":  label,
                "departement":  row.get("Libellé du département"),
                "debut_mandat": row.get("Date de début du mandat"),
                "naissance":    row.get("Date de naissance"),
            })
        return elus

    except Exception:
        return []


async def _chercher_maires(client, code_commune: str, nom_commune: str) -> list:
    try:
        resp = await client.get(
            f"{SOURCE_RNE}/{RNE_MAIRES}/data/",
            params={
                "Code de la commune__exact": code_commune,
                "page_size": 5,
            }
        )

        if resp.status_code != 200:
            return []

        elus = []
        for row in resp.json().get("data", []):
            prenom      = row.get("Prénom de l'élu", "") or ""
            nom_famille = row.get("Nom de l'élu", "") or ""
            elus.append({
                "nom":          (prenom + " " + nom_famille).strip(),
                "prenom":       prenom,
                "nom_famille":  nom_famille,
                "type_mandat":  "Maire",
                "commune":      row.get("Libellé de la commune") or nom_commune,
                "debut_mandat": row.get("Date de début du mandat"),
                "naissance":    row.get("Date de naissance"),
            })
        return elus

    except Exception:
        return []
