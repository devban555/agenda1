TEMA_PADRAO = "principal"
TEMAS_VALIDOS = frozenset({
    "principal",
    "esmeralda",
    "violeta",
    "ambar",
    "rose",
    "lavanda",
    "clinica",
    "champagne",
})


def normalizar_tema(valor):
    tema = str(valor or "").strip().lower()
    return tema if tema in TEMAS_VALIDOS else TEMA_PADRAO
