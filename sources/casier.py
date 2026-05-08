import asyncio
from playwright.async_api import async_playwright

SOURCE_URL = "https://casier-politique.fr"

async def _scraper_toutes_pages(name: str) -> list:
    """Parcourt toutes les pages de casier-politique.fr pour trouver le nom."""
    nom_lower = name.lower()
    condamnations = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(8000)

        try:
            await page.goto(SOURCE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)

            # Récupère le nombre total de pages
            nb_pages = 16  # valeur par défaut
            try:
                boutons_num = await page.query_selector_all("button, span")
                nums = []
                for b in boutons_num:
                    t = await b.inner_text()
                    if t.strip().isdigit() and 1 <= int(t.strip()) <= 50:
                        nums.append(int(t.strip()))
                if nums:
                    nb_pages = max(nums)
            except Exception:
                pass

            print(f"[CASIER] {nb_pages} pages détectées")

            # Scrape page 1
            condamnations += await _extraire_condamnations_page(page, nom_lower)

            # Scrape pages suivantes
            for num_page in range(2, nb_pages + 1):
                try:
                    # Trouve et clique sur le bouton de la page
                    clique = False
                    boutons = await page.query_selector_all("button, span, a")
                    for b in boutons:
                        t = (await b.inner_text()).strip()
                        if t == str(num_page):
                            await b.click()
                            await page.wait_for_timeout(1500)
                            clique = True
                            break

                    if not clique:
                        print(f"[CASIER] Impossible de cliquer page {num_page}")
                        continue

                    resultats = await _extraire_condamnations_page(page, nom_lower)
                    condamnations += resultats

                    # Si on a trouvé des résultats on continue quand même
                    # (la personne peut avoir plusieurs condamnations sur pages différentes)

                except Exception as e:
                    print(f"[CASIER] Erreur page {num_page}: {e}")
                    continue

        except Exception as e:
            print(f"[CASIER] Erreur générale: {e}")
        finally:
            await browser.close()

    return condamnations


async def _extraire_condamnations_page(page, nom_lower: str) -> list:
    """Extrait les condamnations d'une page pour un nom donné."""
    condamnations = []
    try:
        texte = await page.evaluate("document.body.innerText")
        lignes = texte.split("\n")

        i = 0
        while i < len(lignes):
            if nom_lower in lignes[i].lower():
                bloc = [l.strip() for l in lignes[i:i+10] if l.strip()]
                if bloc:
                    condamnations.append({
                        "description": " | ".join(bloc),
                        "source":      "casier-politique.fr",
                        "url":         SOURCE_URL,
                    })
                i += 10
            else:
                i += 1
    except Exception as e:
        print(f"[CASIER] Erreur extraction: {e}")

    return condamnations


async def get_casier_politique_info(name: str) -> dict:
    try:
        condamnations = await asyncio.wait_for(
            _scraper_toutes_pages(name),
            timeout=120  # 2 minutes max pour 16 pages
        )

        return {
            "trouve":        len(condamnations) > 0,
            "condamnations": condamnations,
            "note":          "Source : casier-politique.fr — base de données des condamnations politiques",
            "source_url":    SOURCE_URL,
        }

    except asyncio.TimeoutError:
        return {
            "trouve":        False,
            "note":          "Timeout — casier-politique.fr trop lent",
            "condamnations": [],
            "source_url":    SOURCE_URL,
        }
    except Exception as e:
        return {
            "trouve":        False,
            "erreur":        str(e),
            "condamnations": [],
            "source_url":    SOURCE_URL,
        }
