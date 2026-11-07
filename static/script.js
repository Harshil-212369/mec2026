
async function loadData(endpoint) {
    const results = document.getElementById("results");

    results.textContent = "Loading...";

    try {
        const response = await fetch(endpoint);

        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }

        const data = await response.json();

        results.textContent = JSON.stringify(data, null, 2);

    } catch (error) {
        results.textContent = "Error: " + error.message;
    }
}

let activeDataset = null;

const map = L.map("map").setView(
    [43.657, -79.387], 14
);

// OpenStreetMap background
L.tileLayer(
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
    }
).addTo(map);

// Separate map layers
const roadLayer = L.layerGroup().addTo(map);
const supplierLayer = L.layerGroup().addTo(map);
const requesterLayer = L.layerGroup().addTo(map);

// Store graph nodes for lookup
let nodeLookup = {};

// Escape database text before placing it in HTML popups
function escapeHTML(value) {
    return String(value ?? "").replace(
        /[&<>"']/g,
        ch => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        })[ch]
    );
}

async function loadMap() {
    try {
        const response = await fetch(
            `/api/map?dataset_id=${encodeURIComponent(activeDataset)}`,
            { cache: "no-store" }
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Remove previously drawn features
        roadLayer.clearLayers();
        supplierLayer.clearLayers();
        requesterLayer.clearLayers();

        // Build dictionary of node ID -> node
        nodeLookup = {};

        data.nodes.forEach(node => {
            nodeLookup[node.node_id] = node;
        });

        // Draw roads
        data.roads.forEach(road => {

            const start = nodeLookup[road.node_a];
            const end = nodeLookup[road.node_b];

            if (!start || !end) return;

            const line = L.polyline(
                [
                    [start.lat, start.lng],
                    [end.lat, end.lng]
                ],
                {
                    color: road.is_closed ? "#dc2626" : "#2563eb",
                    weight: 2,
                    opacity: 0.55,
                    dashArray: road.is_closed ? "6, 6" : null
                }
            );

            line.bindPopup(`
                <strong>${escapeHTML(road.street)}</strong>
                <br>Road ID: ${road.road_id}
                <br>Distance: ${road.distance_km} km
                <br>Weight: ${road.weight}
                <br>Status: ${road.is_closed ? "Closed" : "Open"}
            `);

            line.addTo(roadLayer);
        });

        // Draw supplier markers
        data.suppliers.forEach(supplier => {

            const marker = L.circleMarker(
                [supplier.lat, supplier.lng],
                {
                    radius: 10,
                    color: "#ffffff",
                    weight: 2,
                    fillColor: "#2563eb",
                    fillOpacity: 1
                }
            );

            marker.bindPopup(`
                <strong>${escapeHTML(supplier.name)}</strong>
                <hr>
                Supplier: ${escapeHTML(supplier.supp_id)}
                <br>Normal stock: ${supplier.normal_stock}
                <br>Cold stock: ${supplier.cold_stock}
                <br>Node: ${supplier.node_id}
            `);

            marker.addTo(supplierLayer);
        });

        // Draw requester markers
        data.requesters.forEach(requester => {

            const marker = L.circleMarker(
                [requester.lat, requester.lng],
                {
                    radius: 10,
                    color: "#ffffff",
                    weight: 2,
                    fillColor: "#dc2626",
                    fillOpacity: 1
                }
            );

            marker.bindPopup(`
                <strong>${escapeHTML(requester.name)}</strong>
                <hr>
                Requester: ${escapeHTML(requester.req_id)}
                <br>Category: ${escapeHTML(requester.category)}
                <br>Node: ${requester.node_id}
            `);

            marker.addTo(requesterLayer);
        });

        // Fit viewport to the road network
        const coordinates = data.nodes.map(node => [
            node.lat, node.lng
        ]);

        if (coordinates.length > 0) {
            map.fitBounds(
                L.latLngBounds(coordinates),
                { padding: [25, 25] }
            );
        }

        console.log("Map loaded successfully");
        console.log("Nodes:", data.nodes.length);
        console.log("Roads:", data.roads.length);
        console.log("Suppliers:", data.suppliers.length);
        console.log("Requesters:", data.requesters.length);

    } catch (error) {
        console.error("Map loading failed:", error);
    }
}

// Toggleable map layers
L.control.layers(
    {},
    {
        "Road Network": roadLayer,
        "Suppliers": supplierLayer,
        "Requesters": requesterLayer
    },
    { collapsed: false }
).addTo(map);



const datasetSelect =
    document.getElementById("datasetSelect");

const datasetMessage =
    document.getElementById("datasetMessage");

const activeRegionName =
    document.getElementById("activeRegionName");

let switchingDataset = false;


// Retrieve datasets and active region from Neon
async function loadDatasetOptions() {

    const response = await fetch("/api/datasets", {
        cache: "no-store"
    });

    if (!response.ok) {
        throw new Error("Could not retrieve datasets");
    }

    const datasets = await response.json();

    datasetSelect.replaceChildren();

    datasets.forEach(dataset => {
        const option = document.createElement("option");

        option.value = dataset.dataset_id;
        option.textContent = dataset.name;

        datasetSelect.appendChild(option);
    });

    const active = datasets.find(d => d.is_active);

    if (!active) {
        throw new Error("No active dataset configured");
    }

    activeDataset = active.dataset_id;
    datasetSelect.value = activeDataset;
    activeRegionName.textContent = active.name;

    console.log("Active dataset:", activeDataset);

    // Reload the map using the active dataset
    await loadMap();
}


// Switch the active region in Neon
async function switchDataset(datasetId) {

    const response = await fetch(
        "/api/datasets/activate",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                dataset_id: datasetId
            })
        }
    );

    const result = await response.json();

    if (!response.ok) {
        throw new Error(
            result.error || "Dataset switch failed"
        );
    }

    // Verify that Neon saved the active dataset
    const checkResponse = await fetch(
        "/api/active-dataset",
        { cache: "no-store" }
    );

    if (!checkResponse.ok) {
        throw new Error("Could not verify active region");
    }

    const active = await checkResponse.json();

    if (active.dataset_id !== datasetId) {
        throw new Error(
            "Active region did not update in database"
        );
    }

    return result;
}


// Handle dataset dropdown changes
datasetSelect.addEventListener("change", async () => {

    if (switchingDataset) return;

    switchingDataset = true;
    datasetSelect.disabled = true;

    const selectedDataset = datasetSelect.value;

    try {
        datasetMessage.textContent = "Switching region...";

        await switchDataset(selectedDataset);

        await loadDatasetOptions();

        datasetMessage.textContent =
            "Region switched successfully.";

    } catch (error) {
        console.error("Dataset switch failed:", error);

        datasetMessage.textContent = error.message;

        // Restore current active region from database
        try {
            await loadDatasetOptions();
        } catch (refreshError) {
            console.error(refreshError);
        }

    } finally {
        switchingDataset = false;
        datasetSelect.disabled = false;
    }
});


// Upload a new region dataset
document.getElementById("datasetUploadForm")
    .addEventListener("submit", async event => {

        event.preventDefault();

        const fileInput =
            document.getElementById("datasetFile");

        const uploadBtn =
            document.getElementById("uploadDatasetBtn");

        if (!fileInput.files.length) return;

        const formData = new FormData();

        formData.append("file", fileInput.files[0]);

        formData.append(
            "activate",
            document.getElementById(
                "activateOnImport"
            ).checked
        );

        uploadBtn.disabled = true;
        datasetMessage.textContent = "Importing dataset...";

        try {
            const response = await fetch(
                "/api/datasets/upload",
                {
                    method: "POST",
                    body: formData
                }
            );

            const result = await response.json();

            if (!response.ok) {
                throw new Error(
                    result.error || "Import failed"
                );
            }

            fileInput.value = "";

            await loadDatasetOptions();

            datasetMessage.textContent =
                `Dataset ${result.dataset_id} imported successfully.`;

        } catch (error) {
            console.error(error);
            datasetMessage.textContent = error.message;

        } finally {
            uploadBtn.disabled = false;
        }
    });

    
const dispatchBtn =
    document.getElementById("dispatchBtn");

dispatchBtn.addEventListener("click", async () => {

    const message =
        document.getElementById("dispatchMessage");

    dispatchBtn.disabled = true;
    message.textContent = "Processing deliveries...";

    try {
        const response = await fetch(
            "/api/dispatch",
            { method: "POST" }
        );

        const contentType =
            response.headers.get("content-type") || "";

        if (!contentType.includes("application/json")) {
            throw new Error(
                `Server error HTTP ${response.status}`
            );
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Dispatch failed"
            );
        }

        message.textContent =
            `${data.assignments_created} delivery ` +
            `assignments created.`;

        console.table(data.assignments);

        // Refresh any existing priority table
        if (typeof loadTicketQueue === "function") {
            await loadTicketQueue();
        }

        await loadMap();

    } catch (error) {
        console.error(error);
        message.textContent = error.message;

    } finally {
        dispatchBtn.disabled = false;
    }
});


// Initial page load
loadDatasetOptions().catch(error => {
    console.error("Initialization failed:", error);
    datasetMessage.textContent = error.message;
});
