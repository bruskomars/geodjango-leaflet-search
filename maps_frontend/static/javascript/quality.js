// maps_frontend/static/javascript/quality.js
(function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (v) => (v == null ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 }));
  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };
  const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

  const state = { city: "", barangay: "" };
  const charts = {};
  let areas = [];
  let requestId = 0;

  function barChart(key, canvasId, labels, values, tooltipLabel, xTitle) {
    if (charts[key]) charts[key].destroy();
    charts[key] = new Chart($(canvasId), {
      type: "bar",
      data: { labels, datasets: [{ data: values, backgroundColor: "#2f9c8d", borderRadius: 4 }] },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: tooltipLabel } } },
        scales: {
          x: { beginAtZero: true, grid: { color: "#eef1f5" }, title: { display: true, text: xTitle } },
          y: { grid: { display: false }, ticks: { autoSkip: false } },
        },
      },
    });
  }

  function renderCards(d) {
    const streetMissing = d.addresses.fields.find((f) => f.field === "Street name");
    const cards = [
      [d.roads.total, "road segments", `${fmt(d.roads.unnamed_pct)}% have no name`],
      [d.addresses.total, "house numbers", streetMissing && d.addresses.total ? `${fmt(streetMissing.missing_pct)}% have no street name` : ""],
      [d.landmarks.total, "landmarks", `${fmt(d.landmarks.duplicate_names)} names are used more than once`],
      [d.coverage.barangays, d.coverage.barangays === 1 ? "barangay" : "barangays",
        d.coverage.summary_available ? `${fmt(d.coverage.no_addresses_pct)}% have no house numbers` : ""],
    ];
    $("cards").innerHTML = cards
      .map(([v, l, s]) => `<div class="card"><b>${fmt(v)}</b><span>${l}</span><small>${esc(s)}</small></div>`)
      .join("");
  }

  function renderCharts(d) {
    const missing = [
      { label: "Road name", pct: d.roads.unnamed_pct },
      ...d.addresses.fields.map((f) => ({ label: f.field, pct: f.missing_pct })),
      { label: "Landmark name", pct: d.landmarks.unnamed_pct },
    ];
    barChart("missing", "missing-chart", missing.map((m) => m.label), missing.map((m) => m.pct),
      (ctx) => `${fmt(ctx.parsed.x)}% missing`, "% of records");

    const top = d.landmarks.top_repeated;
    if (top.length) {
      $("repeat-empty").textContent = "";
      barChart("repeat", "repeat-chart", top.map((t) => short(t.name, 24)), top.map((t) => t.count),
        (ctx) => `${fmt(ctx.parsed.x)} landmarks`, "Landmarks with this name");
    } else {
      if (charts.repeat) { charts.repeat.destroy(); charts.repeat = null; }
      $("repeat-empty").textContent = "No repeated landmark names in this selection.";
    }
  }

  function renderCoverage(d) {
    const c = d.coverage;
    if (!c.summary_available) {
      $("coverage").innerHTML = "<li>Barangay summary has not been computed yet.</li>";
      return;
    }
    const items = [
      `${fmt(c.no_landmarks)} of ${fmt(c.barangays)} barangays (${fmt(c.no_landmarks_pct)}%) have no landmarks`,
      `${fmt(c.no_addresses)} barangays (${fmt(c.no_addresses_pct)}%) have no house numbers`,
      `${fmt(c.no_roads)} barangays (${fmt(c.no_roads_pct)}%) have no roads`,
    ];
    if (c.landmarks_outside != null) {
      items.push(`${fmt(c.landmarks_outside)} landmarks and ${fmt(c.addresses_outside)} house numbers fall outside every barangay boundary`);
    }
    $("coverage").innerHTML = items.map((t) => `<li>${esc(t)}</li>`).join("");
  }

  async function load() {
    const id = ++requestId;
    $("status").textContent = "Loading… the server may take up to a minute to wake up.";
    const params = new URLSearchParams();
    if (state.city) params.set("city", state.city);
    if (state.barangay) params.set("barangay", state.barangay);
    try {
      const res = await fetch(`/api/analysis/quality/?${params}`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      if (id !== requestId) return; // a newer request replaced this one
      renderCards(d);
      renderCharts(d);
      renderCoverage(d);
      $("scope").textContent = d.area ? `Showing: ${d.area.label}` : "Showing: all loaded data";
      $("note").textContent = d.note;
      $("status").textContent = "";
    } catch (err) {
      if (id === requestId) $("status").textContent = "Something went wrong loading the data. Please try again.";
    }
  }

  function fillBarangays() {
    const sel = $("barangay");
    const city = areas.find((c) => c.name === state.city);
    sel.disabled = !city;
    sel.innerHTML =
      `<option value="">All barangays</option>` +
      (city ? city.barangays.map((b) => `<option value="${esc(b)}">${esc(b)}</option>`).join("") : "");
  }

  async function init() {
    $("city").addEventListener("change", (e) => {
      state.city = e.target.value;
      state.barangay = "";
      fillBarangays();
      load();
    });
    $("barangay").addEventListener("change", (e) => {
      state.barangay = e.target.value;
      load();
    });
    load();
    try {
      const res = await fetch("/api/analysis/areas/");
      if (!res.ok) throw new Error("HTTP " + res.status);
      areas = (await res.json()).cities;
      $("city").innerHTML =
        `<option value="">Whole database</option>` +
        areas.map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join("");
    } catch (err) {
      // Filters stay at "Whole database"; say why instead of failing silently
      $("scope").textContent = "City list could not be loaded (" + err.message + ").";
    }
  }

  init();
})();
