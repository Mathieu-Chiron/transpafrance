"""
Script à lancer une fois (puis périodiquement).
Parse toutes les condamnations de Casier Politique
et les indexe par nom dans Redis.
"""
import asyncio
import redis
import json
import re
from playwright.async_api import async_playwright

SOURCE_URL = "https://casier-politique.fr"
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Partis connus pour détecter les lignes de noms
PARTIS_CONNUS = {
    "LR", "RN", "PS", "LFI", "EELV", "LREM", "UMP", "UDI", "UDF",
    "PCF", "PC", "PRG", "MoDem", "DVG", "DVD", "DVC", "FN", "MPF",
    "RPR", "RPR/UMP/LR", "LS", "RE", "REN", "HOR", "SOC", "GDR",
    "MODEM", "Reconquête", "NPA", "LO", "POI", "MRC", "PRV"
}

def _est_parti(ligne: str) -> bool:
    """Détecte si une ligne est un nom de parti."""
    return (
        ligne in PARTIS_CONNUS or
        re.match(r'^[A-Z]{2,6}(/[A-Z]{2,6})*$', ligne) is not None or
        any(p in ligne for p in ["RPR", "UMP", "LR", "FN", "RN", "PS", "LFI"])
    )

def _est_nom(ligne: str) -> bool:
    """Détecte si une ligne est probablement un nom de personne."""
    if len(ligne) < 3 or len(ligne) > 60:
        return False
    if any(c in ligne for c in ["€", "💰", "🗳", "⌛", "arrow", "keyboard"]):
        return False
    if ligne[0].isdigit():
        return False
    if ligne in ["Tri", "Date", "Tous", "appel", "cassation", "definitif"]:
        return False
    # Un nom contient au moins une majuscule et des lettres
    return bool(re.match(r'^[A-ZÀ-Ü][a-zA-ZÀ-ü\s\-\']+$', ligne))

async def _scraper_page(page, num_page: int) -> list:
    """Extrait les condamnations structurées d'une page."""
    condamnations = []

    texte  = await page.evaluate("document.body.innerText")
    lignes = [l.strip() for l in texte.split("\n") if l.strip()]

    # Trouve le début des données (après keyboard_arrow_right)
    debut = 0
    for i, l in enumerate(lignes):
        if l == "keyboard_arrow_right":
            debut = i + 1
            break

    i = debut
    while i < len(lignes) - 2:
        ligne = lignes[i]

        # Détecte un nom suivi d'un parti
        if _est_nom(ligne) and i + 1 < len(lignes) and _est_parti(lignes[i + 1]):
            nom   = ligne
            parti = lignes[i + 1]

            # Récupère les détails de la condamnation
            details = []
            j = i + 2
            while j < len(lignes) and j < i + 12:
                l = lignes[j]
                # Arrête si on trouve un nouveau nom+parti
                if _est_nom(l) and j + 1 < len(lignes) and _est_parti(lignes[j + 1]):
                    break
                if l not in ["keyboard_arrow_left", "keyboard_arrow_right"] and not l.isdigit():
                    details.append(l)
                j += 1

            condamnations.append({
                "nom":         nom,
                "parti":       parti,
                "details":     details,
                "description": f"{nom} | {parti} | " + " | ".join(details[:5]),
                "source":      SOURCE_URL,
            })
            i = j
        else:
            i += 1

    return condamnations

async def main():
    print("[PRECALCUL] Démarrage...")
    index = {}  # nom_lower -> liste condamnations

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        await page.goto(SOURCE_URL, wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(3000)

        # Détecte nb pages
        nb_pages = 16
        try:
            boutons = await page.query_selector_all("button, span")
            nums = []
            for b in boutons:
                t = (await b.inner_text()).strip()
                if t.isdigit() and 1 <= int(t) <= 50:
                    nums.append(int(t))
            if nums:
                nb_pages = max(nums)
        except Exception:
            pass

        print(f"[PRECALCUL] {nb_pages} pages")

        for num_page in range(1, nb_pages + 1):
            if num_page > 1:
                try:
                    boutons = await page.query_selector_all("button, span, a")
                    for b in boutons:
                        t = (await b.inner_text()).strip()
                        if t == str(num_page):
                            await b.click()
                            await page.wait_for_timeout(1500)
                            break
                except Exception as e:
                    print(f"[PRECALCUL] Nav page {num_page}: {e}")
                    continue

            condamnations = await _scraper_page(page, num_page)
            print(f"[PRECALCUL] Page {num_page}/{nb_pages} — {len(condamnations)} condamnations")

            for c in condamnations:
                nom_lower = c["nom"].lower()
                if nom_lower not in index:
                    index[nom_lower] = []
                index[nom_lower].append(c)

        await browser.close()

    # Stockage Redis
    print(f"[PRECALCUL] Stockage de {len(index)} personnes dans Redis...")
    for nom_lower, conds in index.items():
        cache_key = f"politico:condamnations:{nom_lower.replace(' ', '_')}"
        r.setex(
            cache_key,
            60 * 60 * 24 * 7,  # 7 jours
            json.dumps({
                "nb":            len(conds),
                "condamnations": conds
            }, ensure_ascii=False)
        )

    print(f"[PRECALCUL] ✅ {len(index)} politiciens indexés")

asyncio.run(main())
