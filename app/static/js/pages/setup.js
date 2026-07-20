(() => {
  "use strict";

  const app = document.getElementById("setupApp");
  if (!app) return;

  const horariosPadraoSemana = [
    "09:40", "10:20", "11:00", "13:00", "13:40", "14:20",
    "15:00", "15:40", "16:20", "17:40", "19:00"
  ];
  const horariosPadraoSabado = [
    "11:00", "11:40", "12:20", "13:00", "13:40", "14:20", "15:00"
  ];
  const diasPadrao = [0, 1, 2, 3, 4, 5];

  const fontes = {
    padrao: "'Poppins', sans-serif",
    poppins: "'Poppins', sans-serif",
    montserrat: "'Montserrat', sans-serif",
    playfair: "'Playfair Display', serif",
    cormorant: "'Cormorant Garamond', serif",
    quicksand: "'Quicksand', sans-serif",
    dancing: "'Dancing Script', cursive",
    lora: "'Lora', serif"
  };

  const nomesTemas = {
    principal: "Azul Noturno",
    azul_claro: "Azul & Branco",
    neutra: "Neve & Grafite",
    rose: "Rosé",
    lavanda: "Lavanda",
    clinica: "Clínica Clean",
    champagne: "Champagne"
  };
  const temasValidos = new Set(Object.keys(nomesTemas));

  const urls = {
    config: app.dataset.configUrl,
    saveBase: app.dataset.saveBaseUrl,
    saveIdentity: app.dataset.saveIdentityUrl,
    saveException: app.dataset.saveExceptionUrl,
    loadAvailability: app.dataset.loadAvailabilityUrl
  };

  const profissionalAgenda = document.getElementById("profissionalAgenda");
  const inputNome = document.getElementById("nomeFantasia");
  const selectFonte = document.getElementById("fonteTitulo");
  const fontPreview = document.getElementById("fontPreview");
  const themeRoot = document.documentElement;
  const themeButtons = [...document.querySelectorAll("[data-theme-option]")];
  const themeSummary = document.getElementById("themeSummary");
  const professionalContext = document.querySelector(".professional-context");
  const dataSelecionada = document.getElementById("dataSelecionada");
  const diaAtivo = document.getElementById("diaAtivo");
  const exceptionSchedule = document.getElementById("exceptionSchedule");

  let temaSelecionado = temasValidos.has(app.dataset.currentTheme)
    ? app.dataset.currentTheme
    : "principal";
  let horariosBloqueados = new Set();

  function setStatus(elementId, message = "", type = "") {
    const element = document.getElementById(elementId);
    if (!element) return;
    element.textContent = message;
    element.className = `form-status${type ? ` is-${type}` : ""}`;
  }

  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {})
      },
      ...options
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }

    if (!response.ok) {
      throw new Error(payload.mensagem || payload.erro || "Não foi possível concluir a operação.");
    }
    return payload;
  }

  function ativarAba(nome) {
    const aba = document.querySelector(`[data-tab="${nome}"]`);
    if (!aba) return;

    document.querySelectorAll("[data-tab]").forEach((button) => {
      const active = button === aba;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });

    document.querySelectorAll(".setup-panel").forEach((panel) => {
      const active = panel.id === aba.getAttribute("aria-controls");
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });

    professionalContext.hidden = nome === "aparencia";

    try {
      sessionStorage.setItem("agenda1-config-tab", nome);
    } catch (_error) {
      // Navegadores com armazenamento bloqueado continuam funcionando.
    }
  }

  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => ativarAba(button.dataset.tab));
    button.addEventListener("keydown", (event) => {
      if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      const tabs = [...document.querySelectorAll("[data-tab]")];
      const direction = event.key === 'ArrowRight' ? 1 : -1;
      const next = (tabs.indexOf(button) + direction + tabs.length) % tabs.length;
      tabs[next].focus();
      ativarAba(tabs[next].dataset.tab);
    });
  });

  function createHorarioItem(valor = "") {
    const item = document.createElement("div");
    item.className = "horario-item";

    const input = document.createElement("input");
    input.type = "time";
    input.value = valor;
    input.setAttribute("aria-label", "Horário de atendimento");

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn-remove-hora";
    remove.title = "Remover horário";
    remove.setAttribute("aria-label", "Remover horário");

    const icon = document.createElement("i");
    icon.className = "fa-solid fa-xmark";
    icon.setAttribute("aria-hidden", "true");
    remove.appendChild(icon);
    remove.addEventListener("click", () => item.remove());

    item.append(input, remove);
    return item;
  }

  function addHorarioInput(gridId, valor = "") {
    document.getElementById(gridId)?.appendChild(createHorarioItem(valor));
  }

  function renderHorarios(semana = [], sabado = []) {
    const gridSemana = document.getElementById("gridSemana");
    const gridSabado = document.getElementById("gridSabado");
    gridSemana.replaceChildren();
    gridSabado.replaceChildren();

    const listaSemana = Array.isArray(semana) && semana.length ? semana : horariosPadraoSemana;
    const listaSabado = Array.isArray(sabado) && sabado.length ? sabado : horariosPadraoSabado;
    listaSemana.forEach((hora) => addHorarioInput("gridSemana", hora));
    listaSabado.forEach((hora) => addHorarioInput("gridSabado", hora));
  }

  function aplicarDiasSelecionados(dias = []) {
    const lista = Array.isArray(dias) && dias.length ? dias : diasPadrao;
    document.querySelectorAll("#diasSemana input").forEach((checkbox) => {
      checkbox.checked = lista.includes(Number.parseInt(checkbox.value, 10));
    });
  }

  function coletarHorarios(gridId) {
    return [...document.querySelectorAll(`#${gridId} input[type="time"]`)]
      .map((input) => input.value)
      .filter(Boolean)
      .sort();
  }

  async function carregarConfiguracaoBase() {
    if (!profissionalAgenda?.value) return;
    setStatus("baseStatus", "Carregando agenda...", "info");
    const params = new URLSearchParams({ profissional_id: profissionalAgenda.value });

    try {
      const data = await jsonRequest(`${urls.config}?${params.toString()}`);
      aplicarDiasSelecionados(data.dias_semana || []);
      renderHorarios(
        data.horarios_base?.semana || [],
        data.horarios_base?.sabado || []
      );
      setStatus("baseStatus");
    } catch (error) {
      console.error("Erro ao carregar a agenda:", error);
      aplicarDiasSelecionados(diasPadrao);
      renderHorarios(horariosPadraoSemana, horariosPadraoSabado);
      setStatus("baseStatus", "A configuração padrão foi exibida porque a agenda não pôde ser carregada.", "error");
    }
  }

  document.querySelectorAll("[data-add-schedule]").forEach((button) => {
    button.addEventListener("click", () => addHorarioInput(button.dataset.addSchedule));
  });

  document.getElementById("salvarBase").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const dias = [...document.querySelectorAll("#diasSemana input:checked")]
      .map((checkbox) => Number.parseInt(checkbox.value, 10));
    const semana = coletarHorarios("gridSemana");
    const sabado = coletarHorarios("gridSabado");

    if (!dias.length) {
      setStatus("baseStatus", "Selecione ao menos um dia de funcionamento.", "error");
      return;
    }
    if (!semana.length && !sabado.length) {
      setStatus("baseStatus", "Adicione ao menos um horário de funcionamento.", "error");
      return;
    }

    button.disabled = true;
    setStatus("baseStatus", "Salvando agenda...", "info");
    try {
      await jsonRequest(urls.saveBase, {
        method: "POST",
        body: JSON.stringify({
          profissional_id: profissionalAgenda.value,
          dias_semana: dias,
          horarios_base: { semana, sabado }
        })
      });
      aplicarDiasSelecionados(dias);
      renderHorarios(semana, sabado);
      setStatus("baseStatus", "Agenda padrão salva com sucesso!", "success");
    } catch (error) {
      console.error("Erro ao salvar a agenda:", error);
      setStatus("baseStatus", error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  function atualizarPreviaFonte() {
    const fonte = fontes[selectFonte.value] || fontes.padrao;
    fontPreview.style.fontFamily = fonte;
    fontPreview.textContent = inputNome.value.trim() || "Prévia do nome do seu negócio";
  }

  inputNome.value = app.dataset.currentName || "";
  selectFonte.value = fontes[app.dataset.currentFont] ? app.dataset.currentFont : "padrao";
  inputNome.addEventListener("input", atualizarPreviaFonte);
  selectFonte.addEventListener("change", atualizarPreviaFonte);

  document.getElementById("salvarIdentidade").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const nome = inputNome.value.trim();
    if (!nome) {
      setStatus("identityStatus", "Informe o nome fantasia.", "error");
      inputNome.focus();
      return;
    }

    button.disabled = true;
    setStatus("identityStatus", "Salvando identidade...", "info");
    try {
      await jsonRequest(urls.saveIdentity, {
        method: "POST",
        body: JSON.stringify({ nome_fantasia: nome, fonte_titulo: selectFonte.value })
      });
      setStatus("identityStatus", "Identidade salva com sucesso!", "success");
    } catch (error) {
      console.error("Erro ao salvar identidade:", error);
      setStatus("identityStatus", error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  function selecionarTema(tema, mostrarPrevia = false) {
    if (!temasValidos.has(tema)) return;
    temaSelecionado = tema;
    themeRoot.dataset.theme = tema;
    themeButtons.forEach((button) => {
      const selected = button.dataset.themeOption === tema;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-checked", String(selected));
    });
    themeSummary.textContent = `Paleta atual: ${nomesTemas[tema]}.`;
    if (mostrarPrevia) {
      setStatus("themeStatus", "Prévia aplicada. Salve para usar em outros dispositivos.", "info");
    }
  }

  themeButtons.forEach((button) => {
    button.addEventListener("click", () => selecionarTema(button.dataset.themeOption, true));
  });

  document.getElementById("salvarTema").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    setStatus("themeStatus", "Salvando paleta...", "info");
    try {
      const result = await jsonRequest(urls.saveIdentity, {
        method: "POST",
        body: JSON.stringify({ tema: temaSelecionado })
      });
      selecionarTema(result.tema || temaSelecionado);
      setStatus("themeStatus", "Paleta salva com sucesso!", "success");
    } catch (error) {
      console.error("Erro ao salvar paleta:", error);
      setStatus("themeStatus", error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  function renderExceptionTimes(horarios = []) {
    exceptionSchedule.replaceChildren();
    if (!horarios.length) {
      const empty = document.createElement("p");
      empty.className = "exception-empty";
      empty.textContent = "Não há horários configurados para esta data.";
      exceptionSchedule.appendChild(empty);
      return;
    }

    horarios.forEach((hora) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "exception-time";
      button.dataset.time = hora;
      button.textContent = hora;
      button.disabled = !diaAtivo.checked;
      const blocked = horariosBloqueados.has(hora);
      button.classList.toggle("is-blocked", blocked);
      button.setAttribute("aria-pressed", String(blocked));
      button.setAttribute("aria-label", `${hora}: ${blocked ? "bloqueado" : "disponível"}`);
      button.addEventListener("click", () => {
        if (horariosBloqueados.has(hora)) {
          horariosBloqueados.delete(hora);
        } else {
          horariosBloqueados.add(hora);
        }
        const isBlocked = horariosBloqueados.has(hora);
        button.classList.toggle("is-blocked", isBlocked);
        button.setAttribute("aria-pressed", String(isBlocked));
        button.setAttribute("aria-label", `${hora}: ${isBlocked ? "bloqueado" : "disponível"}`);
        setStatus("exceptionStatus", "Alteração ainda não salva.", "info");
      });
      exceptionSchedule.appendChild(button);
    });
  }

  async function carregarExcecao() {
    const data = dataSelecionada.value;
    if (!data || !profissionalAgenda?.value) {
      horariosBloqueados = new Set();
      renderExceptionTimes([]);
      return;
    }

    setStatus("exceptionStatus", "Carregando data...", "info");
    try {
      const result = await jsonRequest(urls.loadAvailability, {
        method: "POST",
        body: JSON.stringify({ data, profissional_id: profissionalAgenda.value })
      });
      horariosBloqueados = new Set(result.bloqueados || []);
      diaAtivo.checked = result.dia_ativo !== false;
      renderExceptionTimes(result.horarios || []);
      setStatus("exceptionStatus");
    } catch (error) {
      console.error("Erro ao carregar exceção:", error);
      horariosBloqueados = new Set();
      renderExceptionTimes([]);
      setStatus("exceptionStatus", error.message, "error");
    }
  }

  diaAtivo.addEventListener("change", () => {
    document.querySelectorAll(".exception-time").forEach((button) => {
      button.disabled = !diaAtivo.checked;
    });
    setStatus(
      "exceptionStatus",
      diaAtivo.checked ? "Dia reaberto. Se desejar, bloqueie horários específicos." : "O dia inteiro será bloqueado ao salvar.",
      "info"
    );
  });

  dataSelecionada.addEventListener("change", carregarExcecao);

  document.getElementById("salvarExcecao").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const data = dataSelecionada.value;
    if (!data) {
      setStatus("exceptionStatus", "Selecione uma data primeiro.", "error");
      dataSelecionada.focus();
      return;
    }

    button.disabled = true;
    setStatus("exceptionStatus", "Salvando exceção...", "info");
    try {
      await jsonRequest(urls.saveException, {
        method: "POST",
        body: JSON.stringify({
          profissional_id: profissionalAgenda.value,
          data,
          dia_ativo: diaAtivo.checked,
          horarios_bloqueados: [...horariosBloqueados].sort()
        })
      });
      setStatus("exceptionStatus", "Exceção salva com sucesso!", "success");
    } catch (error) {
      console.error("Erro ao salvar exceção:", error);
      setStatus("exceptionStatus", error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  profissionalAgenda?.addEventListener("change", async () => {
    await carregarConfiguracaoBase();
    if (dataSelecionada.value) await carregarExcecao();
  });

  let abaInicial = "agenda";
  try {
    abaInicial = sessionStorage.getItem("agenda1-config-tab") || abaInicial;
  } catch (_error) {
    // Mantém a aba Agenda como padrão.
  }
  if (!document.querySelector(`[data-tab="${abaInicial}"]`)) abaInicial = "agenda";

  ativarAba(abaInicial);
  atualizarPreviaFonte();
  selecionarTema(temaSelecionado);
  carregarConfiguracaoBase();
})();
