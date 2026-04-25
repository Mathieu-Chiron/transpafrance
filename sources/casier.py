import asyncio
from playwright.async_api import async_playwright

SOURCE_URL = "https://casier-politique.fr"

async def get_casier_politique_info(name: str) -> dict:
    """
    Scrape casier-politique.fr en cherchant le nom dans la liste des condamnations.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(SOURCE_URL)
            await page.wait_for_timeout(4000)

            # Récupère tout le texte visible
            texte = await page.evaluate("document.body.innerText")

            # Cherche le nom dans le texte
            nom_lower = name.lower()
            lignes = texte.split("\n")

            condamnations = []
            i = 0
            while i < len(lignes):
                ligne = lignes[i]
                if nom_lower in ligne.lower():
                    # Récupère les lignes suivantes pour le contexte
                    bloc = []
                    for j in range(i, min(i + 10, len(lignes))):
                        l = lignes[j].strip()
                        if l:
                            bloc.append(l)
                    condamnations.append({
                        "description": " | ".join(bloc),
                        "source":      SOURCE_URL,
                        "url":         SOURCE_URL,
                    })
                    i += 10
                else:
                    i += 1

            await browser.close()

            if not condamnations:
                # Tente de naviguer sur les pages suivantes
                condamnations = await _chercher_toutes_pages(name)

            return {
                "trouve":        len(condamnations) > 0,
                "condamnations": condamnations,
                "note":          "Source : casier-politique.fr — base de données des condamnations politiques",
                "source_url":    SOURCE_URL,
            }

    except Exception as e:
        return {
            "trouve":        False,
            "erreur":        str(e),
            "condamnations": [],
            "source_url":    SOURCE_URL,
        }


async def _chercher_toutes_pages(name: str) -> list:
    """Parcourt jusqu'à 16 pages pour trouver le nom."""
    condamnations = []
    nom_lower = name.lower()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(SOURCE_URL)
        await page.wait_for_timeout(4000)

        for num_page in range(2, 17):
            try:
                # Clique sur le numéro de page
                await page.get_by_text(str(num_page), exact=True).first.click()
                await page.wait_for_timeout(2000)

                texte = await page.evaluate("document.body.innerText")
                lignes = texte.split("\n")

                i = 0
                while i < len(lignes):
                    if nom_lower in lignes[i].lower():
                        bloc = []
                        for j in range(i, min(i + 10, len(lignes))):
                            l = lignes[j].strip()
                            if l:
                                bloc.append(l)
                        condamnations.append({
                            "description": " | ".join(bloc),
                            "source":      SOURCE_URL,
                            "url":         SOURCE_URL,
                        })
                        i += 10
                    else:
                        i += 1

                if condamnations:
                    break

            except Exception:
                continue

        await browser.close()

    return condamnations
