"""
Précalcul bimensuel des fiches députés + sénateurs.
Lance les appels /politician?refresh=true pour chaque élu
afin de peupler le cache Redis avant que les utilisateurs ne cherchent.

Usage local :
    python precalcul_fiches.py

Via Railway Cron :
    python precalcul_fiches.py
    Planning : 0 3 1,15 * *  (1er et 15 du mois à 3h)
"""

import asyncio
import httpx
import time

RNE_BASE    = "https://tabular-api.data.gouv.fr/api/resources/{}/data/"
API_BASE    = "https://web-production-6c245.up.railway.app"
SEMAPHORE   = 5      # appels simultanés vers l'API
PAGE_SIZE   = 200    # max autorisé par tabular-api

RESSOURCES = {
    "Député":   "1ac42ff4-1336-44f8-a221-832039dbc142",
    "Sénateur": "b78f8945-509f-4609-a4a7-3048b8370479",
}


async def _fetch_elus(client: httpx.AsyncClient, label: str, rid: str) -> list[str]:
    """Récupère tous les noms depuis le RNE (pagination complète)."""
    noms   = []
    page   = 1
    total  = None

    while True:
        try:
            resp = await client.get(
                RNE_BASE.format(rid),
                params={"page_size": PAGE_SIZE, "page": page},
            )
            if resp.status_code != 200:
                print(f"[RNE] {label} page {page} — HTTP {resp.status_code}")
                break

            data  = resp.json()
            rows  = data.get("data", [])
            if total is None:
                total = data.get("meta", {}).get("total", "?")
                print(f"[RNE] {label} — {total} élus à charger")

            for row in rows:
                prenom = (row.get("Prénom de l'élu") or "").strip()
                nom    = (row.get("Nom de l'élu") or "").strip()
                if prenom and nom:
                    noms.append(f"{prenom} {nom}")

            if len(rows) < PAGE_SIZE:
                break
            page += 1

        except Exception as e:
            print(f"[RNE] Erreur {label} page {page}: {e}")
            break

    return noms


async def _precalculer(client: httpx.AsyncClient, sem: asyncio.Semaphore, nom: str, idx: int, total: int):
    async with sem:
        try:
            resp = await client.get(
                f"{API_BASE}/politician",
                params={"name": nom, "refresh": "true"},
                timeout=60,
            )
            status = "✅" if resp.status_code == 200 else f"❌ HTTP {resp.status_code}"
        except Exception as e:
            status = f"❌ {e}"

        print(f"[{idx}/{total}] {nom} — {status}")


async def main():
    t0 = time.time()
    print("=" * 55)
    print("  Précalcul fiches TranspaFrance")
    print("=" * 55)

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Récupérer tous les noms
        resultats = await asyncio.gather(*[
            _fetch_elus(client, label, rid)
            for label, rid in RESSOURCES.items()
        ])

    tous_les_noms = []
    for noms in resultats:
        tous_les_noms.extend(noms)

    # Dédoublonner (cumul possible entre les deux listes)
    tous_les_noms = list(dict.fromkeys(tous_les_noms))
    total = len(tous_les_noms)
    print(f"\n→ {total} élus uniques à précalculer\n")

    # 2. Précalculer chaque fiche
    sem = asyncio.Semaphore(SEMAPHORE)
    async with httpx.AsyncClient(timeout=60) as client:
        await asyncio.gather(*[
            _precalculer(client, sem, nom, i + 1, total)
            for i, nom in enumerate(tous_les_noms)
        ])

    duree = round(time.time() - t0)
    print(f"\n✅ Terminé en {duree // 60}m{duree % 60:02d}s — {total} fiches mises en cache")


if __name__ == "__main__":
    asyncio.run(main())
