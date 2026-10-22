// maps_frontend/static/javascript/compare.js
(function () {
  const COLORS = { a: "#2563eb", b: "#ea580c" };
  const $ = (id) => document.getElementById(id);
  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };
  const fmt = (v) =>
    v == null
      ? "–"
      : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });

  const map = L.map("map").setView([14.5995, 121.0], 11);
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 19,
      referrerPolicy: "no-referrer-when-downgrade",
      attribution:
        "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, TomTom, Intermap, iPC, USGS, FAO, NPS, NRCAN, GeoBase, Kadaster NL, Ordnance Survey, Esri Japan, METI, Esri China (Hong Kong), and the GIS User Community",
    },
  ).addTo(map);

  const layers = { a: null, b: null };
  let chart = null;
  let areas = [];
  let requestId = 0;

  function fillBarangays(side) {
    const city = areas.find((c) => c.name === $(`${side}-city`).value);
    const sel = $(`${side}-barangay`);
    sel.disabled = !city;
    sel.innerHTML =
      `<option value="">Whole city</option>` +
      (city
        ? city.barangays
            .map((b) => `<option value="${esc(b)}">${esc(b)}</option>`)
            .join("")
        : "");
  }

  function renderMap(d) {
    for (const side of ["a", "b"]) {
      if (layers[side]) map.removeLayer(layers[side]);
      layers[side] = L.geoJSON(d[side].geometry, {
        style: {
          color: COLORS[side],
          weight: 1.5,
          fillColor: COLORS[side],
          fillOpacity: 0.25,
        },
        onEachFeature: (f, layer) =>
          layer.bindTooltip(
            `${esc(f.properties.name)} (${esc(d[side].label)})`,
            { sticky: true },
          ),
      }).addTo(map);
    }
    const group = L.featureGroup([layers.a, layers.b]);
    if (group.getBounds().isValid())
      map.fitBounds(group.getBounds(), { padding: [20, 20] });
  }

  function renderTable(d) {
    $("th-a").textContent = d.a.label;
    $("th-b").textContent = d.b.label;
    const metrics = [
      ["Barangays", "barangays"],
      ["Area (km²)", "area_km2"],
      ["Landmarks", "landmarks"],
      ["House numbers", "addresses"],
      ["Road length (km)", "road_km"],
      ["Landmarks per km²", "landmark_density"],
      ["House numbers per km²", "address_density"],
      ["Road km per km²", "road_density"],
    ];
    $("rows").innerHTML = metrics
      .map(([label, key]) => {
        const a = d.a[key];
        const b = d.b[key];
        return `<tr><td>${label}</td><td class="${a > b ? "win" : ""}">${fmt(a)}</td><td class="${b > a ? "win" : ""}">${fmt(b)}</td></tr>`;
      })
      .join("");
  }

  function renderChart(d) {
    // The categories with the highest combined density come first
    const byKey = Object.fromEntries(d.b.categories.map((c) => [c.key, c]));
    const rows = d.a.categories
      .map((c) => ({ label: c.label, a: c.per_km2, b: byKey[c.key].per_km2 }))
      .sort((x, y) => y.a + y.b - (x.a + x.b));
    if (chart) chart.destroy();
    chart = new Chart($("chart"), {
      type: "bar",
      data: {
        labels: rows.map((r) => r.label),
        datasets: [
          {
            label: d.a.label,
            data: rows.map((r) => r.a),
            backgroundColor: COLORS.a,
            borderRadius: 3,
          },
          {
            label: d.b.label,
            data: rows.map((r) => r.b),
            backgroundColor: COLORS.b,
            borderRadius: 3,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          tooltip: {
            callbacks: {
              label: (c) => `${c.dataset.label}: ${fmt(c.parsed.x)} per km²`,
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            grid: { color: "#eef1f5" },
            title: { display: true, text: "Landmarks per km²" },
          },
          y: { grid: { display: false }, ticks: { autoSkip: false } },
        },
      },
    });
  }

  async function load() {
    const aCity = $("a-city").value;
    const bCity = $("b-city").value;
    if (!aCity || !bCity) return;
    const id = ++requestId;
    $("status").textContent =
      "Comparing… the server may take up to a minute to wake up.";
    const params = new URLSearchParams({ a_city: aCity, b_city: bCity });
    if ($("a-barangay").value) params.set("a_barangay", $("a-barangay").value);
    if ($("b-barangay").value) params.set("b_barangay", $("b-barangay").value);
    try {
      const res = await fetch(`/api/analysis/compare/?${params}`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      if (id !== requestId) return; // a newer request replaced this one
      renderMap(d);
      renderTable(d);
      renderChart(d);
      $("result").hidden = false;
      $("note").textContent = d.note;
      $("status").textContent = "";
    } catch (err) {
      if (id === requestId)
        $("status").textContent =
          "Something went wrong loading the comparison. Please try again.";
    }
  }

  async function init() {
    for (const side of ["a", "b"]) {
      $(`${side}-city`).addEventListener("change", () => {
        fillBarangays(side);
        load();
      });
      $(`${side}-barangay`).addEventListener("change", load);
    }
    try {
      const res = await fetch("/api/analysis/areas/");
      if (!res.ok) throw new Error("HTTP " + res.status);
      areas = (await res.json()).cities;
      const options = areas
        .map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`)
        .join("");
      for (const side of ["a", "b"])
        $(`${side}-city`).innerHTML =
          `<option value="">Choose a city</option>` + options;
    } catch (err) {
      $("status").textContent =
        "The city list could not be loaded (" + err.message + ").";
    }
  }

  init();
})();
