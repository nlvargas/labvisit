document.querySelectorAll("[data-slot-picker]").forEach((form) => {
  const tabs = form.querySelector(".day-tabs");
  const groups = form.querySelectorAll("[data-day]");
  const checked = form.querySelector("input[name=slot]:checked");
  if (checked) {
    const day = checked.closest("[data-day]").dataset.day;
    form.querySelector(`input[name=day][value="${day}"]`).checked = true;
  }
  const show = () => {
    const day = form.querySelector("input[name=day]:checked").value;
    groups.forEach((group) => { group.hidden = group.dataset.day !== day; });
  };
  tabs.hidden = false;
  form.classList.add("tabbed");
  tabs.addEventListener("change", show);
  show();
});
