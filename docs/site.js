/* Slate Gravestones — public site */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let DB, IMG = "", map, tagChart, decadeChart;
const cemById = {}, tagById = {}, catById = {};
const F = { country: "", state: "", cemetery: "", yearMin: null, yearMax: null,
            tags: new Set() };
const GALLERY_PAGE = 120;
let galleryShown = GALLERY_PAGE;

const PALETTE = ["#4a3f63", "#b3823c", "#7c6a9c", "#5a6470", "#9b3b7a",
  "#4a7c59", "#b3552f", "#6d8196", "#8c7a4e", "#54838c", "#8c4e5b", "#2b2433"];

const imgUrl = (photoId, kind) => `${IMG}/img/${photoId}/${kind}.jpg`;
// " · 1745–1794", " · d. 1794", " · b. 1745", or ""
const yearsOf = (s) =>
  s.birth && s.year ? ` · ${s.birth}–${s.year}` :
  s.year ? ` · d. ${s.year}` :
  s.birth ? ` · b. ${s.birth}` : "";

/* ---------- filtering ---------- */
function filteredStones() {
  return DB.stones.filter((s) => {
    const c = cemById[s.cem];
    if (F.country && c.country !== F.country) return false;
    if (F.state && c.state !== F.state) return false;
    if (F.cemetery && String(s.cem) !== F.cemetery) return false;
    if (F.yearMin != null && (s.year == null || s.year < F.yearMin)) return false;
    if (F.yearMax != null && (s.year == null || s.year > F.yearMax)) return false;
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

function buildTagFilters() {
  // counts within the current filtered set (ignoring each tag's own filter is
  // fancier; keeping it simple and fast)
  const counts = {};
  for (const s of filteredStones()) for (const t of s.tags) counts[t] = (counts[t] || 0) + 1;
  $("#tagFilters").innerHTML = DB.categories.map((cat) => {
    const tags = DB.tags.filter((t) => t.cat === cat.id &&
      ((counts[t.id] || 0) > 0 || F.tags.has(t.id)));
    if (!tags.length) return "";
    return `<div class="tgroup"><h3>${esc(cat.name)}</h3><div class="chips">` +
      tags.map((t) =>
        `<span class="chip ${F.tags.has(t.id) ? "on" : ""}" data-id="${t.id}">
           ${esc(t.name)} <span class="n">${counts[t.id] || 0}</span></span>`).join("") +
      `</div></div>`;
  }).join("");
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
$("#clearBtn").addEventListener("click", () => {
  F.country = F.state = F.cemetery = "";
  F.yearMin = F.yearMax = null;
  F.tags.clear();
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
      new maplibregl.Popup({ offset: 10 })
        .setLngLat(e.features[0].geometry.coordinates)
        .setHTML(`<strong>${esc(p.name)}</strong><br>
          ${esc([p.city, p.state].filter(Boolean).join(", "))}<br>
          ${p.count} gravestone(s) shown ·
          <a href="#" onclick="setCem(${p.id});return false">filter to this cemetery</a>`)
        .addTo(map);
    });
    map.on("mouseenter", "cem-circles", () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", "cem-circles", () => map.getCanvas().style.cursor = "");
    fitToData();
  });
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
  const labelsOf = (s) => groupBy === "state" ? (cemById[s.cem].state || "—")
    : groupBy === "cemetery" ? cemById[s.cem].name : "All";

  const groups = [...new Set(stones.map(labelsOf))].sort();
  const counts = {}; // group -> tagId -> n
  for (const g of groups) counts[g] = {};
  for (const s of stones) {
    const g = labelsOf(s);
    for (const t of s.tags) if (tagIds.includes(t))
      counts[g][t] = (counts[g][t] || 0) + 1;
  }
  const usedTags = catTags.filter((t) => groups.some((g) => counts[g][t.id]));
  const single = groupBy === "none";
  const data = {
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
      indexAxis: "y", maintainAspectRatio: false, responsive: true,
      plugins: { legend: { display: !single, position: "bottom",
                           labels: { boxWidth: 12, font: { size: 11 } } },
                 title: { display: true,
                   text: `${catById[catId].name} — ${stones.length} gravestones` } },
      scales: { x: { stacked: !single, ticks: { precision: 0 } },
                y: { stacked: !single, ticks: { font: { size: 11 } } } },
    },
  });
}
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
function renderGallery(stones) {
  $("#galleryHead").textContent =
    `${stones.length} gravestone${stones.length === 1 ? "" : "s"}`;
  const shown = stones.slice(0, galleryShown);
  $("#gallery").innerHTML = shown.map((s) => {
    const c = cemById[s.cem];
    return `<div class="stone" data-id="${s.id}">
      <img loading="lazy" src="${imgUrl(s.photos[0].id, "thumb")}" alt="">
      <div class="cap">${esc(s.title) || "Unnamed"}${yearsOf(s)}
        <span class="where">${esc(c.name)}, ${esc(c.state || c.country)}</span></div>
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
  $("#lbPhotos").innerHTML = s.photos.map((p) =>
    `<img loading="lazy" src="${imgUrl(p.id, "disp")}" alt="">`).join("");
  const byCat = {};
  for (const t of s.tags) {
    const tag = tagById[t];
    if (tag) (byCat[tag.cat] = byCat[tag.cat] || []).push(tag.name);
  }
  $("#lbMeta").innerHTML = `
    <h3>${esc(s.title) || "Unnamed gravestone"}${yearsOf(s)}</h3>
    <div class="where">${esc(s.dateText || "")}${s.dateText ? " — " : ""}
      ${esc(c.name)}, ${esc([c.city, c.state, c.country].filter(Boolean).join(", "))}</div>
    <div class="tags">${DB.categories.map((cat) =>
      (byCat[cat.id] || []).map((n) =>
        `<span><b>${esc(cat.name)}:</b> ${esc(n)}</span>`).join("")).join("")}</div>`;
  $("#lightbox").classList.remove("hidden");
}
$("#lbClose").addEventListener("click", () => $("#lightbox").classList.add("hidden"));
$("#lightbox").addEventListener("click", (e) => {
  if (e.target.id === "lightbox") $("#lightbox").classList.add("hidden");
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $("#lightbox").classList.add("hidden");
});

/* ---------- update cycle ---------- */
function update() {
  galleryShown = GALLERY_PAGE;
  buildFilterOptions();
  buildTagFilters();
  const stones = filteredStones();
  renderGallery(stones);
  renderTagChart(stones);
  renderDecadeChart(stones);
  if (map?.getSource("cems")) {
    map.getSource("cems").setData(cemGeojson());
    fitToData();
  }
  $("#counts").textContent =
    `${DB.stones.length} gravestones · ${DB.cemeteries.filter((c) => c.stones).length} cemeteries`;
}

/* ---------- init ---------- */
(async function init() {
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
})();
