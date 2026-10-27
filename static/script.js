const form = document.getElementById("form");
const textArea = document.getElementById("text");
const fileInput = document.getElementById("file");
const preview = document.getElementById("preview");
const dropTitle = document.getElementById("drop-title");
const drop = document.getElementById("drop");
const errorBox = document.getElementById("error");
const result = document.getElementById("result");
const summaryBox = document.getElementById("summary");
const goBtn = document.getElementById("go");
let mode = "text";

// Switch between "paste text" and "upload file"
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    mode = tab.dataset.mode;
    document.querySelectorAll(".tab").forEach((t) => {
      const active = t === tab;
      t.classList.toggle("active", active);
      t.setAttribute("aria-selected", active);
    });
    document.getElementById("pane-text").hidden = mode !== "text";
    document.getElementById("pane-file").hidden = mode !== "file";
  });
});

// Word counter
textArea.addEventListener("input", () => {
  const words = textArea.value.trim().split(/\s+/).filter(Boolean).length;
  document.getElementById("count").textContent = words;
});

// File chosen: show its name, and a preview for images
function showFile() {
  const file = fileInput.files[0];
  preview.hidden = true;
  if (!file) { dropTitle.textContent = "Choose a file or drop it here"; return; }
  dropTitle.textContent = file.name;
  if (file.type.startsWith("image/")) {
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
  }
}
fileInput.addEventListener("change", showFile);

["dragenter", "dragover"].forEach((e) =>
  drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((e) =>
  drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (ev) => {
  if (ev.dataTransfer.files.length) {
    fileInput.files = ev.dataTransfer.files;
    showFile();
  }
});

function showError(msg) { errorBox.textContent = msg; errorBox.hidden = false; }

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  errorBox.hidden = true;
  result.hidden = true;

  const data = new FormData(form);
  // Only send the input from the tab that is open
  if (mode === "text") data.delete("file"); else data.delete("text");

  goBtn.disabled = true;
  goBtn.textContent = "Summarizing...";
  try {
    const res = await fetch("/summarize", { method: "POST", body: data });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "Something went wrong.");
    summaryBox.textContent = json.summary;
    result.hidden = false;
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    showError(err.message);
  } finally {
    goBtn.disabled = false;
    goBtn.textContent = "Summarize";
  }
});

document.getElementById("copy").addEventListener("click", async (ev) => {
  await navigator.clipboard.writeText(summaryBox.textContent);
  ev.target.textContent = "Copied";
  setTimeout(() => (ev.target.textContent = "Copy"), 1500);
});
