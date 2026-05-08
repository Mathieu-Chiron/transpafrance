from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from sources.wikipedia import get_wikipedia_info
from sources.nosdeputes import get_nosdeputes_info
from sources.hatvp import get_hatvp_info
from sources.news import get_news_info
from sources.casier import get_casier_politique_info
from sources.propositions import get_propositions_info
from sources.rne import get_rne_info
from sources.activite import get_activite_info
from sources.bord_politique import get_bord_politique
from sources.groupes import get_groupes_mapping
from cache import get_cache, set_cache, cache_stats

app = FastAPI(
    title="Politician API",
    description="API de recherche d'informations sur les personnalités politiques françaises",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Politician API — utilisez /politician?name=Prénom+Nom"}

@app.get("/cache/stats")
def get_cache_stats():
    return cache_stats()

@app.get("/debug/groupes")
async def debug_groupes():
    dep, sen = await get_groupes_mapping()
    sample_dep = dict(list(dep.items())[:5])
    sample_sen = dict(list(sen.items())[:5])
    return {"deputes_count": len(dep), "senateurs_count": len(sen),
            "deputes_sample": sample_dep, "senateurs_sample": sample_sen}

@app.get("/politicians")
async def get_politicians(
    type_mandat: str  = Query(None, description="depute, senateur, maire, europeen"),
    parti:       str  = Query(None),
    bord:        str  = Query(None),
    page:        int  = Query(1),
    page_size:   int  = Query(50),
):
    from sources.bord_politique import get_bord_politique
    import httpx, redis as redis_lib, json as json_mod

    dep_groupes, sen_groupes = await get_groupes_mapping()

    RESSOURCES = {
        "depute":   "1ac42ff4-1336-44f8-a221-832039dbc142",
        "senateur": "b78f8945-509f-4609-a4a7-3048b8370479",
        "maire":    "2876a346-d50c-4911-934e-19ee07b0e503",
        "europeen": "70957bb0-f19f-40c5-b97b-90b3d4d71f9e",
    }

    # Pour les maires (34 637 entrées), on délègue la pagination à l'API externe.
    # Pour les autres types (<1000), on charge tout puis on filtre/pagine localement.
    LARGE = {"maire"}

    BASE_URL = "https://tabular-api.data.gouv.fr/api/resources/{}/data/"

    if type_mandat and type_mandat in RESSOURCES:
        ressources = {type_mandat: RESSOURCES[type_mandat]}
    else:
        ressources = RESSOURCES

    try:
        r_cache = redis_lib.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    except Exception:
        r_cache = None

    def build_elu(row, label):
        prenom      = row.get("Prénom de l'élu", "") or ""
        nom_famille = row.get("Nom de l'élu", "") or ""
        nom_complet = (prenom + " " + nom_famille).strip()
        parti_elu   = row.get("Libellé du groupe politique", "") or ""

        # Enrichissement depuis nosdeputes / sénat si le RNE n'a pas le groupe
        bord_elu = None
        if not parti_elu:
            key = f"{prenom.strip().lower()}|{nom_famille.strip().lower()}"
            if label == "depute":
                info = dep_groupes.get(key, {})
            elif label == "senateur":
                info = sen_groupes.get(key, {})
            else:
                info = {}
            parti_elu = info.get("parti") or ""
            bord_elu  = info.get("bord")  # bord déjà résolu par groupes.py

        if not bord_elu and parti_elu:
            bord_elu = get_bord_politique(parti_elu)

        nb_condamnations = None
        condamne         = None
        if r_cache:
            try:
                cache_key = f"politico:condamnations:{nom_complet.lower().replace(' ', '_')}"
                cached    = r_cache.get(cache_key)
                if cached:
                    cond_data        = json_mod.loads(cached)
                    nb_condamnations = cond_data.get("nb", 0)
                    condamne         = nb_condamnations > 0
                else:
                    nb_condamnations = 0
                    condamne         = False
            except Exception:
                pass

        return {
            "nom":              nom_complet,
            "prenom":           prenom,
            "nom_famille":      nom_famille,
            "type_mandat":      label,
            "departement":      row.get("Libellé du département"),
            "commune":          row.get("Libellé de la commune"),
            "parti":            parti_elu,
            "bord":             bord_elu,
            "debut_mandat":     row.get("Date de début du mandat"),
            "naissance":        row.get("Date de naissance"),
            "nb_condamnations": nb_condamnations,
            "condamne":         condamne,
        }

    async def fetch_all_pages(client, rid):
        """Charge toutes les pages d'un petit dataset en parallèle (BATCH=100)."""
        BATCH = 100
        resp0 = await client.get(BASE_URL.format(rid), params={"page_size": BATCH, "page": 1})
        if resp0.status_code != 200:
            return []
        data0     = resp0.json()
        api_total = data0.get("meta", {}).get("total", 0)
        rows      = list(data0.get("data", []))
        nb_pages  = (api_total + BATCH - 1) // BATCH
        if nb_pages > 1:
            resps = await asyncio.gather(*[
                client.get(BASE_URL.format(rid), params={"page_size": BATCH, "page": p})
                for p in range(2, nb_pages + 1)
            ], return_exceptions=True)
            for r in resps:
                if not isinstance(r, Exception) and r.status_code == 200:
                    rows.extend(r.json().get("data", []))
        return rows

    elus  = []
    total = 0

    # Petits datasets (depute, senateur, europeen) : toujours charger les 3
    # pour détecter les cumuls, puis filtrer par type demandé.
    SMALL = {k: v for k, v in RESSOURCES.items() if k not in LARGE}

    async with httpx.AsyncClient(timeout=30) as client:

        # ── Petits datasets ──────────────────────────────────────────────────
        try:
            fetches = await asyncio.gather(*[
                fetch_all_pages(client, rid) for rid in SMALL.values()
            ], return_exceptions=True)

            # Grouper par personne (prénom+nom normalisé) pour détecter le cumul
            persons = {}
            for label, rows in zip(SMALL.keys(), fetches):
                if isinstance(rows, Exception):
                    continue
                for row in rows:
                    prenom  = (row.get("Prénom de l'élu", "") or "").strip()
                    nom_f   = (row.get("Nom de l'élu", "") or "").strip()
                    key     = f"{prenom.lower()}|{nom_f.lower()}"
                    if key not in persons:
                        e = build_elu(row, label)
                        e["type_mandats"] = [label]
                        persons[key] = e
                    else:
                        if label not in persons[key]["type_mandats"]:
                            persons[key]["type_mandats"].append(label)

            # Filtre type_mandat : ne garder que ceux qui ont ce mandat
            small_elus = list(persons.values())
            if type_mandat and type_mandat in SMALL:
                small_elus = [e for e in small_elus if type_mandat in e["type_mandats"]]

            # Filtres bord / parti
            for e in small_elus:
                if parti and parti.lower() not in (e["parti"] or "").lower():
                    continue
                if bord and (not e["bord"] or bord.lower() not in e["bord"].lower()):
                    continue
                elus.append(e)

        except Exception as exc:
            print(f"[POLITICIANS] Erreur petits datasets: {exc}")

        # ── Maires (large dataset, pagination serveur) ───────────────────────
        if not type_mandat or type_mandat == "maire":
            try:
                resp = await client.get(
                    BASE_URL.format(RESSOURCES["maire"]),
                    params={"page_size": page_size, "page": page}
                )
                if resp.status_code == 200:
                    data   = resp.json()
                    total += data.get("meta", {}).get("total", 0)
                    for row in data.get("data", []):
                        e = build_elu(row, "maire")
                        e["type_mandats"] = ["maire"]
                        if parti and parti.lower() not in (e["parti"] or "").lower():
                            continue
                        elus.append(e)
            except Exception as exc:
                print(f"[POLITICIANS] Erreur maire: {exc}")

    # Pagination locale pour les petits datasets
    if type_mandat != "maire" and not (not type_mandat):
        total = len(elus)
        start = (page - 1) * page_size
        elus  = elus[start:start + page_size]
    elif type_mandat is None:
        # Tous les types : petits datasets paginés localement + maires côté serveur
        small_part = [e for e in elus if "maire" not in e["type_mandats"]]
        maire_part = [e for e in elus if "maire" in e["type_mandats"]]
        total     += len(small_part)
        start      = (page - 1) * page_size
        small_part = small_part[start:start + page_size]
        elus       = small_part + maire_part

    return {
        "total": total,
        "page":  page,
        "elus":  elus,
    }


@app.get("/politician")
async def get_politician(
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
            return {}
        return result

    wikipedia    = safe(results[0])
    nosdeputes   = safe(results[1])
    hatvp        = safe(results[2])
    news         = safe(results[3])
    casier       = safe(results[4])
    propositions = safe(results[5])
    rne          = safe(results[6])
    activite     = safe(results[7])

    groupe_parlementaire = nosdeputes.get("groupe")
    parti = wikipedia.get("parti") or nosdeputes.get("parti") or groupe_parlementaire

    mandats_rne  = rne.get("mandats", [])
    type_mandat  = "depute"
    for m in mandats_rne:
        if "Sénateur" in m.get("type", ""):
            type_mandat = "senateur"
            break

    response = {
        "recherche": name,
        "cache":     False,
        "resultats": {
            "identite": {
                "nom":                 wikipedia.get("nom"),
                "parti":               parti,
                "groupe_parlementaire": groupe_parlementaire,
                "bord_politique":      wikipedia.get("bord_politique") or get_bord_politique(parti) or get_bord_politique(groupe_parlementaire),
                "naissance":           wikipedia.get("naissance") or rne.get("date_naissance"),
                "photo":               wikipedia.get("photo"),
                "resume":              wikipedia.get("resume"),
                "profession":          rne.get("profession"),
                "source":              wikipedia.get("source_url"),
            },
            "mandats": {
                "mandats_rne":     mandats_rne,
                "cumul_mandats":   rne.get("cumul_mandats") or nosdeputes.get("cumul_mandats"),
                "nombre_mandats":  rne.get("nombre_mandats") or nosdeputes.get("nombre_mandats"),
                "anciens_mandats": nosdeputes.get("anciens_mandats", []),
                "autres_mandats":  nosdeputes.get("autres_mandats", []),
                "groupe":          nosdeputes.get("groupe"),
                "source_rne":      rne.get("source_url"),
                "source_deputes":  nosdeputes.get("source_url"),
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
                "source_votes":     nosdeputes.get("source_url"),
                "source_props":     propositions.get("source_url"),
            },
            "indemnites": {
                "type_mandat":  type_mandat,
                "montants":     activite.get("indemnites", {}),
                "declarations": hatvp.get("declarations", []),
                "note":         "Montants légaux fixes — identiques pour tous les parlementaires du même type",
                "source_hatvp": hatvp.get("source_url"),
            },
            "condamnations": {
                "trouve":        casier.get("trouve"),
                "condamnations": casier.get("condamnations", []),
                "source_url":    casier.get("source_url"),
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

    set_cache(name, response, "politician")
    return response
