const MAX_SIDE = 2000;
const SHRINK_ABOVE_BYTES = 1_500_000;

async function shrink(file) {
  if (!file.type.startsWith("image/")) return file;
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return file;
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  if (scale === 1 && file.size <= SHRINK_ABOVE_BYTES) return file;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  if (!blob || blob.size >= file.size) return file;
  const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
  return new File([blob], name, { type: "image/jpeg" });
}

document.querySelectorAll("[data-dropzone]").forEach((zone) => {
  const form = zone.closest("form");
  const input = zone.querySelector("input[type=file]");
  const filename = zone.querySelector("[data-filename]");
  const button = form.querySelector("[data-submit]");
  const error = form.querySelector("[data-error]");
  const buttonLabel = button.textContent;
  let upload = null;
  let waiting = false;

  function showError(message) {
    error.textContent = message;
    error.hidden = !message;
  }

  async function start(file) {
    if (!file) return;
    showError("");
    filename.textContent = file.name;
    zone.classList.add("has-file");
    const current = (async () => {
      const body = new FormData();
      body.append("file", await shrink(file));
      body.append("csrfmiddlewaretoken", form.querySelector("[name=csrfmiddlewaretoken]").value);
      const response = await fetch(form.action || window.location.href, {
        method: "POST",
        body,
        headers: { Accept: "application/json" },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.url) throw new Error(data.error || "No pudimos subir el archivo. Intenta de nuevo.");
      return data.url;
    })();
    upload = current;
    current.catch((err) => {
      if (upload !== current) return;
      upload = null;
      zone.classList.remove("has-file");
      filename.textContent = "";
      button.textContent = buttonLabel;
      button.disabled = false;
      waiting = false;
      showError(err.message);
    });
  }

  form.addEventListener("submit", async (event) => {
    if (!upload) return;
    event.preventDefault();
    if (waiting) return;
    waiting = true;
    button.disabled = true;
    button.textContent = "Subiendo tu orden…";
    const pending = upload;
    try {
      window.location.href = await pending;
    } catch {
      // the error is shown by start()
    }
  });

  input.addEventListener("change", () => start(input.files[0]));
  ["dragenter", "dragover"].forEach((type) =>
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.add("is-dragging");
    })
  );
  ["dragleave", "drop"].forEach((type) =>
    zone.addEventListener(type, () => zone.classList.remove("is-dragging"))
  );
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    start(file);
  });
  window.addEventListener("pageshow", () => {
    waiting = false;
    button.disabled = false;
    button.textContent = buttonLabel;
  });
});

["dragover", "drop"].forEach((type) =>
  window.addEventListener(type, (event) => {
    if (!event.target.closest?.("[data-dropzone]")) event.preventDefault();
  })
);
