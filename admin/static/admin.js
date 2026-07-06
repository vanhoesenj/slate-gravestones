/* Slate Gravestones — admin SPA (vanilla JS) */
const $ = (s) => document.querySelector(s);
const api = async (url, opts = {}) => {
  if (opts.body && typeof opts.body !== "string") {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(opts.body);
  }
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---------- tabs ---------- */
document.querySelectorAll("#tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll("#tabs button, .tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#tab-" + b.dataset.tab).classList.add("active");
    if (b.dataset.tab === "cemeteries") setTimeout(() => cemMap?.resize(), 50);
  }));

async function refreshSummary() {
  const s = await api("/api/summary");
  $("#summary").textContent =
    `${s.cemeteries} cemeteries · ${s.stones} gravestones · ${s.photos} photos · ` +
    `${s.untagged} untagged · ${s.unsynced} not on R2`;
  if (!$("#importDir").value && s.source_dir) $("#importDir").value = s.source_dir;
  window._sum = s;
}

/* ---------- cemeteries ---------- */
let cemMap, cemMarker, cemeteries = [];

function initCemMap() {
  cemMap = new maplibregl.Map({
    container: "cemMap",
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [-73.2, 43.5], zoom: 5,
  });
  cemMap.addControl(new maplibregl.NavigationControl());
  cemMap.on("click", (e) => {
    if ($("#cemForm").classList.contains("hidden")) return;
    $("#cemLat").value = e.lngLat.lat.toFixed(6);
    $("#cemLng").value = e.lngLat.lng.toFixed(6);
    setCemMarker(e.lngLat.lng, e.lngLat.lat);
  });
}
function setCemMarker(lng, lat) {
  if (cemMarker) cemMarker.remove();
  cemMarker = new maplibregl.Marker({ color: "#35606e" })
    .setLngLat([lng, lat]).addTo(cemMap);
}

async function loadCemeteries() {
  cemeteries = await api("/api/cemeteries");
  $("#cemList").innerHTML = cemeteries.map((c) =>
    `<li data-id="${c.id}"><span>${esc(c.name)}</span>
     <span class="n">${esc(c.state || c.country)} · ${c.stones} gravestones</span></li>`).join("");
  const opts = cemeteries.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  $("#importCem").innerHTML = opts;
  $("#sdCem").innerHTML = opts;
  $("#stoneCemFilter").innerHTML = `<option value="">All cemeteries</option>` + opts;
  document.querySelectorAll("#cemList li").forEach((li) =>
    li.addEventListener("click", () => editCem(+li.dataset.id)));
}

function showCemForm(c) {
  $("#cemForm").classList.remove("hidden");
  $("#cemId").value = c?.id || "";
  $("#cemName").value = c?.name || "";
  $("#cemCity").value = c?.city || "";
  $("#cemState").value = c?.state || "";
  $("#cemCountry").value = c?.country || "United States";
  $("#cemLat").value = c?.lat ?? "";
  $("#cemLng").value = c?.lng ?? "";
  $("#cemNotes").value = c?.notes || "";
  $("#cemDelete").classList.toggle("hidden", !c);
  if (c?.lat != null) { setCemMarker(c.lng, c.lat); cemMap.flyTo({ center: [c.lng, c.lat], zoom: 13 }); }
}
function editCem(id) { showCemForm(cemeteries.find((c) => c.id === id)); }

$("#cemNew").addEventListener("click", () => showCemForm(null));
$("#cemCancel").addEventListener("click", () => $("#cemForm").classList.add("hidden"));
$("#cemForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = {
    name: $("#cemName").value, city: $("#cemCity").value,
    state: $("#cemState").value, country: $("#cemCountry").value,
    lat: parseFloat($("#cemLat").value) || null,
    lng: parseFloat($("#cemLng").value) || null,
    notes: $("#cemNotes").value,
  };
  const id = $("#cemId").value;
  if (id) await api(`/api/cemeteries/${id}`, { method: "PUT", body: d });
  else await api("/api/cemeteries", { method: "POST", body: d });
  $("#cemForm").classList.add("hidden");
  await loadCemeteries(); refreshSummary();
});
$("#cemDelete").addEventListener("click", async () => {
  const id = $("#cemId").value;
  if (!id || !confirm("Delete this cemetery?")) return;
  try { await api(`/api/cemeteries/${id}`, { method: "DELETE" }); }
  catch (err) { alert(err.message); return; }
  $("#cemForm").classList.add("hidden");
  await loadCemeteries(); refreshSummary();
});
$("#geoBtn").addEventListener("click", async () => {
  const q = $("#geoQuery").value.trim();
  if (!q) return;
  const r = await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=5&q=" +
    encodeURIComponent(q));
  const res = await r.json();
  $("#geoResults").innerHTML = res.map((x, i) =>
    `<div data-i="${i}">${esc(x.display_name)}</div>`).join("") || "<div>No results</div>";
  document.querySelectorAll("#geoResults div[data-i]").forEach((el) =>
    el.addEventListener("click", () => {
      const x = res[+el.dataset.i];
      $("#cemLat").value = (+x.lat).toFixed(6);
      $("#cemLng").value = (+x.lon).toFixed(6);
      setCemMarker(+x.lon, +x.lat);
      cemMap.flyTo({ center: [+x.lon, +x.lat], zoom: 14 });
      $("#geoResults").innerHTML = "";
    }));
});

/* ---------- import ---------- */
let scanFiles = [], selected = new Set();

$("#scanBtn").addEventListener("click", async () => {
  $("#impStatus").textContent = "Scanning…";
  try {
    const r = await api("/api/import/scan?dir=" + encodeURIComponent($("#importDir").value));
    scanFiles = r.files; selected.clear();
    $("#impStatus").textContent = `${r.files.length} new photo(s) found`;
    // group by subfolder (e.g. one folder per cemetery)
    const groups = {};
    r.files.forEach((f, i) => {
      const dir = f.rel.includes("/") ? f.rel.slice(0, f.rel.lastIndexOf("/")) : "";
      (groups[dir] = groups[dir] || []).push(i);
    });
    $("#importGrid").innerHTML = Object.keys(groups).sort().map((dir) => `
      <div class="impdir">
        <span>${esc(dir) || "(top level)"}</span>
        <button class="seldir" data-dir="${esc(dir)}">select folder</button>
      </div>` +
      groups[dir].map((i) => {
        const f = scanFiles[i];
        return `<div class="card" data-i="${i}">
          <img loading="lazy" src="/orig?path=${encodeURIComponent(f.path)}">
          <div class="cap" title="${esc(f.rel)}">${esc(f.name)}</div></div>`;
      }).join("")).join("");
    document.querySelectorAll("#importGrid .card").forEach((el) =>
      el.addEventListener("click", () => {
        const i = +el.dataset.i;
        selected.has(i) ? selected.delete(i) : selected.add(i);
        el.classList.toggle("sel");
        updateImpButtons();
      }));
    document.querySelectorAll("#importGrid .seldir").forEach((b) =>
      b.addEventListener("click", () => {
        const idx = groups[b.dataset.dir];
        const allOn = idx.every((i) => selected.has(i));
        idx.forEach((i) => allOn ? selected.delete(i) : selected.add(i));
        document.querySelectorAll("#importGrid .card").forEach((el) =>
          el.classList.toggle("sel", selected.has(+el.dataset.i)));
        if (!allOn) matchCemetery(b.dataset.dir);
        updateImpButtons();
      }));
    updateImpButtons();
  } catch (err) { $("#impStatus").textContent = err.message; }
});
function matchCemetery(dir) {
  // if the folder name matches a cemetery name, pre-select it in the dropdown
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const d = norm(dir.split("/").pop());
  if (!d) return;
  const hit = cemeteries.find((c) => {
    const n = norm(c.name);
    return n === d || n.includes(d) || d.includes(n);
  });
  if (hit) $("#importCem").value = hit.id;
}

function updateImpButtons() {
  $("#impOnePer").disabled = selected.size === 0 || !$("#importCem").value;
  $("#impGroup").disabled = selected.size < 2 || !$("#importCem").value;
}
async function runImport(groups) {
  const cem = +$("#importCem").value;
  let done = 0;
  for (const g of groups) {
    $("#impStatus").textContent = `Importing ${++done}/${groups.length}…`;
    try {
      const r = await api("/api/import", { method: "POST",
        body: { paths: g, cemetery_id: cem } });
      r.errors.forEach((e) => console.warn(e));
    } catch (err) { alert(err.message); break; }
  }
  $("#impStatus").textContent = "Done. Rescanning…";
  selected.clear();
  $("#scanBtn").click();
  refreshSummary(); loadStones();
}
$("#impOnePer").addEventListener("click", () =>
  runImport([...selected].sort().map((i) => [scanFiles[i].path])));
$("#impGroup").addEventListener("click", () =>
  runImport([[...selected].sort().map((i) => scanFiles[i].path)]));
$("#importCem").addEventListener("change", updateImpButtons);

/* ---------- stones ---------- */
let cats = [], curStone = null;

async function loadCats() { cats = await api("/api/categories"); renderCatAdmin(); }

async function loadStones() {
  const p = new URLSearchParams();
  if ($("#stoneCemFilter").value) p.set("cemetery", $("#stoneCemFilter").value);
  if ($("#stoneUntagged").checked) p.set("untagged", "1");
  if ($("#stoneSearch").value) p.set("q", $("#stoneSearch").value);
  const rows = await api("/api/stones?" + p);
  $("#stoneGrid").innerHTML = rows.map((s) =>
    `<div class="card ${curStone === s.id ? "sel" : ""}" data-id="${s.id}">
       ${s.thumb ? `<img loading="lazy" src="/media/${s.thumb}/thumb.jpg">` : ""}
       <span class="badge ${s.ntags ? "" : "warn"}">${s.ntags ? s.ntags + " tags" : "untagged"}</span>
       <div class="cap">#${s.id} ${esc(s.title || "")} ${s.year || ""} · ${esc(s.cemetery)}</div>
     </div>`).join("") || "<p class='hint'>No gravestones match.</p>";
  document.querySelectorAll("#stoneGrid .card").forEach((el) =>
    el.addEventListener("click", () => openStone(+el.dataset.id)));
}
["stoneCemFilter", "stoneUntagged"].forEach((id) =>
  $("#" + id).addEventListener("change", loadStones));
$("#stoneSearch").addEventListener("input", () => {
  clearTimeout(window._st); window._st = setTimeout(loadStones, 300);
});

async function openStone(id) {
  const s = await api("/api/stones/" + id);
  curStone = id;
  $("#stoneHint").classList.add("hidden");
  $("#stoneDetail").classList.remove("hidden");
  $("#sdTitleHead").textContent = `Gravestone #${id}`;
  $("#sdTitle").value = s.title || "";
  renderPersons(s.persons?.length ? s.persons : [{}]);
  $("#sdTrans").value = s.transcription || "";
  $("#sdNotes").value = s.notes || "";
  $("#sdCem").value = s.cemetery_id;
  $("#sdPhotos").innerHTML = s.photos.map((p) =>
    `<div class="ph ${p.is_primary ? "primary" : ""}">
       <a href="/media/${p.id}/disp.jpg" target="_blank"><img src="/media/${p.id}/thumb.jpg"></a>
       <div class="tools">
         <button data-act="primary" data-id="${p.id}" title="Set as primary">★</button>
         <button data-act="enh" data-id="${p.id}" title="View enhanced (carving/inscription)">◐</button>
         <button data-act="del" data-id="${p.id}" title="Remove photo">✕</button>
       </div></div>`).join("");
  $("#sdPhotos").querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", async () => {
      if (b.dataset.act === "enh") {
        window.open(`/media/${b.dataset.id}/enh.jpg`, "_blank");
        return;
      }
      if (b.dataset.act === "primary")
        await api(`/api/photos/${b.dataset.id}/primary`, { method: "PUT" });
      else if (confirm("Remove this photo from the library?"))
        await api(`/api/photos/${b.dataset.id}`, { method: "DELETE" });
      openStone(id); loadStones();
    }));
  renderTagGroups(new Set(s.tag_ids));
  document.querySelectorAll("#stoneGrid .card").forEach((el) =>
    el.classList.toggle("sel", +el.dataset.id === id));
}

function personRow(p = {}) {
  const div = document.createElement("div");
  div.className = "prow";
  div.innerHTML = `
    <input class="pname" placeholder="Name" value="${esc(p.name || "")}">
    <input class="pbirth" type="number" min="1500" max="2100" placeholder="Birth" value="${p.birth ?? ""}">
    <input class="pdeath" type="number" min="1500" max="2100" placeholder="Death" value="${p.death ?? ""}">
    <button type="button" class="pdel" title="Remove person">✕</button>`;
  div.querySelector(".pdel").addEventListener("click", () => {
    div.remove();
    if (!$("#sdPersons").children.length) renderPersons([{}]);
  });
  return div;
}
function renderPersons(list) {
  const box = $("#sdPersons");
  box.innerHTML = "";
  list.forEach((p) => box.appendChild(personRow(p)));
}
$("#addPerson").addEventListener("click", () =>
  $("#sdPersons").appendChild(personRow()));
function gatherPersons() {
  return [...$("#sdPersons").querySelectorAll(".prow")].map((r) => ({
    name: r.querySelector(".pname").value.trim(),
    birth: parseInt(r.querySelector(".pbirth").value) || null,
    death: parseInt(r.querySelector(".pdeath").value) || null,
  })).filter((p) => p.name || p.birth || p.death);
}

function renderTagGroups(selectedIds) {
  $("#sdTagGroups").innerHTML = cats.map((c) => `
    <div class="taggroup" data-cat="${c.id}" data-single="${c.single}">
      <h4>${esc(c.name)}${c.single ? " (pick one)" : ""}</h4>
      <div class="chips">
        ${c.tags.map((t) =>
          `<span class="chip ${selectedIds.has(t.id) ? "on" : ""}" data-id="${t.id}">${esc(t.name)}</span>`).join("")}
        <span class="chip add" data-cat="${c.id}">+ add</span>
      </div>
    </div>`).join("");
  $("#sdTagGroups").querySelectorAll(".chip:not(.add)").forEach((chip) =>
    chip.addEventListener("click", () => {
      const grp = chip.closest(".taggroup");
      if (grp.dataset.single === "1" && !chip.classList.contains("on"))
        grp.querySelectorAll(".chip.on").forEach((c) => c.classList.remove("on"));
      chip.classList.toggle("on");
    }));
  $("#sdTagGroups").querySelectorAll(".chip.add").forEach((chip) =>
    chip.addEventListener("click", async () => {
      const name = prompt("New tag name:");
      if (!name) return;
      try {
        const r = await api("/api/tags", { method: "POST",
          body: { category_id: +chip.dataset.cat, name } });
        await loadCats();
        const on = new Set([...$("#sdTagGroups").querySelectorAll(".chip.on")]
          .map((c) => +c.dataset.id));
        on.add(r.id);
        renderTagGroups(on);
      } catch (err) { alert(err.message); }
    }));
}

$("#sdForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api(`/api/stones/${curStone}`, { method: "PUT", body: {
    title: $("#sdTitle").value,
    persons: gatherPersons(),
    transcription: $("#sdTrans").value,
    notes: $("#sdNotes").value,
    cemetery_id: +$("#sdCem").value,
  }});
  const tag_ids = [...$("#sdTagGroups").querySelectorAll(".chip.on")].map((c) => +c.dataset.id);
  await api(`/api/stones/${curStone}/tags`, { method: "PUT", body: { tag_ids } });
  $("#sdStatus").textContent = "Saved ✓";
  setTimeout(() => ($("#sdStatus").textContent = ""), 1500);
  loadStones(); refreshSummary();
});
$("#sdDelete").addEventListener("click", async () => {
  if (!confirm("Delete this gravestone and its photos from the library?")) return;
  await api(`/api/stones/${curStone}`, { method: "DELETE" });
  $("#stoneDetail").classList.add("hidden");
  $("#stoneHint").classList.remove("hidden");
  curStone = null;
  loadStones(); refreshSummary();
});

/* ---------- tags admin ---------- */
function renderCatAdmin() {
  $("#catList").innerHTML = cats.map((c) => `
    <div class="catblock">
      <h3>${esc(c.name)} <small class="hint">${c.single ? "single-select" : "multi-select"}</small></h3>
      ${c.tags.map((t) =>
        `<span class="tagrow">${esc(t.name)} <span class="use">${t.used}</span>
         <button class="ren" data-id="${t.id}" data-name="${esc(t.name)}" title="Rename tag">✎</button>
         <button class="del" data-id="${t.id}" data-used="${t.used}" title="Delete tag">✕</button></span>`).join("")}
      <span class="tagrow"><button class="addtag" data-cat="${c.id}">+ add tag</button></span>
    </div>`).join("");
  $("#catList").querySelectorAll("button.ren").forEach((b) =>
    b.addEventListener("click", async () => {
      const name = prompt("Rename tag (updates it everywhere):", b.dataset.name);
      if (!name || name === b.dataset.name) return;
      try { await api(`/api/tags/${b.dataset.id}`, { method: "PUT",
        body: { name } }); loadCats(); }
      catch (err) { alert(err.message); }
    }));
  $("#catList").querySelectorAll("button.del").forEach((b) =>
    b.addEventListener("click", async () => {
      const used = +b.dataset.used;
      const msg = used
        ? `This tag is on ${used} gravestone(s). Delete it and remove it from all of them?`
        : "Delete this tag?";
      if (!confirm(msg)) return;
      try { await api(`/api/tags/${b.dataset.id}?force=1`, { method: "DELETE" });
        loadCats(); }
      catch (err) { alert(err.message); }
    }));
  $("#catList").querySelectorAll(".addtag").forEach((b) =>
    b.addEventListener("click", async () => {
      const name = prompt("New tag name:");
      if (!name) return;
      try { await api("/api/tags", { method: "POST",
        body: { category_id: +b.dataset.cat, name } }); loadCats(); }
      catch (err) { alert(err.message); }
    }));
}
$("#catForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/categories", { method: "POST",
      body: { name: $("#catName").value, single: $("#catSingle").checked } });
    $("#catName").value = "";
    loadCats();
  } catch (err) { alert(err.message); }
});

/* ---------- publish ---------- */
$("#syncBtn").addEventListener("click", async () => {
  $("#syncStatus").textContent = "Syncing…";
  try {
    let remaining = 1, total = 0;
    while (remaining > 0) {
      const r = await api("/api/r2/sync", { method: "POST", body: { limit: 10 } });
      total += r.done.length;
      remaining = r.remaining;
      if (r.errors.length) throw new Error(r.errors[0].error);
      $("#syncStatus").textContent = `Uploaded ${total}, ${remaining} remaining…`;
    }
    $("#syncStatus").textContent = `All images synced ✓ (${total} uploaded)`;
  } catch (err) { $("#syncStatus").textContent = "Error: " + err.message; }
  refreshSummary();
});
$("#exportBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/publish", { method: "POST" });
    $("#exportStatus").textContent =
      `Exported ${r.stones} stones, ${r.cemeteries} cemeteries ✓`;
  } catch (err) { $("#exportStatus").textContent = "Error: " + err.message; }
});
async function refreshDrafts() {
  const s = await api("/api/drafts/status");
  $("#applyDraftsBtn").disabled = !s.found || s.error;
  $("#draftStatus").textContent = s.error ? "Drafts file unreadable: " + s.error
    : s.found ? `${s.count} draft(s) ready to apply`
    : "No drafts file (ask Claude to transcribe a batch — it writes data/transcription_drafts.json)";
}
$("#applyDraftsBtn").addEventListener("click", async () => {
  try {
    const r = await api("/api/drafts/apply", { method: "POST" });
    $("#draftStatus").textContent =
      `Applied ${r.applied} · skipped ${r.skipped} (fields already filled)` +
      (r.missing ? ` · ${r.missing} unknown stone id(s)` : "");
    loadStones(); refreshSummary();
  } catch (err) { $("#draftStatus").textContent = "Error: " + err.message; }
});

function renderPubStatus() {
  const s = window._sum || {};
  $("#pubStatus").innerHTML = s.r2_configured
    ? "<p>R2 is configured.</p>"
    : "<p class='warn'>R2 is NOT configured — edit <code>config.json</code> " +
      "(see README “Cloudflare R2 setup”). You can import and tag now and sync later.</p>";
}

/* ---------- init ---------- */
(async function init() {
  initCemMap();
  await refreshSummary();
  await loadCemeteries();
  await loadCats();
  await loadStones();
  renderPubStatus();
  refreshDrafts();
  document.querySelector('[data-tab="publish"]').addEventListener("click", () => {
    renderPubStatus();
    refreshDrafts();
  });
})();
