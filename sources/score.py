"""
Calcul du Score de Transparence TranspaFrance
Score sur 100 basé sur les données publiques disponibles.

Moyennes nationales calculées sur 6 mois (juin à décembre 2023)
sur ~580 députés actifs par mois — source : NosDéputés.fr
"""

# Moyennes réelles calculées depuis NosDéputés.fr
# Base : 6 mois (202306, 202307, 202309, 202310, 202311, 202312)
# ~580 députés actifs par mois — uniquement les députés ayant au moins une activité
MOYENNES_NATIONALES = {
    "semaines_presence":              3.34,   # sur 3402 mesures
    "commission_presences":           6.31,   # sur 3269 mesures
    "hemicycle_interventions":       16.84,   # sur 2040 mesures
    "hemicycle_interventions_courtes": 25.26, # sur 1989 mesures
    "amendements_proposes":          22.66,   # sur 2235 mesures
    "amendements_adoptes":           20.64,   # sur 3273 mesures
    "amendements_signes":           381.44,   # sur 3456 mesures
    "questions_ecrites":              2.86,   # sur 1794 mesures
    "questions_orales":               1.05,   # sur 629 mesures
    "propositions_ecrites":           1.27,   # sur 378 mesures
    "rapports":                       1.40,   # sur 393 mesures
}

SOURCE_MOYENNES = "NosDéputés.fr — synthèse mensuelle 16e législature (juin–décembre 2023, ~580 députés actifs/mois)"
PERIODE_MOYENNES = "Juin 2023 – Décembre 2023 (16e législature)"

POIDS = {
    "presence":       25,
    "initiative":     20,
    "engagement":     15,
    "condamnations":  20,
    "cumul":          10,
    "hatvp":          10,
}

EXPLICATION = f"""
Le Score de Transparence TranspaFrance est calculé sur 100 points à partir de données publiques officielles.

CRITÈRES ET PONDÉRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Présence (25 pts)
  Semaines de présence en hémicycle et en commission.
  Comparées à la moyenne nationale réelle : {MOYENNES_NATIONALES["semaines_presence"]} sem./mois.

- Initiative législative (20 pts)
  Amendements proposés + propositions de loi déposées.
  Moyenne nationale : {MOYENNES_NATIONALES["amendements_proposes"]} amendements/mois.

- Engagement (15 pts)
  Interventions en hémicycle + questions au gouvernement.
  Moyenne nationale : {MOYENNES_NATIONALES["hemicycle_interventions"]} interventions/mois.

- Condamnations (20 pts)
  Toute condamnation définitive retire 20 pts.
  En appel : −14 pts. En 1re instance : −10 pts.
  Source : casier-politique.fr

- Cumul de mandats (10 pts)
  Mandat unique : 10/10. Double mandat : 5/10. Triple ou plus : 0/10.
  Source : Répertoire National des Élus (data.gouv.fr)

- Transparence HATVP (10 pts)
  Présence d'une déclaration de patrimoine et d'intérêts.
  Source : hatvp.fr

SOURCES DES MOYENNES NATIONALES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{SOURCE_MOYENNES}
Calculées sur les députés ayant au moins une activité enregistrée.
Ces moyennes sont issues de la 16e législature et seront mises à jour
dès que les données de la 17e législature seront disponibles.

LIMITES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ Les données d'activité couvrent la 16e législature (2022–2024).
Pour les élus entrés en fonction en juillet 2024, le score est partiel.
⚠️ Ce score mesure la transparence et l'activité — pas la qualité politique.
Un élu très présent peut voter des lois contestables, et inversement.
⚠️ Les condamnations proviennent de casier-politique.fr — base non exhaustive.
"""

def calculer_score(
    stats_moyennes: dict,
    condamnations:  list,
    mandats_rne:    list,
    hatvp_url:      str,
) -> dict:

    details     = {}
    score_total = 0
    pts_max     = 0
    partiel     = False

    # ── 1. Présence (25 pts) ──────────────────────────────
    presence = stats_moyennes.get("semaines_presence", 0)
    moy_pres = MOYENNES_NATIONALES["semaines_presence"]

    if presence > 0:
        ratio        = min(presence / moy_pres, 1.5)
        pts_presence = round(min(ratio * POIDS["presence"], POIDS["presence"]))
        pct_presence = round(min((presence / moy_pres) * 100, 100))
        pts_max     += POIDS["presence"]
    else:
        pts_presence = None
        pct_presence = None
        partiel      = True

    score_total += pts_presence or 0
    details["presence"] = {
        "pts":         pts_presence,
        "pts_max":     POIDS["presence"],
        "pct":         pct_presence,
        "valeur":      round(presence, 1),
        "moyenne_nat": moy_pres,
        "disponible":  presence > 0,
        "label":       "Présence",
        "unite":       "sem./mois",
    }

    # ── 2. Initiative législative (20 pts) ───────────────
    amendements  = stats_moyennes.get("amendements_proposes", 0)
    propositions = stats_moyennes.get("propositions_ecrites", 0)
    init_val     = amendements + propositions
    moy_init     = MOYENNES_NATIONALES["amendements_proposes"]

    if stats_moyennes:
        ratio     = min(init_val / max(moy_init, 1), 1.5)
        pts_init  = round(min(ratio * POIDS["initiative"], POIDS["initiative"]))
        pct_init  = round(min((init_val / moy_init) * 100, 100))
        pts_max  += POIDS["initiative"]
    else:
        pts_init = None
        pct_init = None
        partiel  = True

    score_total += pts_init or 0
    details["initiative"] = {
        "pts":         pts_init,
        "pts_max":     POIDS["initiative"],
        "pct":         pct_init,
        "valeur":      round(init_val, 1),
        "moyenne_nat": moy_init,
        "disponible":  bool(stats_moyennes),
        "label":       "Initiative législative",
        "unite":       "amend./mois",
    }

    # ── 3. Engagement (15 pts) ───────────────────────────
    interventions = stats_moyennes.get("hemicycle_interventions", 0)
    questions     = stats_moyennes.get("questions_ecrites", 0) + stats_moyennes.get("questions_orales", 0)
    eng_val       = interventions + questions
    moy_eng       = MOYENNES_NATIONALES["hemicycle_interventions"]

    if stats_moyennes:
        ratio    = min(eng_val / max(moy_eng, 1), 1.5)
        pts_eng  = round(min(ratio * POIDS["engagement"], POIDS["engagement"]))
        pct_eng  = round(min((eng_val / moy_eng) * 100, 100))
        pts_max += POIDS["engagement"]
    else:
        pts_eng = None
        pct_eng = None
        partiel = True

    score_total += pts_eng or 0
    details["engagement"] = {
        "pts":         pts_eng,
        "pts_max":     POIDS["engagement"],
        "pct":         pct_eng,
        "valeur":      round(eng_val, 1),
        "moyenne_nat": moy_eng,
        "disponible":  bool(stats_moyennes),
        "label":       "Engagement",
        "unite":       "interv./mois",
    }

    # ── 4. Condamnations (20 pts) ────────────────────────
    pts_max += POIDS["condamnations"]
    nb_cond  = len(condamnations)

    if nb_cond == 0:
        pts_cond    = POIDS["condamnations"]
        statut_cond = "aucune"
    else:
        textes    = " ".join([c.get("description", "").lower() for c in condamnations])
        definitif = "définitif" in textes or "cassation" in textes
        en_appel  = "appel" in textes
        if definitif:
            pts_cond    = 0
            statut_cond = "definitif"
        elif en_appel:
            pts_cond    = round(POIDS["condamnations"] * 0.3)
            statut_cond = "appel"
        else:
            pts_cond    = round(POIDS["condamnations"] * 0.5)
            statut_cond = "instance"

    score_total += pts_cond
    details["condamnations"] = {
        "pts":        pts_cond,
        "pts_max":    POIDS["condamnations"],
        "nb":         nb_cond,
        "statut":     statut_cond,
        "disponible": True,
        "label":      "Condamnations",
    }

    # ── 5. Cumul de mandats (10 pts) ─────────────────────
    pts_max    += POIDS["cumul"]
    nb_mandats  = len(mandats_rne)

    if nb_mandats <= 1:
        pts_cumul    = POIDS["cumul"]
        statut_cumul = "unique"
    elif nb_mandats == 2:
        pts_cumul    = round(POIDS["cumul"] * 0.5)
        statut_cumul = "double"
    else:
        pts_cumul    = 0
        statut_cumul = "multiple"

    score_total += pts_cumul
    details["cumul"] = {
        "pts":        pts_cumul,
        "pts_max":    POIDS["cumul"],
        "nb_mandats": nb_mandats,
        "statut":     statut_cumul,
        "disponible": True,
        "label":      "Cumul de mandats",
    }

    # ── 6. Transparence HATVP (10 pts) ───────────────────
    pts_max  += POIDS["hatvp"]
    hatvp_ok  = bool(hatvp_url and "hatvp.fr" in hatvp_url)
    pts_hatvp = POIDS["hatvp"] if hatvp_ok else 0

    score_total += pts_hatvp
    details["hatvp"] = {
        "pts":        pts_hatvp,
        "pts_max":    POIDS["hatvp"],
        "disponible": True,
        "hatvp_ok":   hatvp_ok,
        "url":        hatvp_url,
        "label":      "Transparence HATVP",
    }

    # ── Score final ───────────────────────────────────────
    score_final = round((score_total / pts_max) * 100) if pts_max > 0 else 0

    return {
        "score":            score_final,
        "pts_obtenus":      score_total,
        "pts_max":          pts_max,
        "partiel":          partiel,
        "details":          details,
        "explication":      EXPLICATION.strip(),
        "source_moyennes":  SOURCE_MOYENNES,
        "periode_moyennes": PERIODE_MOYENNES,
    }
