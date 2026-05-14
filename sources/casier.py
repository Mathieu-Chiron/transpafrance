import asyncio
import re
from playwright.async_api import async_playwright

SOURCE_URL = "https://casier-politique.fr"

# Partis politiques connus — indique qu'une ligne est la 2e ligne d'une entrée
PARTIS = re.compile(
    r"^(FN|RN|FN/RN|LR|PS|LFI|EELV|UDF|LREM|PC|R!|UDI|PRG|MoDem|DVD|DVG|"
    r"divers|sans étiquette|MNR|MPF|RPR|RPR/UMP|UMP|NUPES|RE|HOR|SOC|GDR|"
    r"FI|PRV|RCV|DLF|UPR|RéconciliationN|FPF|FédérationN|LO|NPA|EXG)$",
    re.IGNORECASE,
)

RECOURS_RE = re.compile(r"\[.*?(appel|cassation|instance|cours|définitif).*?\]", re.IGNORECASE)
ANNEE_RE   = re.compile(r"^(19|20)\d{2}\s+Affaire")


def _parse_entries(lignes: list, nom_lower: str) -> list:
    """
    Parse structuré : une entrée commence quand une ligne correspond au nom recherché
    ET que la ligne suivante ressemble à un parti politique.
    Évite les faux positifs où le nom est mentionné dans une description.
    """
    entries = []
    i = 0
    while i < len(lignes):
        ligne = lignes[i].strip()
        # Vérifie si cette ligne contient le nom ET que la suivante est un parti
        if nom_lower in ligne.lower():
            next_ligne = lignes[i + 1].strip() if i + 1 < len(lignes) else ""
            if PARTIS.match(next_ligne):
                # C'est bien une entrée dont le sujet est le nom recherché
                bloc = []
                j = i
                # Collecte jusqu'à la prochaine entrée (ligne suivante qui ressemble à un nom + parti)
                while j < len(lignes):
                    l = lignes[j].strip()
                    if not l:
                        j += 1
                        continue
                    # Arrête au prochain nom différent (ligne suivie d'un parti)
                    if j > i and j + 1 < len(lignes) and PARTIS.match(lignes[j + 1].strip()):
                        # Vérifie que ce n'est pas encore notre nom
                        if nom_lower not in l.lower():
                            break
                    bloc.append(l)
                    j += 1

                if bloc:
                    parsed = _build_entry(bloc)
                    if parsed:
                        entries.append(parsed)
                i = j
                continue
        i += 1
    return entries


def _build_entry(bloc: list) -> dict | None:
    """Construit un dict structuré à partir d'un bloc de lignes."""
    if len(bloc) < 3:
        return None

    nom    = bloc[0]
    parti  = bloc[1] if len(bloc) > 1 else ""

    # Trouve la ligne "Année Affaire xxx"
    affaire = ""
    statut  = "définitif"
    for l in bloc[2:]:
        if ANNEE_RE.match(l):
            affaire = l
            m = RECOURS_RE.search(l)
            if m:
                txt = m.group(1).lower()
                if "appel"    in txt: statut = "en appel"
                elif "cassation" in txt: statut = "en cassation"
                elif "instance"  in txt or "cours" in txt: statut = "1re instance"
            break

    if not affaire:
        return None

    # Collecte peine, infraction, description
    idx_affaire = next((k for k, l in enumerate(bloc) if l == affaire), -1)
    reste = bloc[idx_affaire + 1:] if idx_affaire >= 0 else []

    peine       = " ".join(l for l in reste if any(c in l for c in ["ans", "€", "mois", "💰", "🗳️"]) and len(l) < 80)
    infraction  = next((l for l in reste if len(l) > 5 and not any(c in l for c in ["ans", "€", "💰", "🗳️"]) and not l.startswith("Condamn") and len(l) < 60), "")
    description = next((l for l in reste if l.startswith("Condamn") or (len(l) > 60 and l[0].isupper())), "")

    parts = [p for p in [affaire, peine, infraction, description] if p]

    return {
        "description": " | ".join(parts),
        "nom":         nom,
        "parti":       parti,
        "affaire":     affaire,
        "peine":       peine,
        "infraction":  infraction,
        "statut":      statut,
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

            # Détecte le nombre de pages
            nb_pages = 16
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

            print(f"[CASIER] {nb_pages} pages — recherche : {name}")

            for num_page in range(1, nb_pages + 1):
                try:
                    if num_page > 1:
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
                            continue

                    texte  = await page.evaluate("document.body.innerText")
                    lignes = [l.strip() for l in texte.split("\n") if l.strip()]
                    trouve = _parse_entries(lignes, nom_lower)

                    if trouve:
                        print(f"[CASIER] {len(trouve)} entrée(s) page {num_page}")
                        condamnations += trouve

                except Exception as e:
                    print(f"[CASIER] Erreur page {num_page}: {e}")
                    continue

        except Exception as e:
            print(f"[CASIER] Erreur générale: {e}")
        finally:
            await browser.close()

    # Déduplique par affaire
    seen   = set()
    unique = []
    for c in condamnations:
        key = c.get("affaire", c["description"])[:80]
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


async def get_casier_politique_info(name: str) -> dict:
    try:
        condamnations = await asyncio.wait_for(
            _scraper_toutes_pages(name),
            timeout=120
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
