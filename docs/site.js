/* Slate Gravestones — public site */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let DB, IMG = "", map, tagChart, decadeChart;
const cemById = {}, tagById = {}, catById = {};
const F = { country: "", state: "", cemetery: "", yearMin: null, yearMax: null,
            tags: new Set(), q: "" };
const GALLERY_PAGE = 120;
let galleryShown = GALLERY_PAGE;

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
    `<div class="lbph">
       <img loading="lazy" src="${imgUrl(p.id, "disp")}" data-id="${p.id}"
         data-v="disp" title="Click to flip between original and enhanced" alt="">
       <button class="zoomBtn" data-id="${p.id}" title="Full screen &amp; zoom">⛶</button>
     </div>`).join("");
  $("#lbPhotos").querySelectorAll(".zoomBtn").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      const im = b.parentElement.querySelector("img");
      openZoom(+b.dataset.id, im.dataset.v);
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
    <div class="lbhint">◐ Click a photo to flip between the original and an
      enhanced view that brings out carving and inscriptions.</div>`;
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
function openCompare(idA, idB) {
  const a = DB.stones.find((x) => x.id === idA);
  const b = DB.stones.find((x) => x.id === idB);
  if (!a || !b) return;
  cmpHalf($("#cmpA"), a);
  cmpHalf($("#cmpB"), b);
  $("#lightbox").classList.add("hidden");
  $("#compare").classList.remove("hidden");
}
$("#cmpClose").addEventListener("click", () =>
  $("#compare").classList.add("hidden"));
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("#zoomview").classList.contains("hidden")) closeZoom();
  else if (!$("#compare").classList.contains("hidden"))
    $("#compare").classList.add("hidden");
  else if (!$("#lightbox").classList.contains("hidden")) closeLightbox();
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
  // permalink: #stone=7 opens that gravestone directly
  const m = location.hash.match(/#stone=(\d+)/);
  if (m && DB.stones.some((s) => s.id === +m[1])) openLightbox(+m[1]);
})();
