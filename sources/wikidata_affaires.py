import httpx

WD_API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "PoliticianAPI/1.0 (contact@example.com)"}

# Propriétés Wikidata pertinentes pour les affaires judiciaires
PROP_CONVICTED_OF = "P1399"  # condamné pour
PROP_START        = "P580"   # début
PROP_POINT_TIME   = "P585"   # date


async def _get_labels(qids: list, client: httpx.AsyncClient) -> dict:
    if not qids:
        return {}
    resp = await client.get(WD_API, params={
        "action":    "wbgetlabels",
        "ids":       "|".join(qids),
        "languages": "fr|en",
        "format":    "json",
    })
    labels = {}
    for qid, data in resp.json().get("entities", {}).items():
        lbls  = data.get("labels", {})
        label = (lbls.get("fr") or lbls.get("en") or {}).get("value") or qid
        labels[qid] = label
    return labels


async def _search_qid(name: str, client: httpx.AsyncClient) -> str | None:
    resp    = await client.get(WD_API, params={
        "action":   "wbsearchentities",
        "search":   name,
        "language": "fr",
        "type":     "item",
        "format":   "json",
        "limit":    5,
    })
    results = resp.json().get("search", [])
    # Préférer un résultat qui mentionne la politique dans la description
    for r in results:
        desc = (r.get("description") or "").lower()
        if any(w in desc for w in ["politi", "député", "ministre", "sénat", "président", "maire"]):
            return r["id"]
    return results[0]["id"] if results else None


def _extract_date(qualifiers: dict) -> str | None:
    for prop in [PROP_POINT_TIME, PROP_START]:
        snaks = qualifiers.get(prop, [])
        if snaks:
            t = snaks[0].get("datavalue", {}).get("value", {}).get("time", "")
            return t[1:11] if t else None  # "+2021-12-15T..." → "2021-12-15"
    return None


async def get_wikidata_affaires(name: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            qid = await _search_qid(name, client)
            if not qid:
                return {"trouve": False, "qid": None, "affaires": [], "source_url": None}

            resp   = await client.get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
            entity = resp.json().get("entities", {}).get(qid, {})
            claims = entity.get("claims", {})

            affaires  = []
            p1399_raw = claims.get(PROP_CONVICTED_OF, [])

            # Collecte les QID des infractions pour résoudre les libellés en une requête
            infraction_qids = [
                c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                for c in p1399_raw
                if isinstance(c.get("mainsnak", {}).get("datavalue", {}).get("value"), dict)
            ]
            labels = await _get_labels([q for q in infraction_qids if q], client)

            for claim, inf_qid in zip(p1399_raw, infraction_qids):
                if not inf_qid:
                    continue
                label  = labels.get(inf_qid, inf_qid)
                date   = _extract_date(claim.get("qualifiers", {}))
                # rank preferred = confirmé en appel, deprecated = annulé, normal = en cours
                rank   = claim.get("rank", "normal")
                statut = "définitif" if rank == "preferred" else "annulé" if rank == "deprecated" else "condamné"

                affaires.append({
                    "description": f"Condamné pour : {label}",
                    "source":      "wikidata",
                    "type":        "condamnation",
                    "date":        date,
                    "statut":      statut,
                    "url":         f"https://www.wikidata.org/wiki/{qid}",
                })

            return {
                "trouve":     len(affaires) > 0,
                "qid":        qid,
                "affaires":   affaires,
                "source_url": f"https://www.wikidata.org/wiki/{qid}",
            }

    except Exception as e:
        return {"trouve": False, "erreur": str(e), "qid": None, "affaires": [], "source_url": None}
