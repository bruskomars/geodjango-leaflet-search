// maps_frontend/static/javascript/names.js
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };
  const fmt = (v) =>
    v == null
      ? "–"
      : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });

  const map = L.map("map").setView([14.5995, 121.0], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "no-referrer-when-downgrade",
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  const pointLayer = L.layerGroup().addTo(map);
  let requestId = 0;

  function markPressed(button) {
    document
      .querySelectorAll("[aria-pressed='true']")
      .forEach((b) => b.setAttribute("aria-pressed", "false"));
    if (button) button.setAttribute("aria-pressed", "true");
  }

  function renderTotals(d) {
    const items = [
      [d.total, "landmarks"],
      [d.distinct_names, "different names"],
      [d.unnamed, "without a name"],
    ];
    $("totals").innerHTML = items
      .map(([v, l]) => `<div><b>${fmt(v)}</b><span>${l}</span></div>`)
      .join("");
  }

  function rows(items, max, attr, labelOf) {
    return items
      .map((it) => {
        const width = max ? Math.max(3, Math.round((100 * it.count) / max)) : 0;
        return `<button class="row" aria-pressed="false" ${attr(it)}>
          <i class="bar" style="width:${width}%"></i><span>${esc(labelOf(it))}</span><span>${fmt(it.count)}</span></button>`;
      })
      .join("");
  }

  function renderSummary(d) {
    renderTotals(d);
    const maxCat = Math.max(1, ...d.categories.map((c) => c.count));
    $("categories").innerHTML = rows(
      d.categories,
      maxCat,
      (c) =>
        `data-kind="category" data-value="${esc(c.key)}" data-label="${esc(c.label)}"`,
      (c) => c.label,
    );
    const maxChain = Math.max(1, ...d.chains.map((c) => c.count));
    $("chains").innerHTML =
      rows(
        d.chains,
        maxChain,
        (c) =>
          `data-kind="chain" data-value="${esc(c.name)}" data-label="${esc(c.name)}"`,
        (c) => c.name,
      ) || "<p class='help'>No repeated names in the loaded data.</p>";
    $("words").innerHTML = d.words
      .map(
        (w) =>
          `<button class="tag" aria-pressed="false" data-kind="word" data-value="${esc(w.word)}" data-label="“${esc(w.word)}”">${esc(w.word)}<small>${fmt(w.count)}</small></button>`,
      )
      .join("");
    $("note").textContent = d.note;
  }

  async function plot(button) {
    const id = ++requestId;
    const { kind, value, label } = button.dataset;
    markPressed(button);
    $("status").textContent = "Loading…";
    try {
      const res = await fetch(
        `/api/analysis/names/points/?${new URLSearchParams({ [kind]: value })}`,
      );
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      if (id !== requestId) return; // a newer click replaced this one
      pointLayer.clearLayers();
      const markers = d.data.features.map((f) => {
        const [lng, lat] = f.geometry.coordinates;
        return L.circleMarker([lat, lng], {
          radius: 5,
          color: "#ffffff",
          weight: 1,
          fillColor: "#7c3aed",
          fillOpacity: 0.9,
        })
          .bindTooltip(esc(f.properties.name))
          .addTo(pointLayer);
      });
      $("selection").textContent = `${label}: ${fmt(d.count)} landmarks`;
      $("status").textContent =
        d.count > d.shown
          ? `Showing the first ${fmt(d.shown)} on the map.`
          : "";
      if (markers.length)
        map.fitBounds(L.featureGroup(markers).getBounds(), {
          padding: [30, 30],
          maxZoom: 16,
        });
    } catch (err) {
      if (id === requestId)
        $("status").textContent =
          "Something went wrong loading those landmarks.";
    }
  }

  document.querySelector("aside").addEventListener("click", (e) => {
    const button = e.target.closest("[data-kind]");
    if (button) plot(button);
  });

  async function init() {
    $("status").textContent =
      "Loading… the server may take up to a minute to wake up.";
    try {
      const res = await fetch("/api/analysis/names/");
      if (!res.ok) throw new Error("HTTP " + res.status);
      renderSummary(await res.json());
      $("status").textContent =
        "Pick a category, a repeated name or a word to plot it on the map.";
    } catch (err) {
      $("status").textContent =
        "Something went wrong loading the data. Please try again.";
    }
  }

  init();
})();
