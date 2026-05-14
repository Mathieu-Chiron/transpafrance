import asyncio
import re
from playwright.async_api import async_playwright

SOURCE_URL = "https://casier-politique.fr"

RECOURS_RE = re.compile(r"\[.*?(appel|cassation|instance|cours|définitif).*?\]", re.IGNORECASE)

# Extraction DOM : cherche les div.author correspondant au nom,
# remonte au div.content parent pour parser l'entrée structurée.
_DOM_EXTRACTOR = """
(nom) => {
    const results = [];
    document.querySelectorAll('div.author').forEach(el => {
        if (!el.textContent.trim().toLowerCase().includes(nom)) return;

        const content = el.closest('div.content');
        if (!content) return;

        const h4     = content.querySelector('h4');
        const party  = content.querySelector('a.party');
        const chips  = Array.from(content.querySelectorAll('.q-chip'))
                            .map(c => c.textContent.trim());

        // Description : dernier paragraphe hors header et titre
        const paras  = Array.from(content.querySelectorAll('p, .nicegui-markdown p'));
        const desc   = paras.map(p => p.textContent.trim()).filter(t => t.length > 20).join(' ');

        results.push({
            nom:     el.textContent.trim(),
            parti:   party  ? party.textContent.trim() : '',
            affaire: h4     ? h4.textContent.trim()    : '',
            chips:   chips,
            desc:    desc,
        });
    });
    return results;
}
"""


def _statut_from_affaire(affaire: str) -> str:
    m = RECOURS_RE.search(affaire)
    if not m:
        return "définitif"
    t = m.group(1).lower()
    if "appel"     in t: return "en appel"
    if "cassation" in t: return "en cassation"
    if "instance"  in t or "cours" in t: return "1re instance"
    return "définitif"


def _build_entry(raw: dict) -> dict:
    affaire = raw.get("affaire", "")
    chips   = raw.get("chips", [])
    peine   = " ".join(c for c in chips if any(x in c for x in ["ans", "€", "mois", "💰", "🗳️"]))
    infraction = next((c for c in chips if not any(x in c for x in ["ans", "€", "💰", "🗳️", "mois"])), "")
    desc    = raw.get("desc", "")

    parts = [p for p in [affaire, peine, infraction, desc] if p]

    return {
        "description": " | ".join(parts),
        "nom":         raw.get("nom", ""),
        "parti":       raw.get("parti", ""),
        "affaire":     affaire,
        "peine":       peine,
        "infraction":  infraction,
        "statut":      _statut_from_affaire(affaire),
        "source":      "casier-politique.fr",
        "url":         SOURCE_URL,
    }


async def _scraper_toutes_pages(name: str) -> list:
    nom_lower = name.lower()
    condamnations = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        page.set_default_timeout(8000)

        try:
            await page.goto(SOURCE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)

            nb_pages = 16
            try:
                nums = []
                for b in await page.query_selector_all("button, span"):
                    t = await b.inner_text()
                    if t.strip().isdigit() and 1 <= int(t.strip()) <= 50:
                        nums.append(int(t.strip()))
                if nums:
                    nb_pages = max(nums)
            except Exception:
                pass

            print(f"[CASIER] {nb_pages} pages — recherche : {name}")

            for num_page in range(1, nb_pages + 1):
                try:
                    if num_page > 1:
                        clique = False
                        for b in await page.query_selector_all("button, span, a"):
                            if (await b.inner_text()).strip() == str(num_page):
                                await b.click()
                                await page.wait_for_timeout(1500)
                                clique = True
                                break
                        if not clique:
                            continue

                    # Extraction DOM directe : valide tag div.author + div.content
                    raw_entries = await page.evaluate(_DOM_EXTRACTOR, nom_lower)
                    for raw in raw_entries:
                        entry = _build_entry(raw)
                        if entry["affaire"]:
                            condamnations.append(entry)
                            print(f"[CASIER] trouvé page {num_page} : {entry['affaire'][:60]}")

                except Exception as e:
                    print(f"[CASIER] Erreur page {num_page}: {e}")
                    continue

        except Exception as e:
            print(f"[CASIER] Erreur générale: {e}")
        finally:
            await browser.close()

    # Déduplique par affaire
    seen, unique = set(), []
    for c in condamnations:
        key = c["affaire"][:80]
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


async def get_casier_politique_info(name: str) -> dict:
    try:
        condamnations = await asyncio.wait_for(_scraper_toutes_pages(name), timeout=120)
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
