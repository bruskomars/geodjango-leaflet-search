function setupCrossModelSearch(map) {
  const form = document.getElementById("address-search-form");

  let searchResultsLayer = null;

  // Create a message element once, append it under the form
  const messageBox = document.createElement("div");
  messageBox.id = "address-search-message";
  messageBox.style.display = "none";
  form.parentNode.appendChild(messageBox);

  const panel = document.createElement("div");
  panel.id = "search-results-panel";
  Object.assign(panel.style, {
    maxWidth: "100vw",
    maxHeight: "30vh",
    overflowY: "auto",
    background: "white",
    border: "1px solid #ccc",
    borderRadius: "6px",
    boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
    padding: "10px",
    marginTop: "12px",
    display: "none",
    fontSize: "13px",
  });

  const panelHeader = document.createElement("div");
  Object.assign(panelHeader.style, {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "8px",
  });
  const panelTitle = document.createElement("strong");
  panelTitle.textContent = "Search Results";
  const closeBtn = document.createElement("button");
  closeBtn.textContent = "×";
  Object.assign(closeBtn.style, {
    border: "none",
    background: "transparent",
    fontSize: "18px",
    cursor: "pointer",
    lineHeight: "1",
  });
  closeBtn.addEventListener("click", () => {
    panel.style.display = "none";
  });
  panelHeader.appendChild(panelTitle);
  panelHeader.appendChild(closeBtn);

  const panelBody = document.createElement("div");
  panel.appendChild(panelHeader);
  panel.appendChild(panelBody);

  // Insert the panel immediately after the map's container in the DOM,
  // so it renders below the map instead of floating on top of it.
  map.getContainer().insertAdjacentElement("afterend", panel);

  function buildResultTable(title, features, columns, layerRefs) {
    const section = document.createElement("div");
    section.style.marginBottom = "14px";

    const heading = document.createElement("div");
    heading.textContent = `${title} (${features.length})`;
    heading.style.fontWeight = "bold";
    heading.style.margin = "6px 0";
    section.appendChild(heading);

    const table = document.createElement("table");
    Object.assign(table.style, {
      borderCollapse: "collapse",
      width: "100%",
    });

    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    columns.forEach((col) => {
      const th = document.createElement("th");
      th.textContent = col.label;
      Object.assign(th.style, {
        textAlign: "left",
        borderBottom: "1px solid #ddd",
        padding: "4px 6px",
        fontSize: "12px",
      });
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    features.forEach((feature, idx) => {
      const p = feature.properties || {};
      const row = document.createElement("tr");
      row.style.cursor = "pointer";
      row.addEventListener(
        "mouseenter",
        () => (row.style.background = "#f0f4ff"),
      );
      row.addEventListener("mouseleave", () => (row.style.background = ""));

      columns.forEach((col) => {
        const td = document.createElement("td");
        td.textContent = col.value(p) ?? "";
        Object.assign(td.style, {
          borderBottom: "1px solid #eee",
          padding: "4px 6px",
        });
        row.appendChild(td);
      });

      row.addEventListener("click", () => {
        const layer = layerRefs[idx];
        if (!layer) return;
        if (typeof layer.getBounds === "function") {
          map.fitBounds(layer.getBounds(), { maxZoom: 18, padding: [50, 50] });
        } else if (typeof layer.getLatLng === "function") {
          map.setView(layer.getLatLng(), 18);
        }
        if (typeof layer.openPopup === "function") {
          layer.openPopup();
        }
      });

      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    section.appendChild(table);
    return section;
  }

  // submit function in form
  form.addEventListener("submit", function (e) {
    e.preventDefault();

    // preparing data from a form so it can be sent in a URL
    const formData = new FormData(form);
    const params = new URLSearchParams();
    // looping through all the form’s fields and building a clean query string
    for (const [key, value] of formData.entries()) {
      if (value.trim() !== "") {
        params.append(key, value.trim());
      }
    }

    // sends your query string to the backend and handles possible errors before parsing the JSON
    fetch(`/api/search/?${params.toString()}`)
      .then((response) => {
        if (response.status === 404) {
          throw new Error("NOT_FOUND");
        }
        if (!response.ok) {
          throw new Error("SERVER_ERROR");
        }
        return response.json();
      })

      // success handler after fetch returns JSON
      .then((data) => {
        messageBox.style.display = "none";
        panelBody.innerHTML = "";
        panel.style.display = "none";

        // remove previous layer on the map
        if (searchResultsLayer) {
          map.removeLayer(searchResultsLayer);
          searchResultsLayer = null;
        }

        const landmarkGeojson = data.results && data.results.landmark;
        const addressGeojson = data.results && data.results.hn;
        const adminGeojson = data.results && data.results.admin;
        const roadGeojson = data.results && data.results.street;

        const hasLandmarks =
          landmarkGeojson &&
          landmarkGeojson.features &&
          landmarkGeojson.features.length > 0;
        const hasAddresses =
          addressGeojson &&
          addressGeojson.features &&
          addressGeojson.features.length > 0;
        const hasAdmin =
          adminGeojson &&
          adminGeojson.features &&
          adminGeojson.features.length > 0;
        const hasRoad =
          roadGeojson &&
          roadGeojson.features &&
          roadGeojson.features.length > 0;

        const allLayers = [];

        if (!hasLandmarks && !hasAddresses && !hasAdmin && !hasRoad) {
          messageBox.textContent = "No results found for that search.";
          messageBox.style.display = "block";
          return;
        }

        // Track individual feature layers per type, in feature order,
        // so table rows can be matched to the right marker/shape.
        const landmarkLayerRefs = [];
        const addressLayerRefs = [];
        const adminLayerRefs = [];
        const roadLayerRefs = [];

        if (hasLandmarks) {
          const landmarkLayer = L.geoJSON(landmarkGeojson, {
            pointToLayer: function (feature, latlng) {
              const marker = L.marker(latlng);
              landmarkLayerRefs.push(marker);
              return marker;
            },
            onEachFeature: function (feature, layer) {
              const p = feature.properties;
              const popupText = [p.name, p.admin?.barangay, p.admin?.city]
                .filter(Boolean)
                .join(", ");
              layer.bindPopup(popupText);
            },
          });
          allLayers.push(landmarkLayer);
        }

        if (hasAddresses) {
          const addressLayer = L.geoJSON(addressGeojson, {
            pointToLayer: function (feature, latlng) {
              const marker = L.marker(latlng);
              addressLayerRefs.push(marker);
              return marker;
            },
            onEachFeature: function (feature, layer) {
              const p = feature.properties;
              const popupText = [p.hn, p.sn, p.barangay, p.municipality]
                .filter(Boolean)
                .join(", ");
              layer.bindPopup(popupText);
            },
          });
          allLayers.push(addressLayer);
        }

        if (hasAdmin) {
          const adminLayer = L.geoJSON(adminGeojson, {
            style: function (feature) {
              return {
                color: "black",
                weight: 2,
                fillColor: "blue",
                fillOpacity: 0.3,
              };
            },
            onEachFeature: function (feature, layer) {
              const p = feature.properties;
              const popUptext = [p.barangay, p.city].filter(Boolean).join(", ");
              layer.bindPopup(popUptext);
              adminLayerRefs.push(layer);
            },
          });
          allLayers.push(adminLayer);
        }

        if (hasRoad) {
          const roadLayer = L.geoJSON(roadGeojson, {
            style: function (feature) {
              return {
                color: "blue",
                weight: 5,
              };
            },
            onEachFeature: function (feature, layer) {
              const p = feature.properties;
              const popUpText = [p.name_pf, p.name, p.name_sf]
                .filter(Boolean)
                .join(" ");
              layer.bindPopup(popUpText);
              roadLayerRefs.push(layer);
            },
          });
          allLayers.push(roadLayer);
        }

        searchResultsLayer = L.layerGroup(allLayers).addTo(map);

        const combined = allLayers.reduce(
          (bounds, layer) => bounds.extend(layer.getBounds()),
          L.latLngBounds([]),
        );
        map.fitBounds(combined, { padding: [50, 50], maxZoom: 17 });

        // --- Build the results table overlay, one section per model ---
        if (hasLandmarks) {
          panelBody.appendChild(
            buildResultTable(
              "Landmarks",
              landmarkGeojson.features,
              [
                { label: "Name", value: (p) => p.name },
                { label: "Barangay", value: (p) => p.admin?.barangay },
                { label: "City", value: (p) => p.admin?.city },
                { label: "Province", value: (p) => p.admin?.province },
                {
                  label: "Nearest Streets",
                  value: (p) =>
                    (p.nearest_streets || []).map((s) => s.name).join(", "),
                },
              ],
              landmarkLayerRefs,
            ),
          );
        }

        if (hasAddresses) {
          panelBody.appendChild(
            buildResultTable(
              "Addresses",
              addressGeojson.features,
              [
                { label: "House No.", value: (p) => p.hn },
                { label: "Street", value: (p) => p.sn },
                { label: "Subdivision", value: (p) => p.subdivision },
                { label: "Barangay", value: (p) => p.barangay },
                { label: "Municipality", value: (p) => p.municipality },
              ],
              addressLayerRefs,
            ),
          );
        }

        if (hasAdmin) {
          panelBody.appendChild(
            buildResultTable(
              "Admin Boundaries",
              adminGeojson.features,
              [
                { label: "Barangay", value: (p) => p.barangay },
                { label: "City", value: (p) => p.city },
                { label: "Province", value: (p) => p.province },
              ],
              adminLayerRefs,
            ),
          );
        }

        if (hasRoad) {
          panelBody.appendChild(
            buildResultTable(
              "Roads",
              roadGeojson.features,
              [
                { label: "Name", value: (p) => p.name },
                { label: "Prefix", value: (p) => p.name_pf },
                { label: "Suffix", value: (p) => p.name_sf },
                { label: "Barangay", value: (p) => p.admin?.barangay },
                { label: "City", value: (p) => p.admin?.city },
                { label: "Province", value: (p) => p.admin?.province },
              ],
              roadLayerRefs,
            ),
          );
        }

        panel.style.display = "block";
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
      })
      .catch((err) => {
        if (searchResultsLayer) {
          map.removeLayer(searchResultsLayer);
          searchResultsLayer = null;
        }
        if (err.message === "NOT_FOUND") {
          messageBox.textContent = "No results found for that address.";
        } else {
          messageBox.textContent = "Something went wrong. Please try again.";
        }
        messageBox.style.display = "block";
      });
  });
}
