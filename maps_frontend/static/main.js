document.addEventListener("DOMContentLoaded", init);

function init() {
  // Leaflet map initialization
  const map = L.map("map").setView([14.516589, 121.019333], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "no-referrer-when-downgrade",
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  // // "Barangay insights" button under the zoom control
  // const InsightsLink = L.Control.extend({
  //   options: { position: "topleft" },
  //   onAdd() {
  //     const box = L.DomUtil.create("div", "leaflet-bar insights-control");
  //     box.innerHTML =
  //       '<a href="/maps/insights/" title="Barangay insights">Barangay insights</a>';
  //     L.DomEvent.disableClickPropagation(box);
  //     return box;
  //   },
  // });
  // map.addControl(new InsightsLink());

  // Analysis shortcuts under the zoom control
  const AnalysisLinks = L.Control.extend({
    options: { position: "topleft" },
    onAdd() {
      const box = L.DomUtil.create("div", "leaflet-bar insights-control");
      box.innerHTML =
        '<a href="/maps/insights/" title="Barangay insights">Barangay insights</a>' +
        '<a href="/maps/quality/" title="Data quality">Data quality</a>' +
        '<a href="/maps/radius/" title="Radius analysis">Radius analysis</a>' +
        '<a href="/maps/density/" title="Density grid">Density grid</a>';
      L.DomEvent.disableClickPropagation(box);
      return box;
    },
  });
  map.addControl(new AnalysisLinks());

  // fetch data from the backend API
  const fetchGetRequest = async (url, func) => {
    try {
      const response = await fetch(url);
      const data = await response.json();
      func(data);
    } catch (error) {
      console.error("Error fetching data:", error);
    }
  };

  setupCrossModelSearch(map);
}
