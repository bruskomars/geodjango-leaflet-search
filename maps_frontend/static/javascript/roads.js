// maps_frontend/static/javascript/roads.js
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

  const roadLayer = L.layerGroup().addTo(map);
  let requestId = 0;

  function markPressed(button) {
    document
      .querySelectorAll("[aria-pressed='true']")
      .forEach((b) => b.setAttribute("aria-pressed", "false"));
    if (button) button.setAttribute("aria-pressed", "true");
  }

  // items: [{ key, label, value, text }]; value is the number the bar is scaled to
  function rows(items, kind) {
    const max = Math.max(1, ...items.map((i) => i.value));
    return items
      .map((i) => {
        const width = Math.max(3, Math.round((100 * i.value) / max));
        return `<button class="row" aria-pressed="false" data-kind="${kind}" data-value="${esc(i.key)}" data-label="${esc(i.label)}">
          <i class="bar" style="width:${width}%"></i><span>${esc(i.label)}</span><span>${esc(i.text)}</span></button>`;
      })
      .join("");
  }

  function plainList(items) {
    return items
      .map(
        (r) =>
          `<div class="plain"><span>${esc(r.name)}, ${esc(r.city)}</span><span>${esc(r.text)}</span></div>`,
      )
      .join("");
  }

  function renderSummary(d) {
    const t = d.totals;
    $("totals").innerHTML = [
      [t.km, "km of road"],
      [t.segments, "road segments"],
      [`${fmt(t.unnamed_pct)}%`, "have no name"],
    ]
      .map(
        ([v, l]) =>
          `<div><b>${typeof v === "number" ? fmt(v) : v}</b><span>${l}</span></div>`,
      )
      .join("");

    $("types").innerHTML = rows(
      d.types.map((x) => ({
        key: x.type,
        label: x.type,
        value: x.km,
        text: `${fmt(x.km)} km`,
      })),
      "type",
    );
    $("longest").innerHTML = rows(
      d.longest.map((x) => ({
        key: x.name,
        label: x.name,
        value: x.km,
        text: `${fmt(x.km)} km`,
      })),
      "street",
    );
    $("fragmented").innerHTML = rows(
      d.fragmented.map((x) => ({
        key: x.name,
        label: x.name,
        value: x.segments,
        text: `${fmt(x.segments)} segments`,
      })),
      "street",
    );
    $("by-km").innerHTML = plainList(
      d.barangays_by_km.map((r) => ({ ...r, text: `${fmt(r.road_km)} km` })),
    );
    $("by-density").innerHTML = plainList(
      d.barangays_by_density.map((r) => ({
        ...r,
        text: `${fmt(r.road_density)} km/km²`,
      })),
    );
    $("note").textContent = d.note;
  }

  async function plot(button) {
    const id = ++requestId;
    const { kind, value, label } = button.dataset;
    markPressed(button);
    $("status").textContent = "Loading…";
    try {
      const res = await fetch(
        `/api/analysis/roads/geometry/?${new URLSearchParams({ [kind]: value })}`,
      );
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      if (id !== requestId) return; // a newer click replaced this one
      roadLayer.clearLayers();
      // White casing under an amber line, like the search map, so roads stay readable
      L.geoJSON(d.data, {
        interactive: false,
        style: {
          color: "#ffffff",
          weight: 8,
          opacity: 0.95,
          lineCap: "round",
          lineJoin: "round",
        },
      }).addTo(roadLayer);
      const line = L.geoJSON(d.data, {
        style: {
          color: "#f59e0b",
          weight: 4,
          opacity: 1,
          lineCap: "round",
          lineJoin: "round",
        },
        onEachFeature: (f, layer) =>
          layer.bindTooltip(esc(f.properties.name), { sticky: true }),
      }).addTo(roadLayer);
      $("selection").textContent =
        `${label}: ${fmt(d.km)} km in ${fmt(d.segments)} segments`;
      $("status").textContent =
        d.segments > d.shown
          ? `Showing the first ${fmt(d.shown)} segments on the map.`
          : "";
      if (line.getBounds().isValid())
        map.fitBounds(line.getBounds(), { padding: [30, 30], maxZoom: 16 });
    } catch (err) {
      if (id === requestId)
        $("status").textContent = "Something went wrong loading those roads.";
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
      const res = await fetch("/api/analysis/roads/");
      if (!res.ok) throw new Error("HTTP " + res.status);
      renderSummary(await res.json());
      $("status").textContent =
        "Pick a street type or a street to plot it on the map.";
    } catch (err) {
      $("status").textContent =
        "Something went wrong loading the data. Please try again.";
    }
  }

  init();
})();
