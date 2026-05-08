import httpx
import asyncio
import time

_CACHE: dict = {"deputes": None, "senateurs": None, "ts": 0.0}
_TTL = 3600  # 1 heure

# Sigles des groupes sénatoriaux → nom complet + bord politique
SENAT_GROUPES = {
    "LR":     ("Les Républicains",                                      "Droite"),
    "SER":    ("Groupe Socialiste, Écologiste et Républicain",           "Gauche"),
    "RDSE":   ("Rassemblement Démocratique, Social et Européen",         "Centre gauche"),
    "UC":     ("Union Centriste",                                        "Centre droit"),
    "GEST":   ("Rassemblement des Démocrates, Progressistes",            "Centre"),
    "INDEP":  ("Les Indépendants",                                       "Centre droit"),
    "LIRT":   ("Libertés, Indépendants, Outre-mer et Territoires",      "Centre droit"),
    "CRCE":   ("Communiste Républicain Citoyen et Écologiste",           "Gauche radicale"),
    "CRCE-K": ("Communiste Républicain Citoyen et Écologiste",           "Gauche radicale"),
    "ESR":    ("Écologiste, Solidarité et Territoires",                  "Centre gauche"),
    "RN":     ("Rassemblement National",                                 "Extrême droite"),
    "NI":     ("Non-inscrit",                                            None),
}

# Sigles des groupes de l'Assemblée nationale → bord politique
AN_GROUPES = {
    "LFI":      "Gauche radicale",
    "GDR":      "Gauche radicale",
    "SOC":      "Gauche",
    "ECO":      "Centre gauche",
    "LIOT":     "Centre droit",
    "RE":       "Centre",
    "DEM":      "Centre",
    "HOR":      "Centre droit",
    "LR":       "Droite",
    "RN":       "Extrême droite",
    "REC":      "Extrême droite",
    "UDI":      "Centre droit",
    "NI":       None,
}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


async def _fetch_deputes() -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://www.nosdeputes.fr/deputes/json")
        if resp.status_code != 200:
            return {}
        mapping: dict = {}
        for item in resp.json().get("deputes", []):
            d      = item.get("depute", item)
            nom_f  = _norm(d.get("nom_de_famille", ""))
            prenom = _norm(d.get("prenom", ""))
            sigle  = d.get("groupe_sigle", "") or ""
            parti  = d.get("parti_ratt_financier") or sigle
            bord   = AN_GROUPES.get(sigle)
            if nom_f:
                key = f"{prenom}|{nom_f}"
                # Les entrées les plus récentes (ancien_depute=0) écrasent les anciennes
                if key not in mapping or not d.get("ancien_depute"):
                    mapping[key] = {"parti": parti, "sigle": sigle, "bord": bord}
        return mapping


async def _fetch_senateurs() -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://data.senat.fr/data/senateurs/ODSEN_GENERAL.json")
        if resp.status_code != 200:
            return {}
        raw = resp.json()
        # Le JSON du Sénat est enveloppé dans {"results": [...]}
        records = (
            raw if isinstance(raw, list)
            else raw.get("results", raw.get("data", raw.get("senateurs", [])))
        )
        mapping: dict = {}
        for row in records:
            if _norm(row.get("Etat", "")) != "actif":
                continue
            nom_f  = _norm(row.get("Nom_usuel", ""))
            prenom = _norm(row.get("Prenom_usuel", ""))
            sigle  = (row.get("Groupe_politique", "") or "").strip()
            nom_groupe, bord = SENAT_GROUPES.get(sigle, (sigle, None))
            if nom_f:
                mapping[f"{prenom}|{nom_f}"] = {"parti": nom_groupe, "sigle": sigle, "bord": bord}
        return mapping


async def get_groupes_mapping() -> tuple[dict, dict]:
    """Retourne (deputes_mapping, senateurs_mapping) avec cache 1h."""
    now = time.time()
    if _CACHE["deputes"] is None or (now - _CACHE["ts"]) > _TTL:
        dep, sen = await asyncio.gather(
            _fetch_deputes(),
            _fetch_senateurs(),
            return_exceptions=True,
        )
        _CACHE["deputes"]   = dep if isinstance(dep, dict) else {}
        _CACHE["senateurs"] = sen if isinstance(sen, dict) else {}
        _CACHE["ts"]        = now
    return _CACHE["deputes"], _CACHE["senateurs"]
