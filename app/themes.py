TEMA_PADRAO = "principal"
TEMAS_VALIDOS = frozenset({
    "principal",
    "azul_claro",
    "neutra",
    "rose",
    "lavanda",
    "clinica",
    "champagne",
})

TEMAS_LEGADOS = {
    "esmeralda": "clinica",
    "violeta": "lavanda",
    "ambar": "champagne",
}

FONTE_TITULO_PADRAO = "padrao"
FONTES_TITULO_VALIDAS = frozenset({
    "padrao",
    "poppins",
    "montserrat",
    "playfair",
    "cormorant",
    "quicksand",
    "dancing",
    "lora",
})


def normalizar_tema(valor):
    tema = str(valor or "").strip().lower()
    tema = TEMAS_LEGADOS.get(tema, tema)
    return tema if tema in TEMAS_VALIDOS else TEMA_PADRAO


def normalizar_fonte_titulo(valor):
    fonte = str(valor or "").strip().lower()
    return fonte if fonte in FONTES_TITULO_VALIDAS else FONTE_TITULO_PADRAO
