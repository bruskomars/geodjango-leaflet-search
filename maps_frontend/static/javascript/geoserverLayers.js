// geoserverLayers.js
// Config-driven GeoServer WMS overlays with a group toggle panel

const GEOSERVER_URL = "http://localhost:8080/geoserver/mapsapp/wms";

const GEOSERVER_LAYER_CONFIG = {
  roads: {
    label: "Roads",
    geoserverLayer: "mapsapp:roads",
    popupFields: ["name", "name_sf"],
    popupSeperator: " ",
    layer: L.tileLayer.wms(GEOSERVER_URL, {
      layers: "mapsapp:roads",
      format: "image/png",
      transparent: true,
      version: "1.1.1",
      attribution: "GeoServer",
    }),
  },
  // Add new layers here as you publish them, e.g.:
  admin: {
    label: "Admin Boundaries",
    geoserverLayer: "mapsapp:admin",
    popupFields: ["name3", "name2", "name1"],
    popupSeperator: ", ",
    layer: L.tileLayer.wms(GEOSERVER_URL, {
      layers: "mapsapp:admin",
      format: "image/png",
      transparent: true,
      version: "1.1.1",
      attribution: "GeoServer",
    }),
  },
  landmark: {
    label: "Landmarks",
    geoserverLayer: "mapsapp:landmark",
    popupFields: ["name"],
    popupSeperator: " ",
    layer: L.tileLayer.wms(GEOSERVER_URL, {
      layers: "mapsapp:landmark",
      format: "image/png",
      transparent: true,
      version: "1.1.1",
      attribution: "GeoServer",
    }),
  },
};

const geoserverLayerState = {}; // tracks which layers are currently visible

function buildGeoserverTogglePanel(map) {
  const panel = document.getElementById("geoserver-layer-panel");
  if (!panel) return;

  Object.entries(GEOSERVER_LAYER_CONFIG).forEach(([key, config]) => {
    geoserverLayerState[key] = false;

    const row = document.createElement("label");
    row.style.display = "block";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        config.layer.addTo(map);
        geoserverLayerState[key] = true;
      } else {
        map.removeLayer(config.layer);
        geoserverLayerState[key] = false;
      }
    });

    row.appendChild(checkbox);
    row.appendChild(document.createTextNode(" " + config.label));
    panel.appendChild(row);
  });
}

function setupGeoserverLayers(map) {
  buildGeoserverTogglePanel(map);

  map.on("click", function (e) {
    // find any currently visible GeoServer layer to query
    const activeKey = Object.keys(geoserverLayerState).find(
      (key) => geoserverLayerState[key],
    );
    if (!activeKey) return;

    const config = GEOSERVER_LAYER_CONFIG[activeKey];
    const size = map.getSize();
    const point = map.latLngToContainerPoint(e.latlng, map.getZoom());

    const params = {
      request: "GetFeatureInfo",
      service: "WMS",
      srs: "EPSG:4326",
      styles: "",
      transparent: true,
      version: "1.1.1",
      format: "image/png",
      bbox: map.getBounds().toBBoxString(),
      height: size.y,
      width: size.x,
      layers: config.geoserverLayer,
      query_layers: config.geoserverLayer,
      info_format: "application/json",
      x: Math.round(point.x),
      y: Math.round(point.y),
    };

    const url =
      GEOSERVER_URL + L.Util.getParamString(params, GEOSERVER_URL, true);

    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        if (data.features.length > 0) {
          const props = data.features[0].properties;
          const content = config.popupFields
            .map((f) => props[f])
            .filter(Boolean)
            .join(config.popupSeperator ?? " ");
          L.popup()
            .setLatLng(e.latlng)
            .setContent(content || "No data")
            .openOn(map);
        }
      })
      .catch((err) => console.error("GetFeatureInfo error:", err));
  });
}
