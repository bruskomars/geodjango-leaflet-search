// maps_frontend/static/javascript/clusters.js
(function () {
  // Same colour ramps as the density grid: violet for landmarks, teal for house numbers
  const PALETTES = {
    landmarks: ["#d3bff3", "#a98beb", "#7c52d6", "#5d33b8", "#3e1f8a"],
    addresses: ["#b7dfd6", "#6fbfb1", "#2f9c8d", "#0f7f72", "#0b5249"],
  };
  const state = { layer: "landmarks", eps: 100, minpts: 10 };
  const $ = (id) => document.getElementById(id);

  const map = L.map("map").setView([14.5995, 121.0], 11);
  L.tileLayer(
    "https://tiles.stadiamaps.com/tiles/stamen_terrain/{z}/{x}/{y}{r}.{ext}",
    {
      minZoom: 0,
      maxZoom: 18,
      referrerPolicy: "no-referrer-when-downgrade",
      attribution:
        '&copy; <a href="https://www.stadiamaps.com/" target="_blank">Stadia Maps</a> &copy; <a href="https://www.stamen.com/" target="_blank">Stamen Design</a> &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      ext: "png",
    },
  ).addTo(map);

  let clusterLayer = null;
  let hoverOutline = null;
  let layersByRank = {};
  let requestId = 0;

  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };
  const fmt = (v) => {
    if (v == null) return "–";
    const digits = Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
    return Number(v).toLocaleString(undefined, {
      maximumFractionDigits: digits,
    });
  };

  // Class thresholds from the clusters on screen (quintiles of their sizes)
  function breaksOf(counts) {
    const s = [...counts].sort((a, b) => a - b);
    const n = s.length;
    return [1, 2, 3, 4].map((i) => s[Math.min(n - 1, Math.floor((n * i) / 5))]);
  }
  function classOf(v, breaks) {
    for (let i = 0; i < breaks.length; i++) if (v < breaks[i]) return i;
    return 4;
  }

  function clearOutline() {
    if (hoverOutline) {
      map.removeLayer(hoverOutline);
      hoverOutline = null;
    }
  }

  function placeText(p) {
    return (
      [p.barangay, p.city].filter(Boolean).join(", ") ||
      "Outside the loaded barangays"
    );
  }

  function renderMap(resp, breaks, fit) {
    clearOutline();
    if (clusterLayer) map.removeLayer(clusterLayer);
    layersByRank = {};
    const palette = PALETTES[resp.layer];
    const unit = resp.label.toLowerCase();
    clusterLayer = L.geoJSON(resp.data, {
      style: (f) => ({
        fillColor: palette[classOf(f.properties.count, breaks)],
        fillOpacity: 0.65,
        color: "#1b2733",
        weight: 1,
      }),
      onEachFeature: (f, layer) => {
        const p = f.properties;
        layersByRank[p.rank] = layer;
        layer.bindTooltip(
          `<strong>#${p.rank}: ${fmt(p.count)} ${unit}</strong><br>${esc(placeText(p))}<br>` +
            `${fmt(p.density)} per km²` +
            (p.top_name
              ? `<br>${esc(resp.name_label)}: ${esc(p.top_name)}`
              : ""),
          { sticky: true },
        );
        layer.on("mouseover", () => {
          clearOutline();
          hoverOutline = L.geoJSON(f, {
            interactive: false,
            style: { fill: false, color: "#ef4444", weight: 3 },
          }).addTo(map);
        });
        layer.on("mouseout", () => {
          clearOutline();
          layer.closeTooltip();
        });
      },
    }).addTo(map);
    if (fit && clusterLayer.getBounds().isValid())
      map.fitBounds(clusterLayer.getBounds(), { padding: [20, 20] });
  }

  function renderLegend(resp, breaks) {
    const counts = resp.data.features.map((f) => f.properties.count);
    const edges = [Math.min(...counts), ...breaks, Math.max(...counts)];
    $("legend-title").textContent = `${resp.label} per cluster`;
    $("legend").innerHTML = PALETTES[resp.layer]
      .map(
        (c, i) =>
          `<div><i style="background:${c}"></i>${fmt(edges[i])} – ${fmt(edges[i + 1])}</div>`,
      )
      .join("");
  }

  function renderTotals(resp) {
    const pct = resp.points ? (100 * resp.clustered_points) / resp.points : 0;
    const items = [
      [resp.clusters, "clusters found"],
      [`${fmt(pct)}%`, "of points in a cluster"],
      [resp.isolated_points, "isolated points"],
    ];
    $("totals").innerHTML = items
      .map(
        ([v, l]) =>
          `<div><b>${typeof v === "number" ? fmt(v) : v}</b><span>${l}</span></div>`,
      )
      .join("");
  }

  function renderList(resp) {
    const unit = resp.label.toLowerCase();
    const top = resp.data.features.slice(0, 15);
    $("list").innerHTML = top
      .map((f) => {
        const p = f.properties;
        const detail = p.top_name
          ? `${esc(placeText(p))} · ${esc(p.top_name)}`
          : esc(placeText(p));
        return `<li data-rank="${p.rank}"><span>${detail}</span><span class="n">${fmt(p.count)}</span><small>${fmt(p.density)} ${unit} per km²</small></li>`;
      })
      .join("");
    $("list").onclick = (e) => {
      const li = e.target.closest("li[data-rank]");
      const layer = li && layersByRank[li.dataset.rank];
      if (!layer) return;
      map.fitBounds(layer.getBounds(), { maxZoom: 17, padding: [60, 60] });
      layer.openTooltip();
    };
  }

  async function load(fit) {
    const id = ++requestId;
    $("status").textContent =
      "Finding clusters… the server may take up to a minute to wake up.";
    const params = new URLSearchParams({
      layer: state.layer,
      eps: state.eps,
      min_points: state.minpts,
    });
    try {
      const res = await fetch(`/api/analysis/clusters/?${params}`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const resp = await res.json();
      if (id !== requestId) return; // a newer request replaced this one
      renderTotals(resp);
      $("note").textContent = resp.note;
      if (!resp.data.features.length) {
        if (clusterLayer) {
          map.removeLayer(clusterLayer);
          clusterLayer = null;
        }
        $("legend").innerHTML = "";
        $("list").innerHTML = "";
        $("status").textContent =
          "No clusters with these settings. Try a larger distance or fewer minimum points.";
        return;
      }
      const breaks = breaksOf(
        resp.data.features.map((f) => f.properties.count),
      );
      renderMap(resp, breaks, fit);
      renderLegend(resp, breaks);
      renderList(resp);
      $("status").textContent =
        resp.clusters > resp.shown
          ? `Showing the ${resp.shown} largest of ${fmt(resp.clusters)} clusters.`
          : "";
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
  $("eps").addEventListener("change", (e) => {
    state.eps = Number(e.target.value);
    load(false);
  });
  $("minpts").addEventListener("change", (e) => {
    state.minpts = Number(e.target.value);
    load(false);
  });

  load(true);
})();
