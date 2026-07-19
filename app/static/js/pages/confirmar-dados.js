const form = document.getElementById("form-agendamento");
const inputNome = document.getElementById("input-nome");
const errorNome = document.getElementById("error-nome");

function validarNomeCompleto(valor) {
  const limpo = valor.trim().replace(/\s+/g, " ");
  const partes = limpo.split(" ").filter((parte) => parte.length > 0);

  return {
    valido: partes.length >= 2,
    textoFormatado: limpo
  };
}

function definirErroNome(visivel) {
  inputNome.classList.toggle("input-error", visivel);
  inputNome.setAttribute("aria-invalid", String(visivel));
  errorNome.hidden = !visivel;
}

inputNome.addEventListener("input", () => {
  const { valido } = validarNomeCompleto(inputNome.value);
  if (valido || inputNome.value.trim() === "") definirErroNome(false);
});

form.addEventListener("submit", (event) => {
  const resultado = validarNomeCompleto(inputNome.value);

  if (!resultado.valido) {
    event.preventDefault();
    definirErroNome(true);
    inputNome.focus();
    return;
  }

  definirErroNome(false);
  inputNome.value = resultado.textoFormatado;
});
