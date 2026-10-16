const input = document.querySelector("[data-search]");
const results = document.getElementById("search-results");

if (input && results) {
  const options = () => [...results.querySelectorAll("[data-add-exam]")];
  let pendingEnter = false;

  const addFirst = () => {
    const first = options()[0];
    if (!first) return false;
    window.htmx?.process(first);
    first.click();
    return true;
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      options()[0]?.focus();
    } else if (event.key === "Enter") {
      event.preventDefault();
      const searching = input.classList.contains("htmx-request");
      pendingEnter = searching || !addFirst();
    } else if (event.key === "Escape") {
      input.value = "";
      results.innerHTML = "";
    }
  });

  results.addEventListener("keydown", (event) => {
    const list = options();
    const i = list.indexOf(document.activeElement);
    if (i === -1) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      list[i + 1]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      (list[i - 1] || input).focus();
    }
  });

  results.addEventListener("htmx:afterSettle", () => {
    if (pendingEnter) {
      pendingEnter = false;
      addFirst();
    }
  });

  input.addEventListener("input", () => {
    pendingEnter = false;
  });

  results.addEventListener("click", (event) => {
    if (event.target.closest("[data-add-exam]")) {
      input.value = "";
      input.focus();
    }
  });
}
