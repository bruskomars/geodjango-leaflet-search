// maps_frontend/static/javascript/radius.js
(function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (v) =>
    v == null
      ? "–"
      : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };
  const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

  const map = L.map("map").setView([14.5995, 121.0], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "no-referrer-when-downgrade",
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const state = { latlng: null, radius: 500 };
  const landmarkLayer = L.layerGroup().addTo(map);
  let circle = null;
  let centre = null;
  let chart = null;
  let markers = [];
  let requestId = 0;
  let timer = null;

  function drawCircle() {
    if (!circle) {
      circle = L.circle(state.latlng, {
        radius: state.radius,
        color: "#0f766e",
        weight: 2,
        fillColor: "#0f766e",
        fillOpacity: 0.08,
        interactive: false,
      }).addTo(map);
      centre = L.circleMarker(state.latlng, {
        radius: 6,
        color: "#ffffff",
        weight: 2,
        fillColor: "#0f766e",
        fillOpacity: 1,
        interactive: false,
      }).addTo(map);
    } else {
      circle.setLatLng(state.latlng).setRadius(state.radius);
      centre.setLatLng(state.latlng);
    }
  }

  function renderCards(d) {
    const items = [
      [d.landmarks.count, "landmarks"],
      [d.addresses.count, "house numbers"],
      [d.roads.km, "km of road"],
    ];
    $("cards").innerHTML = items
      .map(([v, l]) => `<div><b>${fmt(v)}</b><span>${l}</span></div>`)
      .join("");
  }

  function renderLandmarks(d) {
    landmarkLayer.clearLayers();
    markers = d.landmarks.items.map((lm) =>
      L.circleMarker([lm.lat, lm.lng], {
        radius: 5,
        color: "#ffffff",
        weight: 1,
        fillColor: "#7c3aed",
        fillOpacity: 0.95,
      })
        .bindTooltip(`${esc(lm.name)} (${fmt(lm.distance_m)} m)`)
        .addTo(landmarkLayer),
    );
    $("landmarks").innerHTML =
      d.landmarks.items
        .slice(0, 10)
        .map(
          (lm, i) =>
            `<li data-i="${i}"><span>${esc(lm.name)}</span><span>${fmt(lm.distance_m)} m</span></li>`,
        )
        .join("") || "<li>No landmarks inside the circle.</li>";
    const hidden = d.landmarks.count - Math.min(10, d.landmarks.items.length);
    $("more").textContent =
      d.landmarks.count > d.landmarks.shown
        ? `Showing the 10 nearest of ${fmt(d.landmarks.count)}; the nearest ${d.landmarks.shown} are plotted on the map.`
        : hidden > 0
          ? `Showing the 10 nearest of ${fmt(d.landmarks.count)}; all are plotted on the map.`
          : "";
  }

  function renderChart(d) {
    const top = d.roads.top;
    if (chart) {
      chart.destroy();
      chart = null;
    }
    if (!top.length) return;
    chart = new Chart($("road-chart"), {
      type: "bar",
      data: {
        labels: top.map((r) => short(r.name, 24)),
        datasets: [
          {
            data: top.map((r) => r.metres),
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
              title: (i) => top[i[0].dataIndex].name,
              label: (c) => `${fmt(c.parsed.x)} m of road`,
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            grid: { color: "#eef1f5" },
            title: { display: true, text: "Metres inside the circle" },
          },
          y: { grid: { display: false }, ticks: { autoSkip: false } },
        },
      },
    });
  }

  async function analyse() {
    const id = ++requestId;
    $("status").textContent =
      "Analysing… the server may take up to a minute to wake up.";
    const params = new URLSearchParams({
      lat: state.latlng.lat,
      lng: state.latlng.lng,
      radius: state.radius,
    });
    try {
      const res = await fetch(`/api/analysis/radius/?${params}`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      if (id !== requestId) return; // a newer request replaced this one
      $("hint").hidden = true;
      $("where").textContent = d.barangay
        ? `${d.barangay.name}, ${d.barangay.city}`
        : "Outside the loaded barangay boundaries";
      renderCards(d);
      renderLandmarks(d);
      renderChart(d);
      $("details").hidden = false;
      $("note").textContent = d.note;
      $("status").textContent = "";
    } catch (err) {
      if (id === requestId)
        $("status").textContent =
          "Something went wrong loading the data. Please try again.";
    }
  }

  function schedule(delay) {
    clearTimeout(timer);
    timer = setTimeout(analyse, delay);
  }

  map.on("click", (e) => {
    state.latlng = e.latlng;
    drawCircle();
    schedule(0);
  });

  $("radius").addEventListener("input", (e) => {
    state.radius = Number(e.target.value);
    $("radius-label").textContent = `${fmt(state.radius)} m`;
    if (state.latlng) {
      drawCircle();
      schedule(350); // wait until the slider stops moving
    }
  });

  $("landmarks").addEventListener("click", (e) => {
    const li = e.target.closest("li[data-i]");
    if (!li) return;
    const marker = markers[Number(li.dataset.i)];
    if (marker) {
      map.panTo(marker.getLatLng());
      marker.openTooltip();
    }
  });
})();
