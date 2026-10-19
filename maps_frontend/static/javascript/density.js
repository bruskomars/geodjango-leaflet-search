// maps_frontend/static/javascript/density.js
(function () {
  // Colour ramps match the pin colours: violet for landmarks, teal for house numbers
  const PALETTES = {
    landmarks: ["#f1ebfb", "#d3bff3", "#a98beb", "#7c52d6", "#4c2a9a"],
    addresses: ["#eaf6f3", "#b7dfd6", "#6fbfb1", "#2f9c8d", "#0f6b61"],
  };
  const state = { layer: "landmarks", size: 500 };
  const $ = (id) => document.getElementById(id);

  const map = L.map("map").setView([14.5995, 121.0], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "no-referrer-when-downgrade",
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  let hexLayer = null;
  let hoverOutline = null;
  let requestId = 0;
  let hexLayers = []; // [{ layer, count, density }] for the hotspot list

  const fmt = (v) => {
    if (v == null) return "–";
    const digits = Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
    return Number(v).toLocaleString(undefined, {
      maximumFractionDigits: digits,
    });
  };

  function classOf(value, breaks) {
    for (let i = 0; i < breaks.length; i++) if (value < breaks[i]) return i;
    return 4;
  }

  function clearOutline() {
    if (hoverOutline) {
      map.removeLayer(hoverOutline);
      hoverOutline = null;
    }
  }

  function renderMap(resp, fit) {
    clearOutline();
    if (hexLayer) map.removeLayer(hexLayer);
    hexLayers = [];
    const palette = PALETTES[resp.layer];
    const unit = resp.label.toLowerCase();
    hexLayer = L.geoJSON(resp.data, {
      style: (f) => ({
        fillColor: palette[classOf(f.properties.count, resp.breaks)],
        fillOpacity: 0.8,
        color: "#ffffff",
        weight: 0.5,
      }),
      onEachFeature: (f, layer) => {
        const p = f.properties;
        hexLayers.push({ layer, count: p.count, density: p.density });
        layer.bindTooltip(
          `${fmt(p.count)} ${unit} (${fmt(p.density)} per km²)`,
          { sticky: true },
        );
        layer.on("mouseover", () => {
          clearOutline();
          hoverOutline = L.geoJSON(f, {
            interactive: false,
            style: { fill: false, color: "#1b2733", weight: 2 },
          }).addTo(map);
        });
        layer.on("mouseout", () => {
          clearOutline();
          layer.closeTooltip();
        });
      },
    }).addTo(map);
    if (fit && hexLayer.getBounds().isValid())
      map.fitBounds(hexLayer.getBounds(), { padding: [20, 20] });
  }

  function renderLegend(resp) {
    const palette = PALETTES[resp.layer];
    const edges = [resp.min, ...resp.breaks, resp.max];
    $("legend-title").textContent = `${resp.label} per hexagon`;
    $("legend").innerHTML = palette
      .map(
        (c, i) =>
          `<div><i style="background:${c}"></i>${fmt(edges[i])} – ${fmt(edges[i + 1])}</div>`,
      )
      .join("");
  }

  function renderTotals(resp) {
    const items = [
      [resp.hexagons, "hexagons"],
      [resp.total, resp.label.toLowerCase()],
      [resp.hex_area_km2, "km² per hexagon"],
    ];
    $("totals").innerHTML = items
      .map(([v, l]) => `<div><b>${fmt(v)}</b><span>${l}</span></div>`)
      .join("");
  }

  function renderHotspots(resp) {
    const top = [...hexLayers].sort((a, b) => b.count - a.count).slice(0, 10);
    $("hotspots").innerHTML = top
      .map(
        (h, i) =>
          `<li data-i="${i}"><span>#${i + 1}</span><span>${fmt(h.count)} · ${fmt(h.density)} per km²</span></li>`,
      )
      .join("");
    $("hotspots").onclick = (e) => {
      const li = e.target.closest("li[data-i]");
      if (!li) return;
      const h = top[Number(li.dataset.i)];
      map.fitBounds(h.layer.getBounds(), { maxZoom: 16, padding: [60, 60] });
      h.layer.openTooltip();
    };
  }

  async function load(fit) {
    const id = ++requestId;
    $("status").textContent =
      "Loading… the server may take up to a minute to wake up.";
    const params = new URLSearchParams({
      layer: state.layer,
      size: state.size,
    });
    try {
      const res = await fetch(`/api/analysis/hexgrid/?${params}`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const resp = await res.json();
      if (id !== requestId) return; // a newer request replaced this one
      if (!resp.hexagons) {
        $("status").textContent = "No data to show for that selection.";
        return;
      }
      renderMap(resp, fit);
      renderLegend(resp);
      renderTotals(resp);
      renderHotspots(resp);
      $("note").textContent = resp.note;
      $("status").textContent = "";
    } catch (err) {
      if (id === requestId)
        $("status").textContent =
          "Something went wrong loading the data. Please try again.";
    }
  }

  $("layer").addEventListener("change", (e) => {
    state.layer = e.target.value;
    load(false);
  });
  $("size").addEventListener("change", (e) => {
    state.size = Number(e.target.value);
    load(false);
  });

  load(true);
})();
