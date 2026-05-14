import os
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import asyncio

from sources.wikipedia import get_wikipedia_info
from sources.nosdeputes import get_nosdeputes_info, get_votes_historique
from sources.hatvp import get_hatvp_info
from sources.news import get_news_info
from sources.casier import get_casier_politique_info
from sources.propositions import get_propositions_info
from sources.rne import get_rne_info
from sources.activite import get_activite_info
from sources.score import calculer_score
from sources.bord_politique import get_bord_politique
from cache import get_cache, set_cache, cache_stats

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="TranspaFrance API",
    description="API de transparence sur les personnalités politiques françaises",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://transpafrance-front.vercel.app", "http://localhost:5173", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "TranspaFrance API — utilisez /politician?name=Prénom+Nom"}

@app.get("/stats")
@limiter.limit("30/minute")
async def get_stats(request: Request):
    import redis as _redis, json as _json, os as _os
    try:
        r = _redis.from_url(_os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
        # D'abord depuis l'index dédié
        elus_avec_affaires = 0
        total_procedures   = 0
        for key in r.keys("politico:condamnations:*"):
            try:
                val = r.get(key)
                if val:
                    data = _json.loads(val)
                    nb   = data.get("nb", 0)
                    if nb > 0:
                        elus_avec_affaires += 1
                        total_procedures   += nb
            except Exception:
                continue

        # Fallback : lire depuis le cache politician si l'index est vide
        if elus_avec_affaires == 0:
            for key in r.keys("politico:politician:*"):
                try:
                    val = r.get(key)
                    if not val:
                        continue
                    data  = _json.loads(val)
                    conds = data.get("resultats", {}).get("condamnations", {}).get("condamnations", [])
                    if conds:
                        elus_avec_affaires += 1
                        total_procedures   += len(conds)
                except Exception:
                    continue
        return {
            "deputes":             577,
            "senateurs":           348,
            "elus_avec_affaires":  elus_avec_affaires if elus_avec_affaires > 0 else None,
            "total_procedures":    total_procedures   if total_procedures   > 0 else None,
            "donnees_publiques":   "100%",
        }
    except Exception as e:
        return {
            "deputes":            577,
            "senateurs":          348,
            "elus_avec_affaires": None,
            "total_procedures":   None,
            "donnees_publiques":  "100%",
            "erreur":             str(e),
        }

# Index en mémoire chargé une fois au démarrage
_ELUS_INDEX: list[dict] = []

async def _charger_index_elus():
    """Charge tous les noms de députés et sénateurs depuis le RNE en mémoire."""
    import httpx as _httpx
    global _ELUS_INDEX
    RNE = "https://tabular-api.data.gouv.fr/api/resources/{}/data/"
    RESSOURCES = {"Député": "1ac42ff4-1336-44f8-a221-832039dbc142", "Sénateur": "b78f8945-509f-4609-a4a7-3048b8370479"}
    index = []
    try:
        async with _httpx.AsyncClient(timeout=15) as client:
            for label, rid in RESSOURCES.items():
                page = 1
                while True:
                    resp = await client.get(RNE.format(rid), params={"page_size": 200, "page": page})
                    if resp.status_code != 200:
                        break
                    data = resp.json().get("data", [])
                    if not data:
                        break
                    for row in data:
                        prenom = (row.get("Prénom de l'élu") or "").strip()
                        nom    = (row.get("Nom de l'élu") or "").strip()
                        if prenom and nom:
                            index.append({
                                "nom":         f"{prenom} {nom}",
                                "type_mandat": label,
                                "departement": row.get("Libellé du département") or "",
                            })
                    page += 1
                    if len(data) < 200:
                        break
        _ELUS_INDEX = index
        print(f"[INDEX] {len(_ELUS_INDEX)} élus chargés")
    except Exception as e:
        print(f"[INDEX] Erreur chargement: {e}")

@app.on_event("startup")
async def startup():
    asyncio.create_task(_charger_index_elus())

@app.get("/search")
@limiter.limit("120/minute")
async def search_elus(request: Request, q: str = Query(..., min_length=3)):
    q_norm = q.strip().lower()
    resultats = [
        e for e in _ELUS_INDEX
        if q_norm in e["nom"].lower()
    ][:10]
    return {"resultats": resultats}

@app.get("/debug-casier")
async def debug_casier(request: Request):
    import traceback, shutil
    chromium_path = shutil.which("chromium") or shutil.which("chromium-browser") or "introuvable"
    try:
        from sources.casier import get_casier_politique_info
        result = await asyncio.wait_for(get_casier_politique_info("marine le pen"), timeout=90)
        return {"chromium": chromium_path, "result": result}
    except Exception as e:
        return {"chromium": chromium_path, "erreur": str(e), "trace": traceback.format_exc()}

@app.get("/affaires")
@limiter.limit("30/minute")
async def get_affaires(request: Request):
    import redis as _redis, json as _json, os as _os
    try:
        r = _redis.from_url(_os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
        keys = r.keys("politico:condamnations:*")
        elus = []
        for key in keys:
            try:
                val = r.get(key)
                if not val:
                    continue
                data = _json.loads(val)
                nb = data.get("nb", 0)
                if nb > 0:
                    elus.append({
                        "nom":          data.get("nom", key.replace("politico:condamnations:", "").replace("_", " ").title()),
                        "nb":           nb,
                        "type_mandat":  data.get("type_mandat", ""),
                        "condamnations": data.get("condamnations", []),
                    })
            except Exception:
                continue
        elus.sort(key=lambda x: x["nb"], reverse=True)
        return {"elus": elus, "total": len(elus)}
    except Exception as e:
        return {"elus": [], "total": 0, "erreur": str(e)}

@app.get("/politician/votes")
@limiter.limit("30/minute")
async def get_politician_votes(
    request:   Request,
    name:      str = Query(..., description="Nom complet du député"),
    q:         str = Query("",  description="Mot-clé (ex: retraites, immigration)"),
    position:  str = Query("",  description="pour / contre / abstention"),
    page:      int = Query(1),
    page_size: int = Query(50),
):
    if not name or len(name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Nom invalide")

    cache_key = f"{name.strip()}:votes:{q}:{position}:{page}:{page_size}"
    cached = get_cache(cache_key, "votes")
    if cached:
        return cached

    result = await get_votes_historique(
        name=name.strip(), query=q, position=position,
        page=page, page_size=page_size,
    )
    if result.get("trouve"):
        set_cache(cache_key, result, "votes")
    return result


@app.get("/cache/stats")
@limiter.limit("10/minute")
async def get_cache_stats(request: Request):
    return cache_stats()

@app.get("/politician")
@limiter.limit("20/minute")
async def get_politician(
    request: Request,
    name:    str  = Query(..., description="Nom complet de la personnalité politique"),
    refresh: bool = Query(False, description="Forcer le rechargement depuis les sources")
):
    if not name or len(name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Le nom doit contenir au moins 3 caractères")

    name = name.strip()

    if not refresh:
        cached = get_cache(name, "politician")
        if cached:
            cached["cache"] = True
            return cached

    results = await asyncio.gather(
        get_wikipedia_info(name),
        get_nosdeputes_info(name),
        get_hatvp_info(name),
        get_news_info(name),
        get_casier_politique_info(name),
        get_propositions_info(name),
        get_rne_info(name),
        get_activite_info(name),
        return_exceptions=True
    )

    def safe(result):
        if isinstance(result, Exception):
            return {"erreur": str(result)}
        return result

    wikipedia    = safe(results[0])
    nosdeputes   = safe(results[1])
    hatvp        = safe(results[2])
    news         = safe(results[3])
    casier       = safe(results[4])
    propositions = safe(results[5])
    rne          = safe(results[6])
    activite     = safe(results[7])

    parti = wikipedia.get("parti") or nosdeputes.get("parti")

    mandats_rne = rne.get("mandats", [])
    type_mandat = "depute"
    for m in mandats_rne:
        if "Sénateur" in m.get("type", ""):
            type_mandat = "senateur"
            break

    # URLs spécifiques à la personne pour chaque source
    import unicodedata, re as _re
    def _slugify(s):
        s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
        return _re.sub(r"\s+", "-", _re.sub(r"[^a-z0-9\s]", "", s.lower().strip()))

    slug = _slugify(name)
    url_wikipedia  = wikipedia.get("source_url") or f"https://fr.wikipedia.org/wiki/{name.replace(' ', '_')}"
    url_nosdeputes = nosdeputes.get("source_url") or f"https://www.nosdeputes.fr/{slug}"
    url_hatvp      = hatvp.get("source_url") or f"https://www.hatvp.fr/consulter-les-declarations/?s={name.replace(' ', '+')}"
    url_casier = casier.get("source_url") or "https://casier-politique.fr"
    url_an     = nosdeputes.get("url_an")

    all_affaires = casier.get("condamnations", [])

    response = {
        "recherche": name,
        "cache":     False,
        "resultats": {
            "identite": {
                "nom":            wikipedia.get("nom"),
                "parti":          parti,
                "bord_politique": wikipedia.get("bord_politique") or get_bord_politique(parti),
                "naissance":      wikipedia.get("naissance") or rne.get("date_naissance"),
                "photo":          nosdeputes.get("photo") or wikipedia.get("photo"),
                "resume":         wikipedia.get("resume"),
                "profession":     rne.get("profession"),
                "source":         url_wikipedia,
            },
            "liens": {
                "wikipedia":  url_wikipedia,
                "nosdeputes": url_nosdeputes,
                "assemblee":  url_an,
                "hatvp":      url_hatvp,
                "casier":     url_casier,
            },
            "mandats": {
                "mandats_rne":     mandats_rne,
                "cumul_mandats":   rne.get("cumul_mandats") or nosdeputes.get("cumul_mandats"),
                "nombre_mandats":  rne.get("nombre_mandats") or nosdeputes.get("nombre_mandats"),
                "anciens_mandats": nosdeputes.get("anciens_mandats", []),
                "autres_mandats":  nosdeputes.get("autres_mandats", []),
                "mandat_debut":    nosdeputes.get("mandat_debut"),
                "mandat_fin":      nosdeputes.get("mandat_fin"),
                "groupe":          nosdeputes.get("groupe"),
                "source_rne":      rne.get("source_url"),
                "source_deputes":  url_nosdeputes,
            },
            "activite_parlementaire": {
                "stats_moyennes":   activite.get("stats_moyennes", {}),
                "stats_totales":    activite.get("stats_totales", {}),
                "periode":          activite.get("periode"),
                "votes":            nosdeputes.get("votes", []),
                "propositions_loi": propositions.get("propositions", []),
                "amendements":      propositions.get("amendements", []),
                "note":             activite.get("note"),
                "source_activite":  activite.get("source_url"),
                "source_votes":     url_nosdeputes,
                "source_props":     propositions.get("source_url"),
            },
            "indemnites": {
                "type_mandat":  type_mandat,
                "montants":     activite.get("indemnites", {}),
                "declarations": hatvp.get("declarations", []),
                "note":         "Montants légaux fixes — identiques pour tous les parlementaires du même type",
                "source_hatvp": url_hatvp,
            },
            "condamnations": {
                "trouve":        len(all_affaires) > 0,
                "condamnations": all_affaires,
                "source":        url_casier,
            },
            "affaires_et_condamnations_presse": {
                "articles": news.get("affaires", []),
                "note":     "Résultats issus de la presse",
                "source":   news.get("source_url"),
            },
            "actualites_recentes": {
                "articles": news.get("actualites", []),
                "source":   news.get("source_url"),
            },
        }
    }

    score = calculer_score(
        stats_moyennes = activite.get("stats_moyennes", {}),
        condamnations  = all_affaires,
        mandats_rne    = rne.get("mandats", []),
        hatvp_url      = hatvp.get("source_url", ""),
    )
    response["resultats"]["score"] = score

    set_cache(name, response, "politician")

    # Index condamnations pour /stats et /affaires
    try:
        import redis as _ri, json as _js, os as _os2
        _r = _ri.from_url(_os2.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
        _r.setex(
            f"politico:condamnations:{name.lower().replace(' ', '_')}",
            60 * 60 * 24 * 7,
            _js.dumps({"nb": len(all_affaires), "nom": name, "condamnations": all_affaires, "type_mandat": type_mandat}, ensure_ascii=False),
        )
    except Exception:
        pass

    return response


@app.get("/politicians")
@limiter.limit("60/minute")
async def get_politicians(
    request:     Request,
    type_mandat: str  = Query(None),
    parti:       str  = Query(None),
    bord:        str  = Query(None),
    page:        int  = Query(1),
    page_size:   int  = Query(50),
):
    from sources.bord_politique import get_bord_politique
    import httpx, redis as redis_lib, json as json_mod, asyncio as _asyncio

    RESSOURCES = {
        "depute":   "1ac42ff4-1336-44f8-a221-832039dbc142",
        "senateur": "b78f8945-509f-4609-a4a7-3048b8370479",
        "maire":    "2876a346-d50c-4911-934e-19ee07b0e503",
    }

    # Ressources croisées pour détecter le cumul par requête ciblée par nom
    RESSOURCES_CUMUL = {
        "senateur":                 "b78f8945-509f-4609-a4a7-3048b8370479",
        "depute":                   "1ac42ff4-1336-44f8-a221-832039dbc142",
        "europeen":                 "70957bb0-f19f-40c5-b97b-90b3d4d71f9e",
        "conseiller_regional":      "430e13f9-834b-4411-a1a8-da0b4b6e715c",
        "conseiller_departemental": "601ef073-d986-4582-8e1a-ed14dc857fba",
        "maire":                    "2876a346-d50c-4911-934e-19ee07b0e503",
    }

    BASE_URL = "https://tabular-api.data.gouv.fr/api/resources/{}/data/"

    if type_mandat and type_mandat in RESSOURCES:
        ressources = {type_mandat: RESSOURCES[type_mandat]}
    else:
        ressources = RESSOURCES

    try:
        r_cache = redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    except Exception:
        r_cache = None

    _sem = _asyncio.Semaphore(20)  # max 20 requêtes simultanées

    async def _check_cumul(client, nom_famille: str, prenom: str, type_principal: str) -> list:
        cache_key = f"politico:cumul_check:{nom_famille.lower()}:{prenom.lower()}"
        if r_cache:
            try:
                cached = r_cache.get(cache_key)
                if cached is not None:
                    return json_mod.loads(cached)
            except Exception:
                pass

        autres = {k: v for k, v in RESSOURCES_CUMUL.items() if k != type_principal}

        async def _search(label, rid):
            async with _sem:
                try:
                    resp = await client.get(
                        BASE_URL.format(rid),
                        params={"Nom de l'élu__exact": nom_famille, "page_size": 5},
                    )
                    if resp.status_code != 200:
                        return None
                    rows = resp.json().get("data", [])
                    for row in rows:
                        if (row.get("Prénom de l'élu") or "").strip().lower() == prenom.strip().lower():
                            return label
                except Exception:
                    pass
                return None

        results = await _asyncio.gather(*[_search(label, rid) for label, rid in autres.items()])
        types_trouves = [type_principal] + [r for r in results if r]

        if r_cache:
            try:
                r_cache.setex(cache_key, 86400, json_mod.dumps(types_trouves))
            except Exception:
                pass
        return types_trouves

    elus = []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Récupération de la page principale
            page_resps = await _asyncio.gather(*[
                client.get(BASE_URL.format(rid), params={"page_size": page_size, "page": page})
                for rid in ressources.values()
            ])

            # Construction de la liste d'élus à partir des réponses
            elus_raw = []
            for (label, rid), resp in zip(ressources.items(), page_resps):
                try:
                    if resp.status_code != 200:
                        continue
                    rows = resp.json().get("data", [])
                    for row in rows:
                        prenom      = row.get("Prénom de l'élu", "") or ""
                        nom_famille = row.get("Nom de l'élu", "") or ""
                        naiss       = row.get("Date de naissance", "") or ""
                        nom_complet = (prenom + " " + nom_famille).strip()
                        parti_elu   = row.get("Libellé du groupe politique", "") or ""
                        bord_elu    = get_bord_politique(parti_elu)

                        if parti and parti.lower() not in parti_elu.lower():
                            continue
                        if bord and bord_elu and bord.lower() not in bord_elu.lower():
                            continue

                        nb_condamnations = 0
                        condamne         = False
                        if r_cache:
                            try:
                                ck     = f"politico:condamnations:{nom_complet.lower().replace(' ', '_')}"
                                cached = r_cache.get(ck)
                                if cached:
                                    cond_data        = json_mod.loads(cached)
                                    nb_condamnations = cond_data.get("nb", 0)
                                    condamne         = nb_condamnations > 0
                            except Exception:
                                pass

                        elus_raw.append({
                            "nom":              nom_complet,
                            "prenom":           prenom.strip(),
                            "nom_famille":      nom_famille.strip(),
                            "type_mandat":      label,
                            "departement":      row.get("Libellé du département"),
                            "parti":            parti_elu,
                            "bord":             bord_elu,
                            "debut_mandat":     row.get("Date de début du mandat"),
                            "naissance":        naiss,
                            "nb_condamnations": nb_condamnations,
                            "condamne":         condamne,
                        })
                except Exception as e:
                    print(f"[POLITICIANS] Erreur {label}: {e}")
                    continue

            # Vérification cumul en parallèle — return_exceptions évite qu'une erreur vide la liste
            cumul_results = await _asyncio.gather(*[
                _check_cumul(client, e["nom_famille"], e["prenom"], e["type_mandat"])
                for e in elus_raw
            ], return_exceptions=True)

            for elu, types in zip(elus_raw, cumul_results):
                if isinstance(types, Exception):
                    types = [elu["type_mandat"]]
                elu["cumul_mandats"] = len(types) > 1
                elu["types_mandats"] = types
                elus.append(elu)

    except Exception as e:
        print(f"[POLITICIANS] Erreur: {e}")

    return {
        "total": len(elus),
        "page":  page,
        "elus":  elus,
    }


@app.get("/elus/code-postal/{code_postal}")
@limiter.limit("30/minute")
async def get_elus_par_code_postal(
    request:      Request,
    code_postal:  str,
):
    """Trouve tous les élus (député, sénateur, maire) d'un code postal ou numéro de département."""
    from sources.circonscription import get_elus_par_code_postal, get_elus_par_departement
    if not code_postal.isdigit():
        raise HTTPException(status_code=400, detail="Format invalide — entrez un code postal (75011) ou un numéro de département (75)")
    if len(code_postal) <= 3:
        return await get_elus_par_departement(code_postal.zfill(2))
    return await get_elus_par_code_postal(code_postal)
