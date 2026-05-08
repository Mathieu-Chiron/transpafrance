import asyncio
from playwright.async_api import async_playwright

SOURCE_URL = "https://casier-politique.fr"

async def _scrape_avec_timeout(name: str) -> list:
    """Scrape avec timeout strict de 20 secondes."""
    nom_lower = name.lower()
    condamnations = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(8000)

        try:
            await page.goto(SOURCE_URL, wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(2000)

            texte = await page.evaluate("document.body.innerText")
            lignes = texte.split("\n")

            i = 0
            while i < len(lignes):
                if nom_lower in lignes[i].lower():
                    bloc = [l.strip() for l in lignes[i:i+10] if l.strip()]
                    condamnations.append({
                        "description": " | ".join(bloc),
                        "source":      SOURCE_URL,
                        "url":         SOURCE_URL,
                    })
                    i += 10
                else:
                    i += 1

        except Exception as e:
            print(f"[CASIER] Erreur page 1: {e}")
        finally:
            await browser.close()

    return condamnations


async def get_casier_politique_info(name: str) -> dict:
    try:
        # Timeout global de 25 secondes
        condamnations = await asyncio.wait_for(
            _scrape_avec_timeout(name),
            timeout=25
        )

        return {
            "trouve":        len(condamnations) > 0,
            "condamnations": condamnations,
            "note":          "Source : casier-politique.fr",
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
