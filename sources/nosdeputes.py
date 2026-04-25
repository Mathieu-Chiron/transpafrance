import httpx
import unicodedata
import re
from typing import Optional

SOURCE_URL = "https://www.nosdeputes.fr"

HEADERS = {
    "User-Agent": "PoliticianAPI/1.0 (contact@example.com) python-httpx"
}

def _slugify(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"\s+", "-", name)
    return name

def _to_list(val) -> list:
    """Convertit None, dict ou list en list propre."""
    if not val:
        return []
    if isinstance(val, dict):
        return [val]
    return val

async def get_nosdeputes_info(name: str) -> dict:
    try:
        slug = _slugify(name)
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=HEADERS) as client:

            fiche_resp = await client.get(f"{SOURCE_URL}/{slug}/json")

            if fiche_resp.status_code != 200:
                return {"trouve": False, "source_url": SOURCE_URL}

            fiche = fiche_resp.json().get("depute") or fiche_resp.json().get("senateur") or {}

            if not fiche:
                return {"trouve": False, "source_url": SOURCE_URL}

            # Anciens mandats
            anciens_mandats = [
                m.get("mandat", "")
                for m in _to_list(fiche.get("anciens_mandats"))
            ]

            # Autres mandats en cours (maire, conseiller, etc.)
            autres_mandats = [
                m.get("mandat", "")
                for m in _to_list(fiche.get("autres_mandats"))
            ]

            # Responsabilités parlementaires en cours
            responsabilites = [
                {
                    "organisme": r.get("responsabilite", {}).get("organisme"),
                    "fonction":  r.get("responsabilite", {}).get("fonction"),
                    "debut":     r.get("responsabilite", {}).get("debut_fonction"),
                }
                for r in _to_list(fiche.get("responsabilites"))
            ]

            # Cumul = député + autre mandat en cours
            cumul = len(autres_mandats) > 0

            # Groupe et parti
            groupe = fiche.get("groupe", {})
            if isinstance(groupe, dict):
                groupe_nom = groupe.get("organisme")
            else:
                groupe_nom = None

            # Votes récents
            votes_resp = await client.get(f"{SOURCE_URL}/{slug}/votes/json")
            votes = []
            if votes_resp.status_code == 200:
                for v in _to_list(votes_resp.json().get("votes"))[:10]:
                    vote    = v.get("vote", {})
                    scrutin = vote.get("scrutin", {})
                    votes.append({
                        "texte":          scrutin.get("titre"),
                        "position":       vote.get("position"),
                        "position_groupe": vote.get("position_groupe"),
                        "date":           scrutin.get("date"),
                        "sort":           scrutin.get("sort"),
                        "url":            scrutin.get("url_nosdeputes"),
                    })

            stats = fiche.get("statistiques") or {}

            return {
                "trouve":           True,
                "nom":              fiche.get("nom"),
                "parti":            fiche.get("parti_ratt_financier") or groupe_nom,
                "groupe":           groupe_nom or fiche.get("groupe_sigle"),
                "responsabilites":  responsabilites,
                "anciens_mandats":  anciens_mandats,
                "autres_mandats":   autres_mandats,
                "cumul_mandats":    cumul,
                "mandat_debut":     fiche.get("mandat_debut"),
                "mandat_fin":       fiche.get("mandat_fin"),
                "ancien_depute":    bool(fiche.get("ancien_depute")),
                "presences":        stats.get("presences_commission") or stats.get("presences_hemicycle"),
                "participations":   stats.get("participations_hemicycle"),
                "jetons":           stats.get("remu_moyenne"),
                "votes":            votes,
                "propositions_loi": [],
                "url_an":           fiche.get("url_an"),
                "source_url":       fiche.get("url_nosdeputes") or f"{SOURCE_URL}/{slug}",
            }

    except Exception as e:
        return {"trouve": False, "erreur": str(e), "source_url": SOURCE_URL}
