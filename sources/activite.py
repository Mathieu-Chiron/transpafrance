import httpx
import asyncio
from datetime import datetime

SOURCE_URL = "https://www.nosdeputes.fr"

HEADERS = {
    "User-Agent": "PoliticianAPI/1.0 (contact@example.com) python-httpx"
}

INDEMNITES = {
    "depute": {
        "brut_mensuel":          7637.39,
        "net_mensuel":           5953.34,
        "frais_mandat":          5950.00,
        "credit_collaborateurs": 11463.00,
        "source": "https://www.assemblee-nationale.fr/dyn/synthese/deputes-groupes-parlementaires/la-situation-materielle-du-depute"
    },
    "senateur": {
        "brut_mensuel":          7637.39,
        "net_mensuel":           5676.12,
        "frais_mandat":          6600.00,
        "credit_collaborateurs": 7548.10,
        "source": "https://www.senat.fr/connaitre-le-senat/role-et-fonctionnement/lindemnite-parlementaire.html"
    }
}

CHAMPS_STATS = [
    "semaines_presence",
    "commission_presences",
    "commission_interventions",
    "hemicycle_interventions",
    "hemicycle_interventions_courtes",
    "amendements_proposes",
    "amendements_adoptes",
    "amendements_signes",
    "questions_ecrites",
    "questions_orales",
    "propositions_ecrites",
    "propositions_signees",
    "rapports",
]

def _mois_a_tester() -> list:
    now = datetime.now()
    mois = []
    for i in range(1, 7):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        mois.append(f"{y}{m:02d}")
    mois += ["202312", "202311", "202310", "202309", "202307", "202306"]
    return list(dict.fromkeys(mois))  # déduplique

async def get_activite_info(name: str, type_mandat: str = "depute") -> dict:
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:

            stats_cumul   = {k: 0 for k in CHAMPS_STATS}
            mois_avec_donnees = 0
            mois_utilises     = []
            nom_lower         = name.lower()

            for mois in _mois_a_tester():
                if mois_avec_donnees >= 6:
                    break

                resp = await client.get(f"{SOURCE_URL}/synthese/{mois}/json")
                if resp.status_code != 200:
                    continue

                deputes = resp.json().get("deputes", [])
                trouve  = None

                for d in deputes:
                    dep = d.get("depute", {})
                    if nom_lower in dep.get("nom", "").lower():
                        trouve = dep
                        break

                if not trouve:
                    continue

                # Compte le mois même si activité faible
                mois_avec_donnees += 1
                mois_utilises.append(mois)
                for key in CHAMPS_STATS:
                    stats_cumul[key] += trouve.get(key, 0)

            if mois_avec_donnees == 0:
                return {
                    "trouve":     False,
                    "note":       "Aucune statistique disponible — données non encore publiées pour cette législature",
                    "stats":      {},
                    "indemnites": INDEMNITES.get(type_mandat, INDEMNITES["depute"]),
                    "source_url": SOURCE_URL,
                }

            stats_moyennes = {
                k: round(v / mois_avec_donnees, 1)
                for k, v in stats_cumul.items()
            }

            return {
                "trouve":         True,
                "periode":        f"{mois_avec_donnees} mois ({mois_utilises[-1]} → {mois_utilises[0]})",
                "stats_moyennes": stats_moyennes,
                "stats_totales":  stats_cumul,
                "indemnites":     INDEMNITES.get(type_mandat, INDEMNITES["depute"]),
                "note":           "Moyennes mensuelles — source NosDéputés.fr (16e législature 2022-2024)",
                "source_url":     SOURCE_URL,
            }

    except Exception as e:
        return {
            "trouve":     False,
            "erreur":     str(e),
            "stats":      {},
            "indemnites": INDEMNITES.get(type_mandat, INDEMNITES["depute"]),
            "source_url": SOURCE_URL,
        }
