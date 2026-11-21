// Stupid Code "Study Mode" session control for Kiro Crew.
// Renders one checkbox. Toggling it posts the Study Mode value for the active
// repository to the app webhook and shows the value the backend persisted.
// The export shape and the context fields are assumptions (design Open Risk R1).

const ENDPOINT = "/api/apps/stupid-code/crew";

function repoIdFrom(context) {
  const id = context && (context.repoId ?? context.repo_id);
  return typeof id === "string" && id.length > 0 ? id : null;
}

function initialValueFrom(context) {
  const value = context && (context.studyModeEnabled ?? context.study_mode_enabled);
  return value === true;
}

export function mount(element, context) {
  const repoId = repoIdFrom(context);
  const label = document.createElement("label");
  const box = document.createElement("input");
  const status = document.createElement("span");
  box.type = "checkbox";
  box.checked = initialValueFrom(context);
  label.append(box, " Study Mode ", status);
  element.append(label);

  let active = true;

  if (repoId === null) {
    box.disabled = true;
    status.textContent = "(no repository)";
  }

  async function onChange() {
    const wanted = box.checked;
    box.disabled = true;
    status.textContent = "";
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "study_mode", repo_id: repoId, enabled: wanted }),
      });
      const body = await response.json();
      if (!active) return;
      if (response.ok && typeof body.study_mode_enabled === "boolean") {
        box.checked = body.study_mode_enabled;
      } else {
        box.checked = !wanted;
        status.textContent = `(${body && body.error ? body.error.code : "error"})`;
      }
    } catch {
      if (!active) return;
      box.checked = !wanted;
      status.textContent = "(unavailable)";
    } finally {
      if (active) box.disabled = false;
    }
  }

  box.addEventListener("change", onChange);

  return function unmount() {
    active = false;
    box.removeEventListener("change", onChange);
    label.remove();
  };
}
