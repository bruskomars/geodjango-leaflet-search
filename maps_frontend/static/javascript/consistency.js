// maps_frontend/static/javascript/consistency.js
(function () {
  const COLORS = {
    match: "#2f9c8d",
    mismatch: "#dc2626",
    missing: "#b8c2cc",
    outside: "#f59e0b",
  };
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
  let features = [];
  let selected = null; // { declared, actual, city } while a pair is chosen
  let requestId = 0;

  function renderStack(stackId, keyId, b, total, outside) {
    const parts = [
      ["match", b.match, "match"],
      ["mismatch", b.mismatch, "mismatch"],
      ["missing", b.missing, "not written on the record"],
      ["outside", outside, "outside every boundary"],
    ];
    $(stackId).innerHTML = parts
      .map(
        ([k, n]) =>
          `<i style="width:${total ? (100 * n) / total : 0}%;background:${COLORS[k]}"></i>`,
      )
      .join("");
    $(keyId).innerHTML = parts
      .map(
        ([k, n, label]) =>
          `<span><i style="background:${COLORS[k]}"></i>${fmt(total ? (100 * n) / total : 0)}% ${label}</span>`,
      )
      .join("");
  }

  function plot() {
    pointLayer.clearLayers();
    const shown = features.filter(
      (f) =>
        !selected ||
        (f.properties.declared === selected.declared &&
          f.properties.actual === selected.actual &&
          f.properties.city === selected.city),
    );
    const markers = shown.map((f) => {
      const p = f.properties;
      const [lng, lat] = f.geometry.coordinates;
      const address = [p.house_number, p.street].filter(Boolean).join(" ");
      return L.circleMarker([lat, lng], {
        radius: 5,
        color: "#ffffff",
        weight: 1,
        fillColor: COLORS.mismatch,
        fillOpacity: 0.9,
      })
        .bindTooltip(
          `${address ? `<strong>${esc(address)}</strong><br>` : ""}Written: ${esc(p.declared)}<br>Falls in: ${esc(p.actual)}, ${esc(p.city)}`,
        )
        .addTo(pointLayer);
    });
    if (markers.length)
      map.fitBounds(L.featureGroup(markers).getBounds(), {
        padding: [30, 30],
        maxZoom: 16,
      });
  }

  function renderPairs(d) {
    $("pairs").innerHTML =
      d.top_pairs
        .map(
          (p, i) => `<button class="pair" aria-pressed="false" data-i="${i}">
            <span>“${esc(p.declared)}” → ${esc(p.actual)}</span><span class="n">${fmt(p.count)}</span>
            <small>${esc(p.city)}</small></button>`,
        )
        .join("") || "<p class='help'>No mismatches at this strictness.</p>";
    $("pairs").onclick = (e) => {
      const btn = e.target.closest(".pair");
      if (!btn) return;
      const p = d.top_pairs[Number(btn.dataset.i)];
      selected = { declared: p.declared, actual: p.actual, city: p.city };
      document
        .querySelectorAll(".pair")
        .forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      $("reset").hidden = false;
      plot();
    };
    $("reset").onclick = () => {
      selected = null;
      document
        .querySelectorAll(".pair")
        .forEach((b) => b.setAttribute("aria-pressed", "false"));
      $("reset").hidden = true;
      plot();
    };
  }

  async function load() {
    const id = ++requestId;
    $("status").textContent =
      "Checking addresses… the server may take up to a minute to wake up.";
    try {
      const res = await fetch(
        `/api/analysis/consistency/?${new URLSearchParams({ strictness: $("strictness").value })}`,
      );
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      if (id !== requestId) return; // a newer request replaced this one
      selected = null;
      $("reset").hidden = true;
      $("total").innerHTML = `<b>${fmt(d.total)}</b> house numbers checked`;
      renderStack("stack-b", "key-b", d.barangay, d.total, d.outside);
      renderStack("stack-m", "key-m", d.municipality, d.total, d.outside);
      features = d.points.data.features;
      renderPairs(d);
      plot();
      $("note").textContent = d.note;
      $("status").textContent =
        d.points.count > d.points.shown
          ? `Showing ${fmt(d.points.shown)} of ${fmt(d.points.count)} mismatched barangay names on the map.`
          : "";
    } catch (err) {
      if (id === requestId)
        $("status").textContent =
          "Something went wrong loading the data. Please try again.";
    }
  }

  $("strictness").addEventListener("change", load);
  load();
})();
