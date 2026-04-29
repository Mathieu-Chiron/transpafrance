# Correspondance parti → bord politique
# Source : classification politique française standard

PARTIS_BORD = {
    # Extrême gauche
    "La France insoumise":           "Gauche radicale",
    "LFI":                           "Gauche radicale",
    "Nouveau Parti anticapitaliste": "Extrême gauche",
    "NPA":                           "Extrême gauche",
    "Parti communiste français":     "Gauche radicale",
    "PCF":                           "Gauche radicale",

    # Gauche
    "Parti socialiste":              "Gauche",
    "PS":                            "Gauche",
    "Place Publique":                "Gauche",
    "Génération·s":                  "Gauche",

    # Centre gauche / écologie
    "Europe Écologie Les Verts":     "Centre gauche",
    "EELV":                          "Centre gauche",
    "Les Écologistes":               "Centre gauche",

    # Centre
    "Renaissance":                   "Centre",
    "LREM":                          "Centre",
    "La République En Marche":       "Centre",
    "MoDem":                         "Centre",
    "Mouvement démocrate":           "Centre",
    "Horizons":                      "Centre droit",
    "UDF":                           "Centre droit",

    # Droite
    "Les Républicains":              "Droite",
    "LR":                            "Droite",
    "RPR":                           "Droite",
    "UMP":                           "Droite",
    "RPR/UMP/LR":                    "Droite",
    "Debout la France":              "Droite nationale",

    # Extrême droite
    "Rassemblement national":        "Extrême droite",
    "RN":                            "Extrême droite",
    "Front national":                "Extrême droite",
    "FN":                            "Extrême droite",
    "Reconquête":                    "Extrême droite",
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
