// Run: python tests/serve_stub.py &   then   npm install jsdom && node ui_test.js  (restart the server between runs)
// Drives the real UI (static/app.js) in jsdom against the real Flask backend (stub vision model).
const { JSDOM } = require("jsdom");
const BASE = "http://127.0.0.1:5055";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
const check = (cond, msg) => { console.log((cond ? "PASS " : "FAIL ") + msg); if (!cond) failures++; };

async function until(fn, label, ms = 6000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { try { if (fn()) return true; } catch {} await sleep(40); }
  console.log("TIMEOUT waiting for: " + label);
  return false;
}

(async () => {
  const dom = await JSDOM.fromURL(BASE + "/", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(new URL(u, BASE), o);
      w.FormData = FormData; w.File = File; w.Blob = Blob;
      w.HTMLElement.prototype.setPointerCapture = function () { this._cap = true; };
      w.HTMLElement.prototype.hasPointerCapture = function () { return !!this._cap; };
      w.HTMLElement.prototype.releasePointerCapture = function () { this._cap = false; };
      w.confirm = () => true;
    },
  });
  const w = dom.window, d = w.document;
  const $ = (s) => d.querySelector(s);
  const $$ = (s) => [...d.querySelectorAll(s)];
  const ev = (el, type, props = {}) => el.dispatchEvent(new w.MouseEvent(type, { bubbles: true, cancelable: true, ...props }));
  const R = () => w.eval("result");
  const S = () => w.eval("state");

  // ---- 1. start up: samples load and the first page renders -------------------------------
  await until(() => $$("#samples button").length === 3 && $("#svgbox svg"), "sample page");
  check($$("#samples button").length === 3, "three sample buttons rendered");
  check(!!$("#svgbox svg"), "tactile SVG rendered for first sample");
  check($$("#labels li").length === 5, "5 label rows for the lens sample");
  check($$("#labels .badge").map((b) => b.textContent).join("") === "abcde", "key letters a-e assigned");
  check($$(".handle.marker").length === 5 && $$(".handle.anchor").length === 5, "5 markers + 5 pointer handles on the sheet");
  check($("#download").disabled === false, "download enabled");

  // ---- 2. no API key yet: provider panel shown, naming hidden -----------------------------
  check($("#keybox").hidden === false && $("#suggest").hidden === true, "no key: key panel visible, naming buttons hidden");
  check($$("#provider option").map((o) => o.value).join() === "gemini,openrouter,custom", "three free provider choices listed");
  check(/Google AI Studio/.test($("#provider_help").textContent) && !!$("#provider_help a[href*='aistudio.google.com']"), "Gemini help text links to the free key page");
  check($("#base_wrap").hidden === true, "base URL hidden for a preset provider");
  $("#provider").value = "custom"; ev($("#provider"), "change");
  check($("#base_wrap").hidden === false, "custom provider reveals the base URL field");
  $("#provider").value = "gemini"; ev($("#provider"), "change");
  check($("#base_wrap").hidden === true, "switching back hides it again");
  ev($("#savekey"), "click");
  await sleep(150);
  check(/Paste your API key/.test($("#status").textContent), "empty key rejected with a clear message");
  $("#apikey").value = "abc"; ev($("#savekey"), "click");
  await until(() => /too short/.test($("#status").textContent), "short key message");
  check(/too short/.test($("#status").textContent), "too-short key rejected by the server");
  $("#apikey").value = "AIza" + "x".repeat(30); ev($("#savekey"), "click");
  await until(() => $("#keybox").hidden, "key accepted");
  check($("#keybox").hidden && !$("#suggest").hidden && !$("#autoname_wrap").hidden, "key accepted: panel hidden, naming controls shown");
  check($("#apikey").value === "", "key field cleared after saving");

  // ---- 3. Braille for the first label ----------------------------------------------------
  const brailleText = () => $("#braille_rows").textContent;
  check(brailleText().includes("⠠⠕⠃⠚⠑⠉⠞"), "key shows 'Object' in Braille (⠠⠕⠃⠚⠑⠉⠞)");

  // ---- 4. drag the Object pointer onto the lens: label + Braille must update --------------
  const overlay = $("#overlay");
  const pxW = 840;
  const pxH = () => R().page_mm[1] / R().page_mm[0] * pxW;
  overlay.getBoundingClientRect = () => ({ left: 0, top: 0, width: pxW, height: pxH(), right: pxW, bottom: pxH() });
  const toClient = (nx, ny) => {
    const [W, H] = R().page_mm, [dx, dy, dw, dh] = R().diagram_mm;
    return { clientX: (dx + nx * dw) / W * pxW, clientY: (dy + ny * dh) / H * pxH() };
  };
  const anchor0 = () => $('.handle.anchor[data-hid="0:anchor"]');
  const identifyCalls = [];
  const realFetch = w.fetch;
  w.fetch = (u, o) => { if (String(u).includes("/api/identify")) identifyCalls.push(JSON.parse(o.body)); return realFetch(u, o); };

  let a = anchor0();
  ev(a, "pointerdown", toClient(0.2, 0.43));
  ev(a, "pointermove", toClient(0.5, 0.25));                 // onto the lens
  ev(a, "pointerup", toClient(0.5, 0.25));
  await until(() => S().labels[0].text === "Converging lens", "rename to Converging lens");
  check(identifyCalls.length === 1, "exactly one /api/identify call for one drag");
  check(Math.abs(identifyCalls[0].x - 0.5) < 0.02 && Math.abs(identifyCalls[0].y - 0.25) < 0.02, "identify got the pointer's new position");
  check(S().labels[0].text === "Converging lens", "label renamed from Object to Converging lens");
  const OBJECT = "⠠⠕⠃⠚⠑⠉⠞", CONV = "⠠⠉⠕⠝⠧⠑⠗⠛⠊⠝⠛";
  const count = (hay, needle) => hay.split(needle).length - 1;
  await until(() => !brailleText().includes(OBJECT), "old 'Object' Braille to disappear");
  check(!brailleText().includes(OBJECT), "the old 'Object' Braille entry is gone from the key");
  const keyRows = [...$$("#braille_rows .braille-row")].filter((r) => /^[a-z]/.test(r.textContent));
  check(keyRows.length === 5, "key lists 5 entries (a-e)");
  check(keyRows[0].textContent.startsWith("a" + CONV) && keyRows[1].textContent.startsWith("b" + CONV),
        "entries a and b both read 'Converging lens' in Braille (a was just renamed from Object)");
  check($$("#labels input[type=text]")[0].value === "Converging lens", "label text box shows the new name");
  check(R().key_braille[0].text === "Converging lens" && R().key_braille[0].key === "a", "server result: key entry 'a' is now Converging lens");

  // ---- 5. drag to the right third: becomes Image ------------------------------------------
  a = anchor0();
  ev(a, "pointerdown", toClient(0.5, 0.25));
  ev(a, "pointermove", toClient(0.8, 0.64));
  ev(a, "pointerup", toClient(0.8, 0.64));
  await until(() => S().labels[0].text === "Image", "rename to Image");
  check(S().labels[0].text === "Image", "dragging to the right part renames it Image");

  // ---- 6. a click without moving must not call the model ---------------------------------
  const before = identifyCalls.length;
  a = anchor0();
  ev(a, "pointerdown", toClient(0.8, 0.64)); ev(a, "pointerup", toClient(0.8, 0.64));
  await sleep(400);
  check(identifyCalls.length === before, "click without moving makes no model call");

  // ---- 7. moving the key-letter marker (not the pointer) must not rename ------------------
  const m = $('.handle.marker[data-hid="1:marker"]');
  ev(m, "pointerdown", toClient(0.5, 0.1)); ev(m, "pointermove", toClient(0.6, 0.1)); ev(m, "pointerup", toClient(0.6, 0.1));
  await sleep(500);
  check(identifyCalls.length === before && S().labels[1].text === "Converging lens", "moving a marker repositions it but does not rename");
  check(Math.abs(S().labels[1].x - 0.6) < 0.02, "marker position updated in state");

  // ---- 8. keyboard: arrow keys move a pointer and then rename --------------------------------
  const calls8 = identifyCalls.length;
  a = anchor0(); a.focus();
  const key = (el, k, shift) => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: k, shiftKey: shift, bubbles: true, cancelable: true }));
  for (let i = 0; i < 6; i++) key(a, "ArrowLeft", true);          // 6 x 3% = 18% to the left
  await until(() => identifyCalls.length > calls8, "keyboard rename call", 4000);
  check(identifyCalls.length === calls8 + 1, "six arrow presses produce ONE rename call after they settle");
  check(Math.abs(identifyCalls[identifyCalls.length - 1].x - 0.62) < 0.02, "rename call used the keyboard-moved position (x = 0.62)");
  await until(() => S().labels[0].text === "Converging lens", "keyboard rename result");
  check(S().labels[0].text === "Converging lens", "pointer nudged into the lens region renames the label");
  check(d.activeElement && d.activeElement.dataset.hid === "0:anchor", "keyboard focus stays on the same pointer after the sheet re-renders");

  // ---- 9. autoname off: moving a pointer must not call the model --------------------------
  $("#autoname").checked = false;
  const calls9 = identifyCalls.length;
  a = anchor0();
  ev(a, "pointerdown", toClient(0.5, 0.2)); ev(a, "pointermove", toClient(0.2, 0.4)); ev(a, "pointerup", toClient(0.2, 0.4));
  await sleep(500);
  check(identifyCalls.length === calls9, "rename-on-move switched off: no model call");
  $("#autoname").checked = true;

  // ---- 10. "Name all parts" replaces labels with pointers pre-set ---------------------------
  ev($("#suggest"), "click");
  await until(() => S().labels.length === 3 && S().labels[0].pointer, "name all parts");
  check(S().labels.length === 3 && S().labels.every((l) => l.pointer), "Name all parts: 3 labels, all with pointers");
  await until(() => $$(".handle.anchor").length === 3, "3 pointer handles");
  check($$(".handle.anchor").length === 3, "3 pointer handles rendered");

  // ---- 11. upload path: image in -> page out fast -> names arrive after ------------------------
  const fs = require("fs");
  const bytes = fs.readFileSync(require("path").join(__dirname, "..", "examples", "projectile_tactile.png"));
  const t0 = Date.now();
  w.eval("window.__up = upload");
  const p = w.__up(new File([bytes], "my-diagram.png", { type: "image/png" }));
  await until(() => S().imageId && !S().imageId.startsWith("sample:") && R() && $("#svgbox svg") && $("#title").value === "my diagram", "upload page");
  const tPage = Date.now() - t0;
  check(!S().imageId.startsWith("sample:"), "uploaded image gets its own id");
  check($("#title").value === "my diagram", "title defaults to the file name");
  await until(() => S().labels.length === 3 && S().labels.every((l) => l.pointer), "auto-named after upload");
  check(S().labels.length === 3, "after upload, parts were named automatically (with pointers)");
  console.log(`   upload -> tactile page on screen: ${tPage} ms`);

  console.log(failures ? `\n${failures} FAILED` : "\nALL UI CHECKS PASSED");
  process.exit(failures ? 1 : 0);
})();
