// maps_frontend/static/javascript/insights.js
(function () {
  const PALETTE = ["#eaf6f3", "#b7dfd6", "#6fbfb1", "#2f9c8d", "#0f6b61"];
  const state = { metric: "landmark_density", city: "", citiesLoaded: false };
  const $ = (id) => document.getElementById(id);

  const map = L.map("map").setView([14.5995, 121.0], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "no-referrer-when-downgrade",
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  let geoLayer = null;
  let hoverOutline = null;
  let chart = null;
  let requestId = 0;

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fmt(v) {
    if (v == null) return "–";
    const digits = Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
    return Number(v).toLocaleString(undefined, {
      maximumFractionDigits: digits,
    });
  }

  // breaks are 4 thresholds: values below breaks[0] are class 0, and so on
  function classOf(value, breaks) {
    for (let i = 0; i < breaks.length; i++) if (value < breaks[i]) return i;
    return PALETTE.length - 1;
  }

  function popupHtml(p) {
    return (
      `<strong>${esc(p.name)}</strong><br>${esc(p.city)}<br>` +
      `Area: ${fmt(p.area_km2)} km²<br>` +
      `Landmarks: ${fmt(p.landmark_count)} (${fmt(p.landmark_density)}/km²)<br>` +
      `House numbers: ${fmt(p.address_count)} (${fmt(p.address_density)}/km²)<br>` +
      `Roads: ${fmt(p.road_km)} km (${fmt(p.road_density)} km/km²)`
    );
  }

  function renderMap(resp, fit) {
    if (geoLayer) map.removeLayer(geoLayer);
    if (hoverOutline) {
      map.removeLayer(hoverOutline);
      hoverOutline = null;
    }
    const { metric, breaks } = resp;
    geoLayer = L.geoJSON(resp.data, {
      style: (f) => ({
        fillColor: PALETTE[classOf(f.properties[metric], breaks)],
        fillOpacity: 0.85,
        color: "#ffffff",
        weight: 0.6,
      }),
      onEachFeature: (f, layer) => {
        const p = f.properties;
        layer.bindTooltip(`${esc(p.name)}, ${esc(p.city)}: ${fmt(p[metric])}`, {
          sticky: true,
        });
        layer.bindPopup(popupHtml(p));
        layer.on("mouseover", () => {
          if (hoverOutline) map.removeLayer(hoverOutline);
          hoverOutline = L.geoJSON(f, {
            interactive: false,
            style: { fill: false, color: "#1b2733", weight: 2 },
          }).addTo(map);
        });
        layer.on("mouseout", () => {
          if (hoverOutline) {
            map.removeLayer(hoverOutline);
            hoverOutline = null;
          }
          layer.closeTooltip();
        });
      },
    }).addTo(map);
    if (fit && geoLayer.getBounds().isValid())
      map.fitBounds(geoLayer.getBounds(), { padding: [20, 20] });
  }

  function renderLegend(resp) {
    const edges = [resp.min, ...resp.breaks, resp.max];
    $("legend-title").textContent = resp.label;
    $("legend").innerHTML = PALETTE.map(
      (color, i) =>
        `<div><i style="background:${color}"></i>${fmt(edges[i])} – ${fmt(edges[i + 1])}</div>`,
    ).join("");
  }

  function renderTotals(resp) {
    const t = resp.totals;
    const items = [
      [resp.count, "barangays"],
      [t.landmarks, "landmarks"],
      [t.addresses, "house numbers"],
      [t.road_km, "km of road"],
    ];
    $("totals").innerHTML = items
      .map(([v, l]) => `<div><b>${fmt(v)}</b><span>${l}</span></div>`)
      .join("");
  }

  function renderChart(resp) {
    const top = resp.top;
    const labels = top.map((r) =>
      r.name.length > 22 ? r.name.slice(0, 21) + "…" : r.name,
    );
    if (chart) chart.destroy();
    chart = new Chart($("top-chart"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            data: top.map((r) => r.value),
            backgroundColor: "#2f9c8d",
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) =>
                `${top[items[0].dataIndex].name}, ${top[items[0].dataIndex].city}`,
              label: (ctx) => `${resp.label}: ${fmt(ctx.parsed.x)}`,
            },
          },
        },
        scales: {
          x: { beginAtZero: true, grid: { color: "#eef1f5" } },
          y: { grid: { display: false }, ticks: { autoSkip: false } },
        },
      },
    });
  }

  function fillCities(resp) {
    const cities = [
      ...new Set(resp.data.features.map((f) => f.properties.city)),
    ]
      .filter(Boolean)
      .sort();
    $("city").innerHTML =
      `<option value="">All of NCR</option>` +
      cities
        .map((c) => `<option value="${esc(c)}">${esc(c)}</option>`)
        .join("");
    state.citiesLoaded = true;
  }

  async function load(fit) {
    const id = ++requestId;
    $("status").textContent =
      "Loading… the server may take up to a minute to wake up.";
    const params = new URLSearchParams({ metric: state.metric });
    if (state.city) params.set("city", state.city);
    try {
      const res = await fetch(`/api/analysis/barangays/?${params}`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const resp = await res.json();
      if (id !== requestId) return; // a newer request replaced this one
      if (!resp.count) {
        $("status").textContent = "No barangays found for that selection.";
        return;
      }
      if (!state.citiesLoaded && !state.city) fillCities(resp);
      renderMap(resp, fit);
      renderLegend(resp);
      renderTotals(resp);
      renderChart(resp);
      $("note").textContent = resp.note;
      $("status").textContent = "";
    } catch (err) {
      if (id === requestId)
        $("status").textContent =
          "Something went wrong loading the data. Please try again.";
    }
  }

  $("metric").addEventListener("change", (e) => {
    state.metric = e.target.value;
    load(false);
  });
  $("city").addEventListener("change", (e) => {
    state.city = e.target.value;
    load(true);
  });

  load(true);
})();
