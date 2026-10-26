"use strict";

const $ = (s) => document.querySelector(s);
const clamp = (v, a, b) => Math.min(Math.max(v, a), b);

const state = {
  imageId: null, mode: "auto", sensitivity: 30, detail: 25, line_mm: 1.4,
  title: "", ink: true, border: true,
  labels: [],                         // {text, x, y, pointer, ax, ay}
  erase: [],                          // [x0, y0, x1, y1] fractions of the diagram
};
let result = null;
let view = "tactile";
let aiAvailable = false;
let seq = 0;
let timer = null;
let samples = [];
let providers = [];
let tool = "label";
let processError = false;
let hintedNoKey = false;

// ---------------------------------------------------------------- helpers
function setStatus(msg) { $("#status").textContent = msg || ""; }

function activeLabels() { return state.labels.filter((l) => l.text.trim()); }

function keyFor(index) {
  let n = 0;
  for (let i = 0; i < index; i++) if (state.labels[i].text.trim()) n++;
  return state.labels[index].text.trim() ? String.fromCharCode(97 + n) : "–";
}

function schedule(delay = 220) {
  clearTimeout(timer);
  timer = setTimeout(process, delay);
}

function applyAiState() {
  $("#suggest").hidden = !aiAvailable;
  $("#autoname_wrap").hidden = !aiAvailable;
  $("#keybox").hidden = aiAvailable;
}

function fillProviders() {
  const sel = $("#provider");
  sel.innerHTML = "";
  providers.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = p.name;
    sel.appendChild(o);
  });
  showProvider();
}

function showProvider() {
  const p = providers.find((x) => x.id === $("#provider").value);
  if (!p) return;
  const help = $("#provider_help");
  help.textContent = p.help + " ";
  if (p.help_url) {
    const a = document.createElement("a");
    a.href = p.help_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "Get a key";
    help.appendChild(a);
  }
  $("#base_wrap").hidden = !p.needs_base;
  $("#model").placeholder = p.model || "Model name that accepts images";
}

async function saveKey() {
  const body = {
    provider: $("#provider").value, key: $("#apikey").value.trim(),
    model: $("#model").value.trim(), base: $("#base").value.trim(),
  };
  if (!body.key) { setStatus("Paste your API key first."); return; }
  const res = await fetch("/api/key", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) { setStatus(data.error || "Could not use that key."); return; }
  aiAvailable = data.ai_labels;
  $("#apikey").value = "";
  applyAiState();
  setStatus("Key saved for this session. Parts will be named when you upload or move a pointer.");
  if (state.imageId && !state.imageId.startsWith("sample:") && !state.labels.length) nameAllParts(true);
}

// ---------------------------------------------------------------- samples / upload
async function loadSamples() {
  const res = await fetch("/api/samples");
  const data = await res.json();
  samples = data.samples;
  aiAvailable = data.ai_labels;
  providers = data.providers || [];
  fillProviders();
  applyAiState();
  const box = $("#samples");
  box.innerHTML = "";
  samples.forEach((s) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = s.name;
    b.dataset.id = s.id;
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", () => chooseSample(s));
    box.appendChild(b);
  });
  if (samples.length) chooseSample(samples[0]);
}

function markSelected(id) {
  document.querySelectorAll("#samples button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.id === id)));
}

function chooseSample(s) {
  state.imageId = s.id;
  state.title = s.title;
  state.mode = "solid";
  state.detail = 25;
  state.erase = [];
  state.labels = s.labels.map((l) => ({
    text: l.text, x: l.x, y: l.y,
    pointer: l.ax !== undefined, ax: l.ax ?? clamp(l.x + 0.05, 0, 1), ay: l.ay ?? clamp(l.y + 0.08, 0, 1),
  }));
  markSelected(s.id);
  syncControls();
  renderLabelList();
  $("#source").src = `/api/source/${state.imageId}.png`;
  process();
}

async function upload(file) {
  if (!file) return;
  setStatus("Uploading…");
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) { setStatus(data.error || "Upload failed."); return; }
  state.imageId = data.image_id;
  state.title = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
  state.mode = "auto";
  state.detail = 40;                                 // scans carry larger printed text than the samples
  state.erase = [];
  state.labels = [];
  markSelected(null);
  syncControls();
  renderLabelList();
  $("#source").src = `/api/source/${state.imageId}.png`;
  await process();                                   // tactile page first, so it appears at once
  if (aiAvailable) nameAllParts(true);               // names arrive a few seconds later
  else setStatus("Click a part of the diagram to put an arrow on it, then type its name in the Labels list.");
}

// ---------------------------------------------------------------- controls
function syncControls() {
  $("#title").value = state.title;
  $("#ink").checked = state.ink;
  $("#border").checked = state.border;
  $("#mode").value = state.mode;
  for (const k of ["line_mm", "detail", "sensitivity"]) {
    $("#" + k).value = state[k];
    $("#" + k + "_out").textContent = k === "line_mm" ? state[k].toFixed(1) + " mm" : state[k];
  }
  $("#sens_wrap").hidden = state.mode === "solid";
  renderEraseRow();
}

function renderEraseRow() {
  const n = state.erase.length;
  $("#erase_row").hidden = n === 0;
  $("#erase_count").textContent = n === 1 ? "1 area erased" : `${n} areas erased`;
}

function bindControls() {
  $("#title").addEventListener("input", (e) => { state.title = e.target.value; schedule(); });
  $("#ink").addEventListener("change", (e) => { state.ink = e.target.checked; schedule(0); });
  $("#border").addEventListener("change", (e) => { state.border = e.target.checked; schedule(0); });
  $("#mode").addEventListener("change", (e) => { state.mode = e.target.value; syncControls(); schedule(0); });
  for (const k of ["line_mm", "detail", "sensitivity"]) {
    $("#" + k).addEventListener("input", (e) => {
      state[k] = Number(e.target.value);
      $("#" + k + "_out").textContent = k === "line_mm" ? state[k].toFixed(1) + " mm" : state[k];
      schedule(250);
    });
  }
  $("#file").addEventListener("change", (e) => upload(e.target.files[0]));
  const drop = $("#drop");
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => upload(e.dataTransfer.files[0]));

  $("#add").addEventListener("click", () => addLabelAt(0.5, 0.5, false));
  $("#suggest").addEventListener("click", () => nameAllParts(false));
  $("#savekey").addEventListener("click", saveKey);
  $("#provider").addEventListener("change", showProvider);
  $("#apikey").addEventListener("keydown", (e) => { if (e.key === "Enter") saveKey(); });
  $("#download").addEventListener("click", download);
  document.querySelectorAll("input[name=view]").forEach((r) =>
    r.addEventListener("change", (e) => { view = e.target.value; renderView(); }));
  document.querySelectorAll("input[name=tool]").forEach((r) =>
    r.addEventListener("change", (e) => {
      tool = e.target.value;
      setStatus(tool === "erase"
        ? "Drag a box over printed text to erase it. Switch back to “Label a part” to add arrows."
        : "Click a part of the diagram to put an arrow on it, then type its name.");
    }));
  $("#erase_undo").addEventListener("click", () => { state.erase.pop(); renderEraseRow(); schedule(0); });
  $("#erase_clear").addEventListener("click", () => { state.erase = []; renderEraseRow(); schedule(0); });
  bindSheet();
}

// ---------------------------------------------------------------- clicking on the sheet
function clientToNorm(cx, cy) {
  const r = $("#overlay").getBoundingClientRect();
  const [W, H] = result.page_mm;
  const [dx, dy, dw, dh] = result.diagram_mm;
  return { x: (((cx - r.left) / r.width) * W - dx) / dw, y: (((cy - r.top) / r.height) * H - dy) / dh };
}
const clampNorm = (n) => ({ x: clamp(n.x, 0, 1), y: clamp(n.y, 0, 1) });

// New label with an arrow whose tip is at (nx, ny); the key letter goes in free space toward the centre.
function addLabelAt(nx, ny, fromClick = true) {
  if (state.labels.length >= 26) { setStatus("A page holds at most 26 labels (a to z)."); return; }
  const label = {
    text: "", pointer: true, ax: nx, ay: ny,
    x: clamp(nx > 0.5 ? nx - 0.09 : nx + 0.09, 0.04, 0.96),
    y: clamp(ny > 0.5 ? ny - 0.12 : ny + 0.12, 0.06, 0.94),
  };
  state.labels.push(label);
  renderLabelList();
  const inputs = document.querySelectorAll("#labels input[type=text]");
  inputs[inputs.length - 1].focus();
  const auto = fromClick && aiAvailable && $("#autoname").checked;
  setStatus(auto ? "Naming the part…" : "Type the name of this part in the Labels list. The arrow appears once it has a name.");
  schedule(0);
  if (auto) renameAtPointer(label, { onlyIfEmpty: true });
}

function bindSheet() {
  const hit = $("#hit"), band = $("#band");
  let drag = null;
  const pct = (nx, ny) => {
    const [W, H] = result.page_mm, [dx, dy, dw, dh] = result.diagram_mm;
    return [((dx + nx * dw) / W) * 100, ((dy + ny * dh) / H) * 100];
  };
  const drawBand = (a, b) => {
    const [x0, y0] = pct(Math.min(a.x, b.x), Math.min(a.y, b.y));
    const [x1, y1] = pct(Math.max(a.x, b.x), Math.max(a.y, b.y));
    Object.assign(band.style, { left: x0 + "%", top: y0 + "%", width: x1 - x0 + "%", height: y1 - y0 + "%" });
  };
  hit.addEventListener("pointerdown", (e) => {
    if (!result) return;
    e.preventDefault();
    hit.setPointerCapture(e.pointerId);
    drag = { cx: e.clientX, cy: e.clientY, n: clientToNorm(e.clientX, e.clientY), moved: false };
  });
  hit.addEventListener("pointermove", (e) => {
    if (!drag) return;
    if (Math.hypot(e.clientX - drag.cx, e.clientY - drag.cy) > 4) drag.moved = true;
    if (tool === "erase" && drag.moved) {
      band.hidden = false;
      drawBand(clampNorm(drag.n), clampNorm(clientToNorm(e.clientX, e.clientY)));
    }
  });
  hit.addEventListener("pointerup", (e) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    band.hidden = true;
    try { hit.releasePointerCapture(e.pointerId); } catch { /* already released */ }
    if (tool === "label") {
      if (d.moved) return;
      const inside = d.n.x >= 0 && d.n.x <= 1 && d.n.y >= 0 && d.n.y <= 1;
      if (!inside) { setStatus("Click inside the frame, on the part you want to label."); return; }
      addLabelAt(d.n.x, d.n.y);
    } else if (d.moved) {
      const a = clampNorm(d.n), b = clampNorm(clientToNorm(e.clientX, e.clientY));
      const r = [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y)];
      if (r[2] - r[0] > 0.008 && r[3] - r[1] > 0.008) { state.erase.push(r); renderEraseRow(); schedule(0); }
    }
  });
}

function renderLabelList() {
  const ul = $("#labels");
  ul.innerHTML = "";
  state.labels.forEach((l, i) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="badge"></span>
      <input type="text" maxlength="40" aria-label="Label text" placeholder="Name this part">
      <label><input type="checkbox"> pointer</label>
      <button type="button" class="remove" aria-label="Remove label">×</button>`;
    const input = li.querySelector("input[type=text]");
    input.value = l.text;
    input.addEventListener("input", () => { l.text = input.value; updateBadges(); schedule(); });
    const ptr = li.querySelector("input[type=checkbox]");
    ptr.checked = l.pointer;
    ptr.addEventListener("change", () => {
      l.pointer = ptr.checked;
      if (l.pointer) { l.ax = clamp(l.x + 0.05, 0, 1); l.ay = clamp(l.y + 0.08, 0, 1); }
      schedule(0);
    });
    li.querySelector(".remove").addEventListener("click", () => {
      state.labels.splice(i, 1);
      renderLabelList();
      schedule(0);
    });
    ul.appendChild(li);
  });
  updateBadges();
}

function updateBadges() {
  document.querySelectorAll("#labels li").forEach((li, i) => {
    const b = li.querySelector(".badge");
    b.textContent = keyFor(i);
    b.classList.toggle("off", !state.labels[i].text.trim());
  });
}

async function nameAllParts(auto) {
  if (!state.imageId) return;
  if (!auto && state.labels.length && !window.confirm("Replace the current labels with suggested ones?")) return;
  const imageId = state.imageId;
  const btn = $("#suggest");
  btn.disabled = true;
  setStatus("Naming the parts of this diagram…");
  try {
    const res = await fetch("/api/autolabel", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_id: imageId, max_labels: 8 }),
    });
    const data = await res.json();
    if (imageId !== state.imageId) return;            // user moved on to another image
    if (!res.ok) { setStatus(data.error || "Naming failed."); return; }
    state.labels = data.labels.map((l) => ({
      text: l.text, x: l.x, y: l.y, pointer: true, ax: l.ax, ay: l.ay,
    }));
    renderLabelList();
    setStatus(state.labels.length
      ? "Parts named. Drag a pointer's ring onto another part and its label renames itself."
      : "No parts found. Add labels by hand.");
    schedule(0);
  } catch {
    setStatus("Could not reach the server.");
  } finally {
    btn.disabled = false;
  }
}

// The pointer was moved to a new spot: name whatever is under it, then rebuild the Braille.
async function renameAtPointer(label, opts = {}) {
  if (!$("#autoname").checked || !aiAvailable) {
    if (!aiAvailable && !hintedNoKey) {
      hintedNoKey = true;
      setStatus("To have parts named automatically, add a free API key in the Labels section. You can always type names by hand.");
    }
    return;
  }
  const rid = (label._rid = (label._rid || 0) + 1);
  const imageId = state.imageId;
  setStatus("Naming the part under the pointer…");
  try {
    const res = await fetch("/api/identify", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_id: imageId, x: label.ax, y: label.ay }),
    });
    const data = await res.json();
    if (rid !== label._rid || imageId !== state.imageId || !state.labels.includes(label)) return;
    if (!res.ok) { setStatus(data.error || "Could not name that part."); return; }
    if (opts.onlyIfEmpty && label.text.trim()) return;   // the user already typed a name
    label.text = data.text;
    renderLabelList();
    setStatus("");
    schedule(0);
  } catch {
    if (rid === label._rid) setStatus("Could not reach the server.");
  }
}

// ---------------------------------------------------------------- processing
async function process() {
  if (!state.imageId) return;
  const mine = ++seq;
  const body = {
    image_id: state.imageId, mode: state.mode, sensitivity: state.sensitivity,
    detail: state.detail, line_mm: state.line_mm, title: state.title,
    ink: state.ink, border: state.border, erase: state.erase,
    labels: activeLabels().map((l) => {
      const o = { text: l.text.trim(), x: l.x, y: l.y };
      if (l.pointer) { o.ax = l.ax; o.ay = l.ay; }
      return o;
    }),
  };
  try {
    const res = await fetch("/api/process", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json();
    if (mine !== seq) return;                         // a newer request superseded this one
    if (!res.ok) { processError = true; setStatus(data.error || "Could not process the image."); return; }
    result = data;
    if (processError) { processError = false; setStatus(""); }
    renderResult();
  } catch {
    if (mine === seq) { processError = true; setStatus("Could not reach the server."); }
  }
}

function renderResult() {
  $("#svgbox").innerHTML = result.svg;
  $("#download").disabled = false;
  renderView();
  renderHandles();

  const w = $("#warnings");
  w.innerHTML = "";
  result.warnings.forEach((t) => {
    const li = document.createElement("li");
    li.textContent = t;
    w.appendChild(li);
  });

  const s = result.stats;
  $("#stats").innerHTML = [
    ["Line width", s.stroke_mm + " mm"],
    ["Page", result.page_mm[0] + " × " + result.page_mm[1] + " mm"],
    ["Path nodes", s.nodes],
    ["File", s.svg_kb + " KB"],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");

  const rows = $("#braille_rows");
  rows.innerHTML = "";
  const addRow = (k, b, t) => {
    const d = document.createElement("div");
    d.className = "braille-row";
    d.innerHTML = `<span class="k"></span><span class="b" aria-hidden="true"></span><span class="t"></span>`;
    d.querySelector(".k").textContent = k;
    d.querySelector(".b").textContent = b;
    d.querySelector(".t").textContent = t;
    rows.appendChild(d);
  };
  if (result.title_braille) addRow("", result.title_braille, "title");
  result.key_braille.forEach((r) => addRow(r.key, r.unicode, r.text));
  $("#braille_key").hidden = rows.children.length === 0;
}

function renderView() {
  const has = !!result;
  $("#empty").hidden = has;
  $("#sheet").hidden = !has || view !== "tactile";
  $("#source").hidden = !has || view !== "source";
}

// ---------------------------------------------------------------- drag handles
function renderHandles() {
  const overlay = $("#overlay");
  // keep keyboard focus on the same handle across re-renders
  const focused = document.activeElement && document.activeElement.dataset
    ? document.activeElement.dataset.hid : null;
  overlay.innerHTML = "";
  const [W, H] = result.page_mm;
  const [dx, dy, dw, dh] = result.diagram_mm;
  const place = (el, nx, ny) => {
    el.style.left = ((dx + nx * dw) / W) * 100 + "%";
    el.style.top = ((dy + ny * dh) / H) * 100 + "%";
  };

  state.erase.forEach((r) => {
    const b = document.createElement("div");
    b.className = "erase-box";
    const [x0, y0] = [(dx + r[0] * dw) / W * 100, (dy + r[1] * dh) / H * 100];
    const [x1, y1] = [(dx + r[2] * dw) / W * 100, (dy + r[3] * dh) / H * 100];
    Object.assign(b.style, { left: x0 + "%", top: y0 + "%", width: x1 - x0 + "%", height: y1 - y0 + "%" });
    overlay.appendChild(b);
  });

  state.labels.forEach((l, i) => {
    const named = !!l.text.trim();
    const m = document.createElement("button");
    m.type = "button";
    m.className = "handle marker" + (named ? "" : " off");
    m.textContent = keyFor(i);
    m.setAttribute("aria-label", named
      ? `Move label ${keyFor(i)}, ${l.text}. Use the arrow keys.`
      : "Move unnamed label. Type its name in the Labels list. Use the arrow keys.");
    m.dataset.hid = `${i}:marker`;
    place(m, l.x, l.y);
    makeDraggable(m, l, "x", "y", place);
    overlay.appendChild(m);

    if (l.pointer) {
      const a = document.createElement("button");
      a.type = "button";
      a.className = "handle anchor";
      a.setAttribute("aria-label", `Move arrow tip for ${l.text || "unnamed label"}. Use the arrow keys.`);
      a.dataset.hid = `${i}:anchor`;
      place(a, l.ax, l.ay);
      makeDraggable(a, l, "ax", "ay", place, () => renameAtPointer(l));
      overlay.appendChild(a);
    }
  });
  if (focused) {
    const again = overlay.querySelector(`[data-hid="${focused}"]`);
    if (again) again.focus({ preventScroll: true });
  }
}

function makeDraggable(el, label, kx, ky, place, onSettle) {
  const toNorm = (cx, cy) => {
    const r = $("#overlay").getBoundingClientRect();
    const [W, H] = result.page_mm;
    const [dx, dy, dw, dh] = result.diagram_mm;
    const mx = ((cx - r.left) / r.width) * W;
    const my = ((cy - r.top) / r.height) * H;
    return [clamp((mx - dx) / dw, 0, 1), clamp((my - dy) / dh, 0, 1)];
  };
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    el.focus();
  });
  el.addEventListener("pointermove", (e) => {
    if (!el.hasPointerCapture(e.pointerId)) return;
    [label[kx], label[ky]] = toNorm(e.clientX, e.clientY);
    el._moved = true;
    place(el, label[kx], label[ky]);
  });
  el.addEventListener("pointerup", (e) => {
    if (!el.hasPointerCapture(e.pointerId)) return;
    el.releasePointerCapture(e.pointerId);
    schedule(0);
    if (el._moved && onSettle) onSettle();
    el._moved = false;
  });
  el.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 0.03 : 0.005;
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (!d) return;
    e.preventDefault();
    label[kx] = clamp(label[kx] + d[0], 0, 1);
    label[ky] = clamp(label[ky] + d[1], 0, 1);
    place(el, label[kx], label[ky]);
    schedule(350);
    if (onSettle) {                                   // wait until the arrow keys go quiet
      clearTimeout(el._settle);
      el._settle = setTimeout(onSettle, 700);
    }
  });
}

// ---------------------------------------------------------------- download
function download() {
  if (!result) return;
  const blob = new Blob([result.svg], { type: "image/svg+xml" });
  const a = document.createElement("a");
  const slug = (state.title || "diagram").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "diagram";
  a.href = URL.createObjectURL(blob);
  a.download = slug + "-tactile.svg";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---------------------------------------------------------------- start
bindControls();
syncControls();
loadSamples().catch(() => setStatus("Could not load the sample diagrams."));
