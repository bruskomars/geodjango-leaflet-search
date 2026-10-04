document.addEventListener("DOMContentLoaded", init);

function init() {
  // Leaflet map initialization
  const map = L.map("map").setView([14.516589, 121.019333], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "no-referrer-when-downgrade",
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

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
