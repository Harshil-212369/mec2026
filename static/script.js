
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

// Separate layer for highlighting delivery routes
const dashboardRouteLayer = L.layerGroup().addTo(map);

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
        dashboardRouteLayer.clearLayers();

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
    await loadOperationsDashboard();
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



function highlightDeliveryRoute(savedRoute) {

    dashboardRouteLayer.clearLayers();

    let nodeIds = savedRoute;

    // Support routes stored as JSON text or JSONB arrays
    if (typeof nodeIds === "string") {
        try {
            nodeIds = JSON.parse(nodeIds);
        } catch (error) {
            alert("Invalid route format");
            return;
        }
    }

    if (!Array.isArray(nodeIds) || nodeIds.length === 0) {
        alert("No route saved for this delivery");
        return;
    }

    const coordinates = [];

    for (const id of nodeIds) {
        const node = nodeLookup[id];

        if (!node) {
            alert(
                "Route contains a node not in the current map"
            );
            return;
        }

        coordinates.push([node.lat, node.lng]);
    }

    const line = L.polyline(coordinates, {
        color: "#16a34a",
        weight: 7,
        opacity: 0.9
    });

    line.addTo(dashboardRouteLayer);

    if (coordinates.length > 1) {
        map.fitBounds(line.getBounds(), {
            padding: [40, 40]
        });
    } else {
        map.setView(coordinates[0], 15);
    }
}


async function postOperationsAction(url, button, label) {

    const message =
        document.getElementById("dispatchMessage");

    button.disabled = true;
    message.textContent = label + "...";

    try {
        const response = await fetch(url, {
            method: "POST"
        });

        const contentType =
            response.headers.get("content-type") || "";

        if (!contentType.includes("application/json")) {
            throw new Error(`Server error ${response.status}`);
        }

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error || "Operation failed"
            );
        }

        message.textContent = result.message;

        await loadOperationsDashboard();

    } catch (error) {
        console.error(error);
        message.textContent = error.message;

    } finally {
        button.disabled = false;
    }
}



async function loadOperationsDashboard() {
    const response = await fetch(
        "/api/operations/overview",
        { cache: "no-store" }
    );

    if (!response.ok) {
        throw new Error(
            `Dashboard failed: HTTP ${response.status}`
        );
    }

    const data = await response.json();

    // Ignore responses from previously selected regions
    if (data.dataset_id !== activeDataset) {
        return;
    }

    // Update overview statistics
    document.getElementById("statTickets").textContent =
        data.statistics.active_tickets;

    document.getElementById("statDeliveries").textContent =
        data.statistics.active_deliveries;

    document.getElementById("statVehicles").textContent =
        data.statistics.available_vehicles;

    document.getElementById("statFood").textContent =
        data.statistics.available_food;

    // Update tables and resource panels
    renderTickets(data.tickets);
    renderDeliveries(data.deliveries);
    renderSuppliers(data.suppliers);
    renderVehicles(data.vehicles);
}


function makeCell(value) {
    const td = document.createElement("td");
    td.textContent = value ?? "—";
    return td;
}


function formatDeadline(value) {
    if (!value) return "—";

    return new Date(value).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
    });
}


// 1. Emergency Priority Queue
function renderTickets(tickets) {
    const body = document.getElementById("ticketsBody");
    body.replaceChildren();

    tickets.forEach(ticket => {
        const row = document.createElement("tr");

        const values = [
            ticket.ticket_id,
            ticket.requester,
            ticket.people_affected,
            ticket.servings_requested,
            formatDeadline(ticket.deadline),
            ticket.priority_score == null
                ? "Pending"
                : Number(ticket.priority_score).toFixed(2),
            ticket.status
        ];

        values.forEach(value => {
            row.appendChild(makeCell(value));
        });

        body.appendChild(row);
    });

    if (tickets.length === 0) {
        body.appendChild(
            emptyRow(7, "No tickets in this region")
        );
    }
}


// 2. Assigned Deliveries
function renderDeliveries(deliveries) {
    const body = document.getElementById("deliveriesBody");
    body.replaceChildren();

    deliveries.forEach(delivery => {
        const row = document.createElement("tr");

        const values = [
            delivery.delivery_id,
            delivery.ticket_id,
            delivery.supplier,
            delivery.vehicle_id,
            delivery.servings_assigned,
            Number(delivery.route_distance_km ?? 0)
                .toFixed(2) + " km",
            delivery.status
        ];

        values.forEach(value => {
            row.appendChild(makeCell(value));
        });

        // Show route button
        const routeCell = document.createElement("td");
        const button = document.createElement("button");

        button.type = "button";
        button.textContent = "Show Route";

        button.addEventListener("click", () => {
            highlightDeliveryRoute(delivery.route);
        });

        routeCell.appendChild(button);
        row.appendChild(routeCell);
        body.appendChild(row);
    });

    if (deliveries.length === 0) {
        body.appendChild(
            emptyRow(8, "No deliveries assigned")
        );
    }
}


// 3. Supplier Inventory
function renderSuppliers(suppliers) {
    const container =
        document.getElementById("supplierCards");

    container.replaceChildren();

    suppliers.forEach(supplier => {
        const card = document.createElement("div");
        card.className = "resource-card";

        const availableNormal =
            Number(supplier.normal_stock) -
            Number(supplier.reserved_normal);

        const availableCold =
            Number(supplier.cold_stock) -
            Number(supplier.reserved_cold);

        const title = document.createElement("strong");
        title.textContent = supplier.name;

        const details = document.createElement("p");
        details.textContent =
            `Normal: ${availableNormal} | ` +
            `Refrigerated: ${availableCold}`;

        card.append(title, details);
        container.appendChild(card);
    });
}


// 4. Vehicle Fleet

function renderVehicles(vehicles) {
    const container =
        document.getElementById("vehicleCards");

    container.replaceChildren();

    vehicles.forEach(vehicle => {
        const card = document.createElement("div");
        card.className = "resource-card vehicle-card";

        const status = vehicle.status?.toLowerCase();

        // Set card color based on vehicle status
        if (status === "available") {
            card.classList.add("vehicle-available");
        } else if (status === "reserved") {
            card.classList.add("vehicle-reserved");
        } else {
            card.classList.add("vehicle-other");
        }

        const title = document.createElement("strong");
        title.textContent =
            vehicle.name || vehicle.vehicle_id;

        const details = document.createElement("p");
        details.textContent =
            `Status: ${vehicle.status} | ` +
            `Capacity: ${vehicle.capacity} | ` +
            `Refrigerated: ${
                vehicle.refrigerated ? "Yes" : "No"
            }`;

        card.append(title, details);
        container.appendChild(card);
    });
}



// Helper for empty tables
function emptyRow(columns, message) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");

    cell.colSpan = columns;
    cell.textContent = message;
    cell.className = "empty-table";

    row.appendChild(cell);
    return row;
}


function highlightDeliveryRoute(savedRoute) {

    dashboardRouteLayer.clearLayers();

    let nodeIds = savedRoute;

    if (typeof nodeIds === "string") {
        try {
            nodeIds = JSON.parse(nodeIds);
        } catch {
            alert("Invalid saved route");
            return;
        }
    }

    if (!Array.isArray(nodeIds) || !nodeIds.length) {
        alert("No route available");
        return;
    }

    const coordinates = [];

    for (const id of nodeIds) {
        const node = nodeLookup[id];

        if (!node) {
            alert(`Node ${id} not found on current map`);
            return;
        }

        coordinates.push([node.lat, node.lng]);
    }

    const line = L.polyline(coordinates, {
        color: "#16a34a",
        weight: 6,
        opacity: 0.9
    }).addTo(dashboardRouteLayer);

    if (coordinates.length > 1) {
        map.fitBounds(line.getBounds(), {
            padding: [40, 40]
        });
    } else {
        map.setView(coordinates[0], 15);
    }
}


const recalculateBtn =
    document.getElementById("recalculateBtn");

const dispatchBtn =
    document.getElementById("dispatchBtn");


recalculateBtn.addEventListener("click", () => {
    postOperationsAction(
        "/api/priorities/recalculate",
        recalculateBtn,
        "Calculating priorities"
    );
});


dispatchBtn.addEventListener("click", () => {
    postOperationsAction(
        "/api/dispatch",
        dispatchBtn,
        "Dispatching tickets"
    );
});


// Initial page load
loadDatasetOptions().catch(error => {
    console.error("Initialization failed:", error);
    datasetMessage.textContent = error.message;
});

// Initial dashboard load
loadOperationsDashboard().catch(console.error);

// Refresh displayed database values every 5 seconds
setInterval(() => {
    if (activeDataset) {
        loadOperationsDashboard().catch(console.error);
    }
}, 5000);
