# Correspondance parti → bord politique
# Source : classification politique française standard

PARTIS_BORD = {
    # Gauche radicale — partis
    "La France insoumise":           "Gauche radicale",
    "LFI":                           "Gauche radicale",
    "Nouveau Parti anticapitaliste": "Gauche radicale",
    "NPA":                           "Gauche radicale",
    "Parti communiste français":     "Gauche radicale",
    "PCF":                           "Gauche radicale",

    # Gauche radicale — groupes parlementaires
    "Groupe La France insoumise":                       "Gauche radicale",
    "Groupe GDR":                                       "Gauche radicale",
    "Groupe communiste républicain citoyen":            "Gauche radicale",
    "Groupe communiste":                                "Gauche radicale",
    "Rassemblement démocratique et social européen":    "Gauche radicale",

    # Gauche — partis
    "Parti socialiste":              "Gauche",
    "PS":                            "Gauche",
    "Place Publique":                "Gauche",
    "Génération·s":                  "Gauche",

    # Gauche — groupes parlementaires
    "Groupe socialiste":                                "Gauche",
    "Groupe socialiste, écologiste et républicain":     "Gauche",
    "Groupe socialiste et républicain":                 "Gauche",
    "Groupe socialiste et apparentés":                  "Gauche",
    "Groupe de la gauche démocrate et républicaine":    "Gauche",

    # Centre gauche — partis
    "Europe Écologie Les Verts":     "Centre gauche",
    "EELV":                          "Centre gauche",
    "Les Écologistes":               "Centre gauche",

    # Centre gauche — groupes parlementaires
    "Groupe écologiste":                                "Centre gauche",
    "Groupe écologiste - nupes":                        "Centre gauche",
    "Les verts":                                        "Centre gauche",

    # Centre — partis
    "Renaissance":                   "Centre",
    "LREM":                          "Centre",
    "La République En Marche":       "Centre",
    "MoDem":                         "Centre",
    "Mouvement démocrate":           "Centre",

    # Centre — groupes parlementaires
    "Groupe renaissance":                               "Centre",
    "Groupe la république en marche":                   "Centre",
    "Groupe démocrate":                                 "Centre",
    "Groupe du rassemblement des démocrates":           "Centre",
    "Rassemblement des démocrates, progressistes":      "Centre",

    # Centre droit — partis
    "Horizons":                      "Centre droit",
    "UDF":                           "Centre droit",

    # Centre droit — groupes parlementaires
    "Groupe horizons":                                  "Centre droit",
    "Groupe union centriste":                           "Centre droit",
    "Groupe les indépendants":                          "Centre droit",
    "Groupe libertés et territoires":                   "Centre droit",
    "Groupe libertés, indépendants, outre-mer":         "Centre droit",
    "Liot":                                             "Centre droit",

    # Droite — partis
    "Les Républicains":              "Droite",
    "LR":                            "Droite",
    "RPR":                           "Droite",
    "UMP":                           "Droite",
    "Union pour un mouvement populaire": "Droite",
    "RPR/UMP/LR":                    "Droite",
    "Debout la France":              "Droite",

    # Droite — groupes parlementaires
    "Groupe les républicains":                          "Droite",
    "Groupe union pour un mouvement populaire":         "Droite",
    "Groupe ump":                                       "Droite",

    # Extrême droite — partis
    "Rassemblement national":        "Extrême droite",
    "RN":                            "Extrême droite",
    "Front national":                "Extrême droite",
    "FN":                            "Extrême droite",
    "Reconquête":                    "Extrême droite",

    # Extrême droite — groupes parlementaires
    "Groupe rassemblement national":                    "Extrême droite",
    "Groupe front national":                            "Extrême droite",
    "Groupe reconquête":                                "Extrême droite",
}

def get_bord_politique(parti: str) -> str:
    """Retourne le bord politique à partir du nom du parti."""
    if not parti:
        return None

    # Recherche exacte
    if parti in PARTIS_BORD:
        return PARTIS_BORD[parti]

    # Recherche partielle (insensible à la casse)
    parti_lower = parti.lower()
    for key, bord in PARTIS_BORD.items():
        if key.lower() in parti_lower or parti_lower in key.lower():
            return bord

    return None
