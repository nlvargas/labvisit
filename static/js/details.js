// Show the isapre list only when Isapre is selected.
const coverageField = document.querySelector("[data-coverage]");
const isapreField = document.querySelector("[data-isapre-field]");
if (coverageField && isapreField) {
  const isapreIds = coverageField.dataset.isapreIds.split(",");
  const select = isapreField.querySelector("select");
  const toggleIsapre = () => {
    const checked = coverageField.querySelector("input:checked");
    const show = Boolean(checked && isapreIds.includes(checked.value));
    isapreField.hidden = !show;
    select.required = show;
  };
  coverageField.addEventListener("change", toggleIsapre);
  toggleIsapre();
}

const form = document.querySelector("[data-details-form]");

if (form) {
  const button = form.querySelector("[data-continue]");
  const hint = form.querySelector("[data-continue-hint]");

  const update = () => {
    const reading = document.querySelector("[data-reading-state]")?.dataset.readingState !== "done";
    const isapreSelect = form.querySelector("select[name=isapre]");
    const needsIsapre = isapreSelect && !isapreSelect.closest("[data-isapre-field]").hidden;
    const coverage = form.querySelector("input[name=coverage]:checked") && (!needsIsapre || isapreSelect.value);
    const address = form.querySelector("input[name=address]")?.value.trim();
    const outOfRange = form.querySelector("[data-out-of-range]");
    const ready = !reading && coverage && address && !outOfRange;
    button.disabled = !ready;
    if (!coverage || !address) hint.textContent = "Completa tu sistema previsional y dirección para continuar.";
    else if (outOfRange) hint.textContent = "Elige una dirección dentro de la zona de cobertura.";
    else if (reading) hint.textContent = "Estamos terminando de leer tu orden…";
    hint.hidden = ready;
  };

  form.addEventListener("input", update);
  form.addEventListener("change", update);
  document.body.addEventListener("htmx:afterSettle", update);
  document.addEventListener("address:changed", update);
  update();

  // Cycling status messages while the order is read.
  let i = 0;
  setInterval(() => {
    const text = document.querySelector("[data-cycling]");
    if (!text) return;
    const messages = text.dataset.messages.split("|");
    if (i < messages.length - 1) text.textContent = messages[++i];
  }, 2500);
}
