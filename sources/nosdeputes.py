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

            # Votes récents (20 derniers pour l'aperçu)
            votes_resp = await client.get(f"{SOURCE_URL}/{slug}/votes/json")
            votes = []
            if votes_resp.status_code == 200:
                for v in _to_list(votes_resp.json().get("votes"))[:20]:
                    vote    = v.get("vote", {})
                    scrutin = vote.get("scrutin", {})
                    votes.append({
                        "texte":           scrutin.get("titre"),
                        "position":        vote.get("position"),
                        "position_groupe": vote.get("position_groupe"),
                        "date":            scrutin.get("date"),
                        "sort":            scrutin.get("sort"),
                        "url":             scrutin.get("url_nosdeputes"),
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
                "photo":            f"{SOURCE_URL}/depute/photo/{slug}/120",
                "source_url":       fiche.get("url_nosdeputes") or f"{SOURCE_URL}/{slug}",
            }

    except Exception as e:
        return {"trouve": False, "erreur": str(e), "source_url": SOURCE_URL}


def _parse_vote(v: dict) -> dict:
    vote    = v.get("vote", {})
    scrutin = vote.get("scrutin", {})
    return {
        "texte":           scrutin.get("titre"),
        "position":        vote.get("position"),
        "position_groupe": vote.get("position_groupe"),
        "date":            scrutin.get("date"),
        "sort":            scrutin.get("sort"),
        "url":             scrutin.get("url_nosdeputes"),
        "numero":          scrutin.get("numero"),
        "type":            scrutin.get("type"),
    }


async def get_votes_historique(
    name:      str,
    query:     str  = "",
    position:  str  = "",
    page:      int  = 1,
    page_size: int  = 50,
) -> dict:
    """Retourne l'historique complet des votes d'un député avec filtre et pagination."""
    slug = _slugify(name)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(f"{SOURCE_URL}/{slug}/votes/json")
            if resp.status_code != 200:
                return {
                    "trouve": False,
                    "votes": [], "total": 0, "page": page, "page_size": page_size,
                    "legislature": "16e (2022–2024)",
                    "note": "Données non disponibles pour cet élu sur NosDéputés.fr",
                    "source_url": f"{SOURCE_URL}/{slug}",
                }

            tous = [_parse_vote(v) for v in _to_list(resp.json().get("votes"))]
            tous = [v for v in tous if v["texte"]]
            tous.sort(key=lambda v: v.get("date") or "", reverse=True)

            # Filtre mot-clé
            if query:
                q = query.lower()
                tous = [v for v in tous if q in (v["texte"] or "").lower()]

            # Filtre position (pour, contre, abstention)
            if position:
                tous = [v for v in tous if (v["position"] or "").lower() == position.lower()]

            total   = len(tous)
            debut   = (page - 1) * page_size
            page_votes = tous[debut: debut + page_size]

            return {
                "trouve":      True,
                "votes":       page_votes,
                "total":       total,
                "page":        page,
                "page_size":   page_size,
                "pages":       (total + page_size - 1) // page_size if total else 0,
                "legislature": "16e (2022–2024)",
                "note":        "17e législature (depuis juillet 2024) : données en attente de mise à jour par NosDéputés.fr",
                "source_url":  f"{SOURCE_URL}/{slug}/votes",
            }

    except Exception as e:
        return {
            "trouve": False, "erreur": str(e),
            "votes": [], "total": 0, "page": page, "page_size": page_size,
            "source_url": SOURCE_URL,
        }
