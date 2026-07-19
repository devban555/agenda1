const inputData = document.getElementById("data");
const container = document.getElementById("horarios-container");
const sectionHorarios = document.getElementById("section-horarios");
const form = document.getElementById("form-confirmar");
const horaEscolhida = document.getElementById("hora-escolhida");
const servicoId = form.dataset.serviceId;
const schedulesUrl = form.dataset.schedulesUrl;

function renderSimpleState(message) {
  container.innerHTML = "";
  const state = document.createElement("div");
  state.className = "schedule-state";
  state.textContent = message;
  container.appendChild(state);
}

function renderUnavailableState() {
  container.innerHTML = `
    <div class="schedule-state schedule-state--detailed">
      <strong>Não há tempo disponível para este serviço nesta data.</strong>
      <p>Este serviço exige um período maior de atendimento e os horários livres já não comportam sua duração.</p>
      <p>Escolha outra data ou selecione um serviço diferente.</p>
    </div>
  `;
}

function createScheduleButton(schedule) {
  const button = document.createElement("button");
  const time = document.createElement("span");
  const status = document.createElement("small");

  button.type = "button";
  button.className = "schedule-time-button";
  time.textContent = schedule;
  status.textContent = "Disponível";
  button.append(time, status);

  button.addEventListener("click", () => {
    button.classList.add("is-selected");
    horaEscolhida.value = schedule;
    window.setTimeout(() => form.submit(), 150);
  });

  return button;
}

inputData.addEventListener("change", async () => {
  renderSimpleState("Buscando horários...");
  sectionHorarios.hidden = false;

  try {
    const response = await fetch(schedulesUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data: inputData.value,
        servico_id: servicoId
      })
    });

    if (!response.ok) throw new Error("Falha ao consultar horários");

    const schedules = await response.json();
    if (!Array.isArray(schedules)) throw new Error("Resposta de horários inválida");

    container.innerHTML = "";
    if (schedules.length === 0) {
      renderUnavailableState();
      return;
    }

    schedules.forEach((schedule) => {
      container.appendChild(createScheduleButton(schedule));
    });
  } catch (error) {
    console.error("Erro ao carregar horários:", error);
    renderSimpleState("Erro ao carregar. Tente novamente.");
  }
});
