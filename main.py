from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from sources.wikipedia import get_wikipedia_info
from sources.nosdeputes import get_nosdeputes_info
from sources.hatvp import get_hatvp_info
from sources.news import get_news_info
from sources.casier import get_casier_politique_info
from sources.propositions import get_propositions_info

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

@app.get("/politician")
async def get_politician(name: str = Query(..., description="Nom complet de la personnalité politique")):
    if not name or len(name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Le nom doit contenir au moins 3 caractères")

    name = name.strip()

    results = await asyncio.gather(
        get_wikipedia_info(name),
        get_nosdeputes_info(name),
        get_hatvp_info(name),
        get_news_info(name),
        get_casier_politique_info(name),
        get_propositions_info(name),
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

    return {
        "recherche": name,
        "resultats": {
            "identite": {
                "nom":            wikipedia.get("nom"),
                "parti":          wikipedia.get("parti") or nosdeputes.get("parti"),
                "bord_politique": wikipedia.get("bord_politique"),
                "naissance":      wikipedia.get("naissance"),
                "photo":          wikipedia.get("photo"),
                "resume":         wikipedia.get("resume"),
                "source":         wikipedia.get("source_url"),
            },
            "mandats": {
                "mandats_en_cours": nosdeputes.get("mandats_en_cours", []),
                "anciens_mandats":  nosdeputes.get("anciens_mandats", []),
                "autres_mandats":   nosdeputes.get("autres_mandats", []),
                "cumul_mandats":    nosdeputes.get("cumul_mandats"),
                "nombre_mandats":   nosdeputes.get("nombre_mandats"),
                "groupe":           nosdeputes.get("groupe"),
                "source":           nosdeputes.get("source_url"),
            },
            "activite_parlementaire": {
                "presences":        nosdeputes.get("presences"),
                "participations":   nosdeputes.get("participations"),
                "jetons":           nosdeputes.get("jetons"),
                "votes":            nosdeputes.get("votes", []),
                "propositions_loi": propositions.get("propositions", []),
                "amendements":      propositions.get("amendements", []),
                "source_votes":     nosdeputes.get("source_url"),
                "source_props":     propositions.get("source_url"),
            },
            "indemnites": {
                "declarations": hatvp.get("declarations", []),
                "source":       hatvp.get("source_url"),
            },
            "condamnations": {
                "trouve":        casier.get("trouve"),
                "condamnations": casier.get("condamnations", []),
                "source":        casier.get("source_url"),
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
