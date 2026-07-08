/* Slate Gravestones — public site */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let DB, MORPHO = null, IMG = "", map, tagChart, decadeChart, pcChart;
const cemById = {}, tagById = {}, catById = {};
const F = { country: "", state: "", cemetery: "", yearMin: null, yearMax: null,
            tags: new Set(), q: "" };
const GALLERY_PAGE = 120;
let galleryShown = GALLERY_PAGE;
let galleryView = "photos";  // "photos" | "outlines"

const PALETTE = ["#4a3f63", "#b3823c", "#7c6a9c", "#5a6470", "#9b3b7a",
  "#4a7c59", "#b3552f", "#6d8196", "#8c7a4e", "#54838c", "#8c4e5b", "#2b2433"];

const imgUrl = (photoId, kind) => `${IMG}/img/${photoId}/${kind}.jpg`;
// " · 1745–1794", " · d. 1794", " · 1852–1863" (multi-person range), or ""
function yearsOf(s) {
  const ps = s.persons || [];
  if (ps.length === 1) {
    const p = ps[0];
    if (p.birth && p.death) return ` · ${p.birth}–${p.death}`;
    if (p.death) return ` · d. ${p.death}`;
    if (p.birth) return ` · b. ${p.birth}`;
  }
  if (ps.length > 1) {
    const deaths = ps.map((p) => p.death).filter(Boolean);
    if (deaths.length) {
      const lo = Math.min(...deaths), hi = Math.max(...deaths);
      return lo === hi ? ` · d. ${lo}` : ` · ${lo}–${hi}`;
    }
  }
  return s.birth && s.year ? ` · ${s.birth}–${s.year}` :
    s.year ? ` · d. ${s.year}` :
    s.birth ? ` · b. ${s.birth}` : "";
}
const personLine = (p) => esc(p.name || "—") +
  (p.birth && p.death ? `, ${p.birth}–${p.death}` :
   p.death ? `, d. ${p.death}` : p.birth ? `, b. ${p.birth}` : "");

/* ---------- filtering ---------- */
function filteredStones() {
  return DB.stones.filter((s) => {
    const c = cemById[s.cem];
    if (F.country && c.country !== F.country) return false;
    if (F.state && c.state !== F.state) return false;
    if (F.cemetery && String(s.cem) !== F.cemetery) return false;
    if (F.yearMin != null && (s.year == null || s.year < F.yearMin)) return false;
    if (F.yearMax != null && (s.year == null || s.year > F.yearMax)) return false;
    if (F.q) {
      const names = (s.persons || []).map((p) => p.name).join(" ");
      const hay = `${s.title} ${names} ${s.trans || ""} ${s.notes || ""} ${c.name} ${c.city}`
        .toLowerCase();
      if (!hay.includes(F.q)) return false;
    }
    // OR within a category, AND across categories:
    // urn + willow = either; urn + Ogee Top = urn on an ogee-top marker
    if (F.tags.size) {
      const byCat = {};
      for (const t of F.tags) {
        const cat = tagById[t]?.cat;
        (byCat[cat] = byCat[cat] || []).push(t);
      }
      for (const ids of Object.values(byCat))
        if (!ids.some((t) => s.tags.includes(t))) return false;
    }
    return true;
  });
}

/* ---------- filter UI ---------- */
function buildFilterOptions() {
  const countries = [...new Set(DB.cemeteries.map((c) => c.country).filter(Boolean))].sort();
  const states = [...new Set(DB.cemeteries
    .filter((c) => !F.country || c.country === F.country)
    .map((c) => c.state).filter(Boolean))].sort();
  const cems = DB.cemeteries.filter((c) =>
    (!F.country || c.country === F.country) && (!F.state || c.state === F.state));
  fillSelect($("#fCountry"), countries, F.country);
  fillSelect($("#fState"), states, F.state);
  fillSelect($("#fCemetery"), cems.map((c) => [c.id, c.name]), F.cemetery);
}
function fillSelect(sel, items, val) {
  const first = sel.querySelector("option");
  sel.innerHTML = "";
  sel.appendChild(first);
  for (const it of items) {
    const o = document.createElement("option");
    if (Array.isArray(it)) { o.value = it[0]; o.textContent = it[1]; }
    else { o.value = it; o.textContent = it; }
    sel.appendChild(o);
  }
  sel.value = val;
}

const openCats = new Set();  // which sidebar groups the user has expanded

function buildTagFilters() {
  // counts within the current filtered set (ignoring each tag's own filter is
  // fancier; keeping it simple and fast)
  const counts = {};
  for (const s of filteredStones()) for (const t of s.tags) counts[t] = (counts[t] || 0) + 1;
  $("#tagFilters").innerHTML = DB.categories.map((cat) => {
    const tags = DB.tags.filter((t) => t.cat === cat.id &&
      ((counts[t.id] || 0) > 0 || F.tags.has(t.id)));
    if (!tags.length) return "";
    // a group with an active selection stays open
    const open = openCats.has(cat.id) || tags.some((t) => F.tags.has(t.id));
    return `<div class="tgroup ${open ? "open" : ""}" data-cat="${cat.id}">
      <h3>${esc(cat.name)} <span class="tw">${open ? "▾" : "▸"}</span></h3>
      <div class="chips">` +
      tags.map((t) =>
        `<span class="chip ${F.tags.has(t.id) ? "on" : ""}" data-id="${t.id}">
           ${esc(t.name)} <span class="n">${counts[t.id] || 0}</span></span>`).join("") +
      `</div></div>`;
  }).join("");
  $("#tagFilters").querySelectorAll(".tgroup h3").forEach((h) =>
    h.addEventListener("click", () => {
      const g = h.parentElement, id = +g.dataset.cat;
      g.classList.toggle("open");
      h.querySelector(".tw").textContent =
        g.classList.contains("open") ? "▾" : "▸";
      g.classList.contains("open") ? openCats.add(id) : openCats.delete(id);
    }));
  $("#tagFilters").querySelectorAll(".chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      const id = +chip.dataset.id;
      F.tags.has(id) ? F.tags.delete(id) : F.tags.add(id);
      update();
    }));
}

["fCountry", "fState", "fCemetery"].forEach((id) =>
  $("#" + id).addEventListener("change", (e) => {
    F[{ fCountry: "country", fState: "state", fCemetery: "cemetery" }[id]] = e.target.value;
    if (id === "fCountry") { F.state = ""; F.cemetery = ""; }
    if (id === "fState") F.cemetery = "";
    update();
  }));
["fYearMin", "fYearMax"].forEach((id) =>
  $("#" + id).addEventListener("change", (e) => {
    F[id === "fYearMin" ? "yearMin" : "yearMax"] =
      e.target.value === "" ? null : +e.target.value;
    update();
  }));
$("#fSearch").addEventListener("input", () => {
  clearTimeout(window._sq);
  window._sq = setTimeout(() => {
    F.q = $("#fSearch").value.trim().toLowerCase();
    update();
  }, 250);
});
$("#clearBtn").addEventListener("click", () => {
  F.country = F.state = F.cemetery = "";
  F.yearMin = F.yearMax = null;
  F.tags.clear();
  F.q = "";
  $("#fSearch").value = "";
  $("#fYearMin").value = $("#fYearMax").value = "";
  update();
});

/* ---------- map ---------- */
function initMap() {
  map = new maplibregl.Map({
    container: "map",
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [-73.2, 43.4], zoom: 4.6,
  });
  map.addControl(new maplibregl.NavigationControl());
  map.on("load", () => {
    map.addSource("cems", { type: "geojson", data: cemGeojson() });
    map.addLayer({
      id: "cem-circles", type: "circle", source: "cems",
      paint: {
        "circle-radius": ["+", 5, ["*", 1.4, ["sqrt", ["get", "count"]]]],
        "circle-color": "#4a3f63", "circle-opacity": 0.85,
        "circle-stroke-color": "#f7f5f0", "circle-stroke-width": 1.5,
      },
    });
    map.addLayer({
      id: "cem-labels", type: "symbol", source: "cems",
      layout: { "text-field": ["get", "count"], "text-size": 10,
                "text-font": ["Noto Sans Regular"] },
      paint: { "text-color": "#f7f5f0" },
    });
    map.on("click", "cem-circles", (e) => {
      const p = e.features[0].properties;
      new maplibregl.Popup({ offset: 10, maxWidth: "290px" })
        .setLngLat(e.features[0].geometry.coordinates)
        .setHTML(cemProfileHTML(p.id))
        .addTo(map);
    });
    map.on("mouseenter", "cem-circles", () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", "cem-circles", () => map.getCanvas().style.cursor = "");
    fitToData();
  });
}
function cemProfileHTML(cemId) {
  const c = cemById[cemId];
  const list = filteredStones().filter((s) => s.cem === cemId);
  // death-year span across all persons (falling back to stone year)
  const years = [];
  for (const s of list) {
    for (const p of (s.persons || [])) if (p.death) years.push(p.death);
    if (!(s.persons || []).some((p) => p.death) && s.year) years.push(s.year);
  }
  const span = years.length
    ? `${Math.min(...years)}–${Math.max(...years)}` : "—";
  // most common shape among these stones
  const shapeCat = DB.categories.find((x) => x.name === "Shape");
  let topShape = "";
  if (shapeCat) {
    const freq = {};
    for (const s of list) for (const t of s.tags) {
      const tag = tagById[t];
      if (tag && tag.cat === shapeCat.id) freq[tag.name] = (freq[tag.name] || 0) + 1;
    }
    const top = Object.entries(freq).sort((a, b) => b[1] - a[1])[0];
    if (top) topShape = `${top[0]} (${top[1]})`;
  }
  // language mix among inscribed stones
  const langs = list.map(langOf).filter(Boolean);
  const welsh = langs.filter((L) => L !== "English").length;
  const langLine = langs.length
    ? `${Math.round(100 * welsh / langs.length)}% Welsh of ${langs.length} inscribed`
    : "no transcriptions yet";
  return `<div class="cemPopup">
    <strong>${esc(c.name)}</strong>
    <span>${esc([c.city, c.state].filter(Boolean).join(", "))}</span>
    <table>
      <tr><td>Gravestones</td><td>${list.length}${F.tags.size || F.q || F.yearMin != null || F.yearMax != null ? " (filtered)" : ""}</td></tr>
      <tr><td>Death years</td><td>${span}</td></tr>
      ${topShape ? `<tr><td>Top shape</td><td>${esc(topShape)}</td></tr>` : ""}
      <tr><td>Language</td><td>${langLine}</td></tr>
    </table>
    <a href="#" onclick="setCem(${cemId});return false">filter to this cemetery →</a>
  </div>`;
}

window.setCem = (id) => {
  F.cemetery = String(id);
  const c = cemById[id];
  F.country = c.country || ""; F.state = c.state || "";
  update();
};
function cemGeojson() {
  const per = {};
  for (const s of filteredStones()) per[s.cem] = (per[s.cem] || 0) + 1;
  return {
    type: "FeatureCollection",
    features: DB.cemeteries
      .filter((c) => c.lat != null && c.lng != null && per[c.id])
      .map((c) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [c.lng, c.lat] },
        properties: { id: c.id, name: c.name, city: c.city, state: c.state,
                      count: per[c.id] },
      })),
  };
}
function fitToData() {
  const g = cemGeojson();
  if (!g.features.length) return;
  const b = new maplibregl.LngLatBounds();
  g.features.forEach((f) => b.extend(f.geometry.coordinates));
  map.fitBounds(b, { padding: 60, maxZoom: 11, duration: 600 });
}

/* ---------- charts ---------- */
function chartColors(n) {
  return Array.from({ length: n }, (_, i) => PALETTE[i % PALETTE.length]);
}
function renderTagChart(stones) {
  const catId = +$("#chartCat").value;
  const groupBy = $("#chartGroup").value;
  const catTags = DB.tags.filter((t) => t.cat === catId);
  const tagIds = catTags.map((t) => t.id);
  const labelsOf = (s) =>
    groupBy === "state" ? (cemById[s.cem].state || "—") :
    groupBy === "cemetery" ? cemById[s.cem].name :
    groupBy === "decade" ? (s.year ? Math.floor(s.year / 10) * 10 + "s" : "undated") :
    "All";

  const groups = [...new Set(stones.map(labelsOf))].sort(
    (a, b) => a === "undated" ? 1 : b === "undated" ? -1 : a < b ? -1 : 1);
  const counts = {}; // group -> tagId -> n
  for (const g of groups) counts[g] = {};
  for (const s of stones) {
    const g = labelsOf(s);
    for (const t of s.tags) if (tagIds.includes(t))
      counts[g][t] = (counts[g][t] || 0) + 1;
  }
  const usedTags = catTags.filter((t) => groups.some((g) => counts[g][t.id]));
  const single = groupBy === "none";
  const byDecade = groupBy === "decade";
  // decade mode transposes the chart: x-axis = decades, stacked bars = tags —
  // the "style evolution over time" view
  const data = byDecade
    ? { labels: groups,
        datasets: usedTags.map((t, i) => ({
          label: t.name, data: groups.map((g) => counts[g][t.id] || 0),
          backgroundColor: PALETTE[i % PALETTE.length], stack: "s" })) }
    : {
      labels: usedTags.map((t) => t.name),
      datasets: single
        ? [{ label: "gravestones", data: usedTags.map((t) => counts["All"]?.[t.id] || 0),
             backgroundColor: chartColors(usedTags.length) }]
        : groups.map((g, i) => ({
            label: g, data: usedTags.map((t) => counts[g][t.id] || 0),
            backgroundColor: PALETTE[i % PALETTE.length], stack: "s" })),
    };
  tagChart?.destroy();
  tagChart = new Chart($("#tagChart"), {
    type: "bar",
    data,
    options: {
      indexAxis: byDecade ? "x" : "y", maintainAspectRatio: false, responsive: true,
      plugins: { legend: { display: !single, position: "bottom",
                           labels: { boxWidth: 12, font: { size: 11 } } },
                 title: { display: true,
                   text: `${catById[catId].name} — ${stones.length} gravestones` } },
      scales: { x: { stacked: !single, ticks: { precision: 0, font: { size: 11 } } },
                y: { stacked: !single, ticks: { precision: 0, font: { size: 11 } } } },
    },
  });
}
/* Welsh/English detection from the transcription (formulaic phrases) */
function langOf(s) {
  const t = (s.trans || "").replace(/\[DRAFT\]\s*/g, "").toLowerCase();
  if (t.trim().length < 8) return null;
  const w = (t.match(/\b(er cof|bu farw|fu farw|ganwyd|mlwydd|blwydd|flwydd|oed|priod|mab|merch|yr hwn|yr hon|hedd|diwrnod|wythnos|hunodd|gorphwys)\b/g) || []).length;
  const e = (t.match(/\b(in memory|memory of|died|born|aged|wife|son of|daughter|departed|this life|years|months)\b/g) || []).length;
  if (w && e) return w >= e * 2 ? "Welsh" : e >= w * 2 ? "English" : "Mixed";
  return w ? "Welsh" : e ? "English" : null;
}

const AGE_BINS = [[0, 4], [5, 14], [15, 24], [25, 34], [35, 44], [45, 54],
                  [55, 64], [65, 74], [75, 120]];

function renderChart2(stones) {
  const mode = $("#chart2Sel").value;
  if (mode === "decade") return renderDecadeChart(stones);
  decadeChart?.destroy();
  if (mode === "age") {
    const counts = AGE_BINS.map(() => 0);
    let n = 0;
    for (const s of stones) for (const p of (s.persons || [])) {
      if (p.birth && p.death) {
        const age = p.death - p.birth;
        const i = AGE_BINS.findIndex(([a, b]) => age >= a && age <= b);
        if (i >= 0) { counts[i]++; n++; }
      }
    }
    decadeChart = new Chart($("#decadeChart"), {
      type: "bar",
      data: { labels: AGE_BINS.map(([a, b]) => b > 110 ? a + "+" : `${a}–${b}`),
              datasets: [{ label: "people", data: counts,
                           backgroundColor: "#7c6a9c" }] },
      options: { maintainAspectRatio: false, responsive: true,
        plugins: { legend: { display: false },
                   title: { display: true,
                            text: `Age at death — ${n} people` } },
        scales: { y: { ticks: { precision: 0 } } } },
    });
    return;
  }
  // mode === "lang": inscription language by decade, stacked
  const LANGS = ["Welsh", "Mixed", "English"];
  const COLORS = { Welsh: "#4a3f63", Mixed: "#7c6a9c", English: "#b3823c" };
  const per = {};  // decade -> lang -> n
  let n = 0;
  for (const s of stones) {
    const L = langOf(s);
    if (!L || !s.year) continue;
    const d = Math.floor(s.year / 10) * 10;
    (per[d] = per[d] || {})[L] = (per[d][L] || 0) + 1;
    n++;
  }
  const decades = Object.keys(per).map(Number).sort((a, b) => a - b);
  decadeChart = new Chart($("#decadeChart"), {
    type: "bar",
    data: { labels: decades.map((d) => d + "s"),
            datasets: LANGS.map((L) => ({
              label: L, data: decades.map((d) => per[d][L] || 0),
              backgroundColor: COLORS[L], stack: "s" })) },
    options: { maintainAspectRatio: false, responsive: true,
      plugins: { legend: { position: "bottom",
                           labels: { boxWidth: 12, font: { size: 11 } } },
                 title: { display: true,
                          text: `Inscription language — ${n} inscribed` } },
      scales: { x: { stacked: true },
                y: { stacked: true, ticks: { precision: 0 } } } },
  });
}
$("#chart2Sel").addEventListener("change", () => renderChart2(filteredStones()));

function renderDecadeChart(stones) {
  const per = {};
  for (const s of stones) if (s.year)
    per[Math.floor(s.year / 10) * 10] = (per[Math.floor(s.year / 10) * 10] || 0) + 1;
  const decades = Object.keys(per).map(Number).sort((a, b) => a - b);
  decadeChart?.destroy();
  decadeChart = new Chart($("#decadeChart"), {
    type: "bar",
    data: { labels: decades.map((d) => d + "s"),
            datasets: [{ label: "gravestones", data: decades.map((d) => per[d]),
                         backgroundColor: "#b3823c" }] },
    options: { maintainAspectRatio: false, responsive: true,
      plugins: { legend: { display: false },
                 title: { display: true, text: "Gravestones by decade" } },
      scales: { y: { ticks: { precision: 0 } } } },
  });
}
["chartCat", "chartGroup"].forEach((id) =>
  $("#" + id).addEventListener("change", () => renderTagChart(filteredStones())));

/* ---------- gallery & lightbox ---------- */
let similarityRef = null;  // stone id being used as a shape-search reference

function shapeDist(a, b) {
  const sa = MORPHO.stones[a]?.s, sb = MORPHO.stones[b]?.s;
  if (!sa || !sb) return Infinity;
  let d = 0;
  for (let i = 0; i < Math.min(sa.length, sb.length); i++)
    d += (sa[i] - sb[i]) ** 2;
  return Math.sqrt(d);
}
function simNeighbors(id, k) {
  return Object.keys(MORPHO.stones)
    .map(Number).filter((x) => x !== id)
    .map((x) => ({ id: x, d: shapeDist(id, x) }))
    .sort((a, b) => a.d - b.d).slice(0, k);
}

const ptsPath = (pts) =>
  "M" + pts.map((p) => p[0] + "," + p[1]).join("L") + "Z";
const ptsBox = (pts) => {
  const h = Math.max(...pts.map((p) => p[1]));
  return `0 0 100 ${Math.ceil(h)}`;
};

function renderSimBanner() {
  const el = $("#simBanner");
  if (similarityRef == null || !MORPHO?.stones?.[similarityRef]) {
    el.classList.add("hidden");
    return;
  }
  const ref = DB.stones.find((s) => s.id === similarityRef);
  el.classList.remove("hidden");
  el.innerHTML = `
    ${ref?.outline ? `<svg viewBox="0 0 100 ${Math.ceil(ref.outline.h)}"
      preserveAspectRatio="xMidYMax meet"><path d="${ref.outline.d}"/></svg>` : ""}
    <span>ranked by shape similarity to
      <strong>${esc(ref?.title || "stone #" + similarityRef)}</strong>
      (Δ = shape distance)</span>
    <button id="simClear" title="Clear shape search">✕</button>`;
  $("#simClear").addEventListener("click", () => {
    similarityRef = null;
    renderGallery(filteredStones());
  });
}

function renderGallery(stones) {
  renderSimBanner();
  if (galleryView === "morpho") return renderMorpho(stones);
  const sim = similarityRef != null && MORPHO?.stones?.[similarityRef];
  if (sim) {
    stones = stones.filter((s) => MORPHO.stones[s.id])
      .sort((a, b) => shapeDist(similarityRef, a.id) -
                      shapeDist(similarityRef, b.id));
  }
  const withOutline = stones.filter((s) => s.outline).length;
  $("#galleryHead").textContent = sim
    ? `${stones.length} analyzed silhouettes, most similar first`
    : galleryView === "outlines"
    ? `${withOutline} of ${stones.length} gravestones have outlines`
    : `${stones.length} gravestone${stones.length === 1 ? "" : "s"}`;
  const shown = stones.slice(0, galleryShown);
  $("#gallery").innerHTML = shown.map((s) => {
    const c = cemById[s.cem];
    const cap = `<div class="cap">${esc(s.title) || "Unnamed"}${yearsOf(s)}
        <span class="where">${esc(c.name)}, ${esc(c.state || c.country)}</span></div>`;
    if (galleryView === "outlines") {
      return `<div class="stone outlineCard" data-id="${s.id}">
        ${s.outline
          ? `<svg viewBox="0 0 100 ${s.outline.h}" preserveAspectRatio="xMidYMax meet">
               <path d="${s.outline.d}"/></svg>`
          : `<div class="noOutline">no outline yet</div>`}
        ${cap}</div>`;
    }
    const badge = sim && s.id !== similarityRef
      ? `<span class="simBadge">Δ ${shapeDist(similarityRef, s.id).toFixed(2)}</span>`
      : sim ? `<span class="simBadge ref">reference</span>` : "";
    return `<div class="stone" data-id="${s.id}">
      <img loading="lazy" src="${imgUrl(s.photos[0].id, "thumb")}" alt="">
      ${badge}${cap}
    </div>`;
  }).join("") +
  (stones.length > galleryShown
    ? `<button id="moreBtn" class="stone" style="min-height:120px">Show ${Math.min(GALLERY_PAGE, stones.length - galleryShown)} more…</button>` : "");
  $("#gallery").querySelectorAll(".stone[data-id]").forEach((el) =>
    el.addEventListener("click", () => openLightbox(+el.dataset.id)));
  $("#moreBtn")?.addEventListener("click", () => {
    galleryShown += GALLERY_PAGE;
    renderGallery(filteredStones());
  });
}
function openLightbox(id) {
  const s = DB.stones.find((x) => x.id === id);
  const c = cemById[s.cem];
  $("#lbPhotos").classList.toggle("landscape",
    s.photos.every((p) => (p.w || 0) > (p.h || 0)));
  $("#lbPhotos").innerHTML = s.photos.map((p) =>
    `<div class="lbph">
       <img loading="lazy" src="${imgUrl(p.id, "disp")}" data-id="${p.id}"
         data-v="disp" title="Click to flip between original and enhanced" alt="">
       <button class="zoomBtn" data-id="${p.id}" title="Full screen &amp; zoom">⛶</button>
       ${p.depth ? `<button class="reliefBtn" data-id="${p.id}"
         title="Raking light — drag a light across the stone">💡</button>` : ""}
     </div>`).join("");
  $("#lbPhotos").querySelectorAll(".zoomBtn").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      const im = b.parentElement.querySelector("img");
      openZoom(+b.dataset.id, im.dataset.v);
    }));
  $("#lbPhotos").querySelectorAll(".reliefBtn").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      openRelief(+b.dataset.id);
    }));
  $("#lbPhotos").querySelectorAll("img").forEach((im) => {
    im.addEventListener("click", () => {
      const v = im.dataset.v === "disp" ? "enh" : "disp";
      const url = imgUrl(+im.dataset.id, v);
      // preload, and only swap once the new version has actually arrived —
      // never leaves a broken/empty image on screen
      const pre = new Image();
      pre.onload = () => {
        im.src = url;
        im.dataset.v = v;
        im.classList.toggle("enhanced", v === "enh");
      };
      pre.onerror = () => {
        im.title = "Enhanced version not available for this photo";
      };
      pre.src = url;
    });
  });
  const byCat = {};
  for (const t of s.tags) {
    const tag = tagById[t];
    if (tag) (byCat[tag.cat] = byCat[tag.cat] || []).push(tag.name);
  }
  $("#lbInfo").innerHTML = `
    <h3>${esc(s.title) || "Unnamed gravestone"}${yearsOf(s)}</h3>
    <div class="where">${esc(c.name)}, ${esc([c.city, c.state, c.country].filter(Boolean).join(", "))}</div>
    ${(s.persons || []).length > 1 || ((s.persons || [])[0]?.name && s.persons[0].name !== s.title)
      ? `<ul class="lbpersons">${s.persons.map((p) => `<li>${personLine(p)}</li>`).join("")}</ul>` : ""}
    <div class="tags">${DB.categories.map((cat) =>
      (byCat[cat.id] || []).map((n) =>
        `<span><b>${esc(cat.name)}:</b> ${esc(n)}</span>`).join("")).join("")}</div>
    <div class="lbbtns">
      <button id="cmpBtn"></button>
      <button id="linkBtn" title="Copy a direct link to this gravestone">🔗 copy link</button>
    </div>
    ${MORPHO?.stones?.[id] ? `<div class="lbsim"><h5>Similar shapes</h5>
      ${simNeighbors(id, 4)
        .map((r) => DB.stones.find((x) => x.id === r.id))
        .filter(Boolean).map((n) => `
        <button class="simBtn" data-id="${n.id}" title="${esc(n.title || "")}">
          ${n.outline ? `<svg viewBox="${`0 0 100 ${Math.ceil(n.outline.h)}`}"
            preserveAspectRatio="xMidYMax meet"><path d="${n.outline.d}"/></svg>` : ""}
          <span>${esc((n.title || "Unnamed").slice(0, 22))}</span>
        </button>`).join("")}
      <button class="simAll" data-id="${id}">◇ rank the whole collection by
        this shape</button></div>` : ""}
    <div class="lbhint">◐ Click a photo to flip between the original and an
      enhanced view that brings out carving and inscriptions.</div>`;
  $("#lbInfo").querySelectorAll(".simBtn").forEach((b) =>
    b.addEventListener("click", () => openLightbox(+b.dataset.id)));
  $("#lbInfo").querySelectorAll(".simAll").forEach((b) =>
    b.addEventListener("click", () => {
      similarityRef = +b.dataset.id;
      closeLightbox();
      galleryView = "photos";
      document.querySelectorAll("#viewToggle button").forEach((x) =>
        x.classList.toggle("on", x.dataset.v === "photos"));
      renderGallery(filteredStones());
    }));
  $("#lbText").innerHTML =
    (s.trans ? `<h4>Inscription</h4><div class="lbtrans">${esc(s.trans)}</div>` : "") +
    (s.notes ? `<h4>Notes / translation</h4><div class="lbnotes">${esc(s.notes)}</div>` : "");
  const cmpBtn = $("#cmpBtn");
  cmpBtn.textContent = compareId && compareId !== id
    ? "⇄ Compare with selected" : compareId === id
    ? "✓ Selected — open another gravestone" : "⇄ Compare";
  cmpBtn.addEventListener("click", () => {
    if (compareId && compareId !== id) {
      openCompare(compareId, id);
      compareId = null;
    } else {
      compareId = id;
      cmpBtn.textContent = "✓ Selected — open another gravestone";
    }
  });
  $("#linkBtn").addEventListener("click", () => {
    const url = location.href.split("#")[0] + "#stone=" + id;
    navigator.clipboard?.writeText(url);
    $("#linkBtn").textContent = "✓ link copied";
    setTimeout(() => { const b = $("#linkBtn"); if (b) b.textContent = "🔗 copy link"; }, 1500);
  });
  history.replaceState(null, "", "#stone=" + id);
  $("#lightbox").classList.remove("hidden");
}
function closeLightbox() {
  $("#lightbox").classList.add("hidden");
  history.replaceState(null, "", location.pathname + location.search);
}
$("#lbClose").addEventListener("click", closeLightbox);
$("#lightbox").addEventListener("click", (e) => {
  if (e.target.id === "lightbox") closeLightbox();
});

/* ---------- compare view ---------- */
let compareId = null;
function cmpHalf(el, s) {
  const c = cemById[s.cem];
  el.innerHTML = `
    <img src="${imgUrl(s.photos[0].id, "disp")}" data-id="${s.photos[0].id}"
      data-v="disp" title="Click to flip original / enhanced" alt="">
    <div class="cmp-cap"><strong>${esc(s.title) || "Unnamed"}</strong>${yearsOf(s)}
      <span>${esc(c.name)}, ${esc(c.state || c.country)}</span></div>`;
  const im = el.querySelector("img");
  im.addEventListener("click", () => {
    const v = im.dataset.v === "disp" ? "enh" : "disp";
    const pre = new Image();
    pre.onload = () => {
      im.src = pre.src; im.dataset.v = v;
      im.classList.toggle("enhanced", v === "enh");
    };
    pre.src = imgUrl(+im.dataset.id, v);
  });
}
let cmpMorphTimer = null;
function openCompare(idA, idB) {
  const a = DB.stones.find((x) => x.id === idA);
  const b = DB.stones.find((x) => x.id === idB);
  if (!a || !b) return;
  cmpHalf($("#cmpA"), a);
  cmpHalf($("#cmpB"), b);
  // morphing transition between the two silhouettes, when both are analyzed
  cancelAnimationFrame(cmpMorphTimer);
  const pa = MORPHO?.stones?.[idA]?.p, pb = MORPHO?.stones?.[idB]?.p;
  const mid = $("#cmpMorph");
  if (pa && pb) {
    const hMax = Math.ceil(Math.max(...pa.map((p) => p[1]),
                                    ...pb.map((p) => p[1])));
    mid.classList.remove("hidden");
    mid.innerHTML = `<svg viewBox="0 0 100 ${hMax}"
      preserveAspectRatio="xMidYMax meet"><path/></svg>
      <span>shape morph · Δ ${shapeDist(idA, idB).toFixed(2)}</span>`;
    const path = mid.querySelector("path");
    const t0 = performance.now();
    const tick = (now) => {
      // ping-pong 0→1→0 every 3 seconds
      const t = 0.5 - 0.5 * Math.cos(((now - t0) / 3000) * Math.PI * 2);
      path.setAttribute("d", ptsPath(pa.map((p, i) =>
        [p[0] + (pb[i][0] - p[0]) * t, p[1] + (pb[i][1] - p[1]) * t])));
      if (!$("#compare").classList.contains("hidden"))
        cmpMorphTimer = requestAnimationFrame(tick);
    };
    cmpMorphTimer = requestAnimationFrame(tick);
  } else {
    mid.classList.add("hidden");
  }
  $("#lightbox").classList.add("hidden");
  $("#compare").classList.remove("hidden");
}
$("#cmpClose").addEventListener("click", () =>
  $("#compare").classList.add("hidden"));
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("#relief").classList.contains("hidden")) closeRelief();
  else if (!$("#zoomview").classList.contains("hidden")) closeZoom();
  else if (!$("#compare").classList.contains("hidden"))
    $("#compare").classList.add("hidden");
  else if (!$("#about").classList.contains("hidden"))
    $("#about").classList.add("hidden");
  else if (!$("#lightbox").classList.contains("hidden")) closeLightbox();
});

/* ---------- virtual raking light (WebGL) ---------- */
const RL = { gl: null, prog: null, light: [0.6, 0.4], strength: 5,
             albedo: 1, texel: [0, 0], ready: false };

function rlShader(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
    throw new Error(gl.getShaderInfoLog(s));
  return s;
}
function rlTexture(gl, unit, img) {
  const t = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0 + unit);
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  return t;
}
function rlDraw() {
  if (!RL.ready) return;
  const gl = RL.gl;
  gl.uniform2fv(RL.uLight, RL.light);
  gl.uniform1f(RL.uStrength, RL.strength);
  gl.uniform1f(RL.uAlbedo, RL.albedo);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
}
function openRelief(pid) {
  const color = new Image(), depth = new Image();
  color.crossOrigin = depth.crossOrigin = "anonymous";
  let loaded = 0;
  const go = () => {
    if (++loaded < 2) return;
    const cv = $("#rlCanvas");
    // fit the image to the viewport
    const scale = Math.min((innerWidth - 40) / color.width,
                           (innerHeight - 90) / color.height);
    cv.width = Math.round(color.width * scale * devicePixelRatio);
    cv.height = Math.round(color.height * scale * devicePixelRatio);
    cv.style.width = Math.round(color.width * scale) + "px";
    cv.style.height = Math.round(color.height * scale) + "px";
    const gl = cv.getContext("webgl");
    if (!gl) { alert("WebGL is not available in this browser."); return; }
    RL.gl = gl;
    const vs = rlShader(gl, gl.VERTEX_SHADER, `
      attribute vec2 aPos; varying vec2 vUv;
      void main(){ vUv = aPos*0.5+0.5; gl_Position = vec4(aPos,0.,1.); }`);
    const fs = rlShader(gl, gl.FRAGMENT_SHADER, `
      precision mediump float;
      uniform sampler2D uColor, uDepth;
      uniform vec2 uLight, uTexel;
      uniform float uStrength, uAlbedo;
      varying vec2 vUv;
      void main(){
        float hL = texture2D(uDepth, vUv - vec2(uTexel.x, 0.)).r;
        float hR = texture2D(uDepth, vUv + vec2(uTexel.x, 0.)).r;
        float hD = texture2D(uDepth, vUv - vec2(0., uTexel.y)).r;
        float hU = texture2D(uDepth, vUv + vec2(0., uTexel.y)).r;
        vec3 n = normalize(vec3((hL-hR)*uStrength, (hD-hU)*uStrength, 1.));
        vec3 L = normalize(vec3(uLight, 0.55));
        float diff = max(dot(n, L), 0.);
        float spec = pow(max(dot(reflect(-L, n), vec3(0.,0.,1.)), 0.), 24.) * .12;
        vec3 base = mix(vec3(.80,.79,.77), texture2D(uColor, vUv).rgb, uAlbedo);
        gl_FragColor = vec4(base * (.22 + .9*diff) + spec, 1.);
      }`);
    const prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs);
    gl.linkProgram(prog); gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER,
      new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
    rlTexture(gl, 0, color);
    rlTexture(gl, 1, depth);
    gl.uniform1i(gl.getUniformLocation(prog, "uColor"), 0);
    gl.uniform1i(gl.getUniformLocation(prog, "uDepth"), 1);
    gl.uniform2f(gl.getUniformLocation(prog, "uTexel"),
                 1.5 / depth.width, 1.5 / depth.height);
    RL.uLight = gl.getUniformLocation(prog, "uLight");
    RL.uStrength = gl.getUniformLocation(prog, "uStrength");
    RL.uAlbedo = gl.getUniformLocation(prog, "uAlbedo");
    gl.viewport(0, 0, cv.width, cv.height);
    RL.ready = true;
    $("#relief").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    rlDraw();
  };
  color.onload = go; depth.onload = go;
  depth.onerror = () => alert(
    "Couldn't load the relief map. If the file exists on R2, the bucket " +
    "needs a CORS policy (Settings → CORS Policy → allow GET from this " +
    "site) — WebGL requires CORS-approved images.");
  color.onerror = depth.onerror;
  // "?cors" gives these requests their own cache key: copies cached before
  // the bucket's CORS policy existed (browser or edge) lack the CORS headers
  // WebGL needs, and would otherwise be served forever
  color.src = imgUrl(pid, "disp") + "?cors";
  depth.src = imgUrl(pid, "depth") + "?cors";
}
function closeRelief() {
  $("#relief").classList.add("hidden");
  RL.ready = false;
  document.body.style.overflow = "";
}
$("#rlClose").addEventListener("click", closeRelief);
$("#relief").addEventListener("pointermove", (e) => {
  RL.light = [((e.clientX / innerWidth) * 2 - 1) * 1.4,
              (1 - (e.clientY / innerHeight) * 2) * 1.4];
  rlDraw();
});
$("#rlStrength").addEventListener("input", (e) => {
  RL.strength = +e.target.value;
  rlDraw();
});
$("#rlAlbedo").addEventListener("click", () => {
  RL.albedo = RL.albedo ? 0 : 1;
  $("#rlAlbedo").classList.toggle("on", !!RL.albedo);
  $("#rlAlbedo").textContent = RL.albedo ? "photo" : "stone";
  rlDraw();
});

/* ---------- about ---------- */
$("#aboutBtn").addEventListener("click", () =>
  $("#about").classList.remove("hidden"));
$("#aboutClose").addEventListener("click", () =>
  $("#about").classList.add("hidden"));
$("#about").addEventListener("click", (e) => {
  if (e.target.id === "about") $("#about").classList.add("hidden");
});

/* ---------- fullscreen zoom viewer ---------- */
const ZV = { pid: null, v: "disp", s: 1, base: 1, tx: 0, ty: 0, iw: 0, ih: 0 };
const zvImg = $("#zvImg");

function zvApply() {
  zvImg.style.transform =
    `translate(${ZV.tx}px, ${ZV.ty}px) scale(${ZV.s * ZV.base})`;
  $("#zvFlip").classList.toggle("on", ZV.v === "enh");
}
function zvFit() {
  ZV.base = Math.min(innerWidth / ZV.iw, innerHeight / ZV.ih);
  ZV.s = 1;
  ZV.tx = (innerWidth - ZV.iw * ZV.base) / 2;
  ZV.ty = (innerHeight - ZV.ih * ZV.base) / 2;
  zvApply();
}
function zvZoomAt(cx, cy, f) {
  const s0 = ZV.s;
  ZV.s = Math.min(14, Math.max(1, ZV.s * f));
  const rf = ZV.s / s0;
  ZV.tx = cx - (cx - ZV.tx) * rf;
  ZV.ty = cy - (cy - ZV.ty) * rf;
  if (ZV.s === 1) return zvFit();
  zvApply();
}
function openZoom(pid, v) {
  ZV.pid = pid; ZV.v = v || "disp";
  const pre = new Image();
  pre.onload = () => {
    ZV.iw = pre.naturalWidth; ZV.ih = pre.naturalHeight;
    zvImg.src = pre.src;
    $("#zoomview").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    zvFit();
  };
  pre.src = imgUrl(pid, ZV.v);
}
function closeZoom() {
  $("#zoomview").classList.add("hidden");
  document.body.style.overflow = "";
}
function zvFlip() {
  const v = ZV.v === "disp" ? "enh" : "disp";
  const pre = new Image();
  pre.onload = () => { ZV.v = v; zvImg.src = pre.src; zvApply(); };
  pre.src = imgUrl(ZV.pid, v);   // same dimensions, transform is preserved
}
$("#zvClose").addEventListener("click", closeZoom);
$("#zvReset").addEventListener("click", zvFit);
$("#zvFlip").addEventListener("click", zvFlip);
$("#zvIn").addEventListener("click", () =>
  zvZoomAt(innerWidth / 2, innerHeight / 2, 1.5));
$("#zvOut").addEventListener("click", () =>
  zvZoomAt(innerWidth / 2, innerHeight / 2, 1 / 1.5));
$("#zoomview").addEventListener("wheel", (e) => {
  e.preventDefault();
  zvZoomAt(e.clientX, e.clientY, Math.exp(-e.deltaY * 0.002));
}, { passive: false });

// drag to pan / click to flip / pinch to zoom (pointer events)
const zvPtrs = new Map();
let zvMoved = 0, zvPinchD = 0;
$("#zoomview").addEventListener("pointerdown", (e) => {
  if (e.target.closest("#zvBar")) return;
  zvPtrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (zvPtrs.size === 1) zvMoved = 0;
  if (zvPtrs.size === 2) {
    const [a, b] = [...zvPtrs.values()];
    zvPinchD = Math.hypot(a.x - b.x, a.y - b.y);
  }
  $("#zoomview").setPointerCapture(e.pointerId);
});
$("#zoomview").addEventListener("pointermove", (e) => {
  const p = zvPtrs.get(e.pointerId);
  if (!p) return;
  const dx = e.clientX - p.x, dy = e.clientY - p.y;
  p.x = e.clientX; p.y = e.clientY;
  if (zvPtrs.size === 1) {
    zvMoved += Math.abs(dx) + Math.abs(dy);
    ZV.tx += dx; ZV.ty += dy;
    zvApply();
  } else if (zvPtrs.size === 2) {
    const [a, b] = [...zvPtrs.values()];
    const d = Math.hypot(a.x - b.x, a.y - b.y);
    if (zvPinchD > 0)
      zvZoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, d / zvPinchD);
    zvPinchD = d;
    zvMoved = 99;
  }
});
["pointerup", "pointercancel"].forEach((ev) =>
  $("#zoomview").addEventListener(ev, (e) => {
    const was = zvPtrs.size;
    zvPtrs.delete(e.pointerId);
    if (ev === "pointerup" && was === 1 && zvMoved < 6 &&
        !e.target.closest("#zvBar"))
      zvFlip();   // a true click (no drag) flips original/enhanced
  }));

document.querySelectorAll("#viewToggle button").forEach((b) =>
  b.addEventListener("click", () => {
    galleryView = b.dataset.v;
    document.querySelectorAll("#viewToggle button").forEach((x) =>
      x.classList.toggle("on", x === b));
    renderGallery(filteredStones());
  }));

/* ---------- shape space (morphometrics) ---------- */
let morphTimer = null;

function renderMorpho(stones) {
  const pts = stones.filter((s) => MORPHO.stones[s.id]);
  $("#galleryHead").textContent =
    `Shape space — ${pts.length} of ${MORPHO.n} analyzed silhouettes in view`;
  const decades = Object.keys(MORPHO.decadeMeans);
  $("#gallery").innerHTML = `
    <div id="morphoWrap">
      <div id="pcBox"><canvas id="pcChart"></canvas></div>
      <div id="morphoSide">
        <h3>The average stone, by decade</h3>
        <div id="decadeRow">${decades.map((d) => `
          <figure><svg viewBox="${ptsBox(MORPHO.decadeMeans[d])}"
            preserveAspectRatio="xMidYMax meet">
            <path d="${ptsPath(MORPHO.decadeMeans[d])}"/></svg>
            <figcaption>${d}s</figcaption></figure>`).join("")}
        </div>
        ${decades.length > 1 ? `
        <div id="morphPlay">
          <svg id="morphSvg" viewBox="0 0 100 220"
            preserveAspectRatio="xMidYMax meet"><path/></svg>
          <button id="morphBtn">▶ morph through the decades</button>
          <span id="morphLabel"></span>
        </div>` : ""}
        <p class="hint">Each dot is a gravestone placed by the geometry of its
          silhouette (principal components of ${MORPHO.n} resampled outlines).
          Nearby dots are similar shapes — clusters often mean one carver or
          workshop. Click a dot to open the stone.</p>
      </div>
    </div>`;
  // scatter, colored by decade
  const byDec = {};
  pts.forEach((s) => {
    const d = s.year ? Math.floor(s.year / 10) * 10 + "s" : "undated";
    const sc = MORPHO.stones[s.id].s;
    (byDec[d] = byDec[d] || []).push(
      { x: sc[0], y: sc[1] ?? 0, sid: s.id,
        title: (s.title || "Unnamed") + yearsOf(s) });
  });
  const keys = Object.keys(byDec).sort();
  pcChart?.destroy();
  pcChart = new Chart($("#pcChart"), {
    type: "scatter",
    data: { datasets: keys.map((k, i) => ({
      label: k, data: byDec[k], pointRadius: 7, pointHoverRadius: 9,
      backgroundColor: PALETTE[i % PALETTE.length] + "cc" })) },
    options: {
      maintainAspectRatio: false, responsive: true,
      onClick: (e, els) => {
        if (els.length) {
          const p = pcChart.data.datasets[els[0].datasetIndex]
            .data[els[0].index];
          openLightbox(p.sid);
        }
      },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12,
                  font: { size: 11 } } },
        tooltip: { callbacks: { label: (c) => c.raw.title } },
      },
      scales: {
        x: { title: { display: true,
             text: `PC1 — ${MORPHO.axes[0]?.explained ?? "?"}% of shape variation` } },
        y: { title: { display: true,
             text: `PC2 — ${MORPHO.axes[1]?.explained ?? "?"}%` } },
      },
    },
  });
  // morph animation between consecutive decade means
  clearInterval(morphTimer);
  const btn = $("#morphBtn");
  if (btn) btn.addEventListener("click", () => {
    const seq = decades.map((d) => MORPHO.decadeMeans[d]);
    let i = 0, t = 0;
    clearInterval(morphTimer);
    morphTimer = setInterval(() => {
      t += 0.04;
      if (t >= 1) { t = 0; i = (i + 1) % (seq.length - 1); }
      const a = seq[i], b = seq[i + 1];
      const mix = a.map((p, k) =>
        [p[0] + (b[k][0] - p[0]) * t, p[1] + (b[k][1] - p[1]) * t]);
      $("#morphSvg path").setAttribute("d", ptsPath(mix));
      $("#morphLabel").textContent =
        `${decades[i]}s → ${decades[i + 1]}s`;
    }, 40);
  });
}

/* ---------- update cycle ---------- */
function update() {
  galleryShown = GALLERY_PAGE;
  buildFilterOptions();
  buildTagFilters();
  const stones = filteredStones();
  renderGallery(stones);
  renderTagChart(stones);
  renderChart2(stones);
  if (map?.getSource("cems")) {
    map.getSource("cems").setData(cemGeojson());
    fitToData();
  }
  $("#counts").textContent =
    `${DB.stones.length} gravestones · ${DB.cemeteries.filter((c) => c.stones).length} cemeteries`;
}

/* ---------- init ---------- */
(async function init() {
  try {
    const rm = await fetch("data/morpho.json");
    if (rm.ok) MORPHO = await rm.json();
  } catch (e) { /* shape space hidden if absent */ }
  if (MORPHO) $("#morphoTab").classList.remove("hidden");
  Chart.defaults.font.family = '"Source Sans 3", sans-serif';
  Chart.defaults.color = "#5a6470";
  Chart.defaults.plugins.title.color = "#4a3f63";
  Chart.defaults.plugins.title.font = { family: '"Jost", sans-serif',
    size: 14, weight: 600 };
  const r = await fetch("data/library.json");
  DB = await r.json();
  IMG = DB.imageBase || "";
  DB.cemeteries.forEach((c) => cemById[c.id] = c);
  DB.tags.forEach((t) => tagById[t.id] = t);
  DB.categories.forEach((c) => catById[c.id] = c);
  $("#chartCat").innerHTML = DB.categories.map((c) =>
    `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  initMap();
  update();
  // permalink: #stone=7 opens that gravestone directly
  const m = location.hash.match(/#stone=(\d+)/);
  if (m && DB.stones.some((s) => s.id === +m[1])) openLightbox(+m[1]);
})();
