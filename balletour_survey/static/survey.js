const BALLERUD_CENTER = [59.9148, 10.5886];
const map = L.map("map").setView(BALLERUD_CENTER, 17);

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 21,
    attribution: "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
}).addTo(map);

const gpsStatus = document.querySelector("#gpsStatus");
const accuracyStatus = document.querySelector("#accuracyStatus");
const gpsIndicator = document.querySelector("#gpsIndicator");
const gpsPermission = document.querySelector("#gpsPermission");
const gpsCoordinates = document.querySelector("#gpsCoordinates");
const gpsAltitude = document.querySelector("#gpsAltitude");
const gpsSpeed = document.querySelector("#gpsSpeed");
const gpsHeading = document.querySelector("#gpsHeading");
const gpsTimestamp = document.querySelector("#gpsTimestamp");
const gpsSatellites = document.querySelector("#gpsSatellites");
const locateButton = document.querySelector("#locateButton");
const sampleButton = document.querySelector("#sampleButton");
const clearDraftButton = document.querySelector("#clearDraftButton");
const saveButton = document.querySelector("#saveButton");
const draftStatus = document.querySelector("#draftStatus");
const featureForm = document.querySelector("#featureForm");
const featureList = document.querySelector("#featureList");
const geometryInput = document.querySelector("#geometryInput");
const featuresUrl = document.body.dataset.featuresUrl || "/api/features";

let watchId = null;
let currentPosition = null;
let currentMarker = null;
let accuracyCircle = null;
let draftPositions = [];
let draftLayer = null;
let savedLayer = L.geoJSON(null, {
    pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
        radius: 8,
        color: "#116149",
        weight: 3,
        fillColor: "#31b985",
        fillOpacity: 0.85,
    }),
    style: {
        color: "#116149",
        weight: 4,
        fillColor: "#31b985",
        fillOpacity: 0.22,
    },
    onEachFeature: (feature, layer) => {
        const props = feature.properties || {};
        layer.bindPopup(`<strong>${escapeHtml(props.name || "Måling")}</strong><br>${escapeHtml(props.feature_type || "")}`);
    },
}).addTo(map);

locateButton.addEventListener("click", startGps);
sampleButton.addEventListener("click", addDraftPoint);
clearDraftButton.addEventListener("click", clearDraft);
geometryInput.addEventListener("change", refreshDraft);
featureForm.addEventListener("submit", saveDraft);

setGpsState("off", "GPS av", "Trykk Start GPS");
refreshPermissionStatus();
loadFeatures();

function startGps() {
    if (!window.isSecureContext) {
        setGpsState("blocked", "GPS blokkert", "GPS krever HTTPS");
        gpsStatus.textContent = "GPS krever HTTPS. Åpne https://survey.shanklife.no";
        return;
    }
    if (!navigator.geolocation) {
        setGpsState("blocked", "GPS mangler", "Nettleseren støtter ikke GPS");
        gpsStatus.textContent = "GPS støttes ikke i denne nettleseren";
        return;
    }
    if (watchId !== null) {
        navigator.geolocation.clearWatch(watchId);
    }
    setGpsState("starting", "GPS starter", "Venter på posisjon");
    gpsStatus.textContent = "Starter GPS...";
    watchId = navigator.geolocation.watchPosition(handlePosition, handleGpsError, {
        enableHighAccuracy: true,
        maximumAge: 1000,
        timeout: 15000,
    });
}

function handlePosition(position) {
    currentPosition = position;
    const latlng = [position.coords.latitude, position.coords.longitude];
    const accuracy = Math.round(position.coords.accuracy * 10) / 10;
    setGpsState("on", "GPS på", `+-${accuracy} m`);
    gpsStatus.textContent = "GPS aktiv";
    accuracyStatus.textContent = `+-${accuracy} m`;
    updateGpsDetails(position);
    sampleButton.disabled = false;

    if (!currentMarker) {
        currentMarker = L.marker(latlng).addTo(map);
        map.setView(latlng, 18);
    } else {
        currentMarker.setLatLng(latlng);
    }

    if (!accuracyCircle) {
        accuracyCircle = L.circle(latlng, {
            radius: accuracy,
            color: "#2d6cdf",
            weight: 1,
            fillColor: "#2d6cdf",
            fillOpacity: 0.12,
        }).addTo(map);
    } else {
        accuracyCircle.setLatLng(latlng);
        accuracyCircle.setRadius(accuracy);
    }
}

function handleGpsError(error) {
    if (error.code === error.PERMISSION_DENIED) {
        setGpsState("blocked", "GPS blokkert", "Posisjon er ikke tillatt");
        gpsStatus.textContent = "Posisjon er blokkert. Åpne siden i Safari/Chrome og tillat posisjon for survey.shanklife.no.";
    } else {
        setGpsState("blocked", "GPS-feil", error.message || "Kunne ikke hente GPS");
        gpsStatus.textContent = error.message || "Kunne ikke hente GPS";
    }
    sampleButton.disabled = true;
    refreshPermissionStatus();
}

function setGpsState(state, label, detail) {
    gpsIndicator.dataset.state = state;
    gpsIndicator.textContent = label;
    accuracyStatus.textContent = detail;
}

async function refreshPermissionStatus() {
    if (!navigator.permissions || !navigator.permissions.query) {
        gpsPermission.textContent = "Ukjent";
        return;
    }
    try {
        const status = await navigator.permissions.query({ name: "geolocation" });
        gpsPermission.textContent = permissionLabel(status.state);
        status.onchange = () => {
            gpsPermission.textContent = permissionLabel(status.state);
        };
    } catch (error) {
        gpsPermission.textContent = "Ukjent";
    }
}

function permissionLabel(state) {
    if (state === "granted") return "Tillatt";
    if (state === "prompt") return "Spør ved bruk";
    if (state === "denied") return "Blokkert";
    return "Ukjent";
}

function updateGpsDetails(position) {
    const coords = position.coords;
    gpsCoordinates.textContent = `${coords.latitude.toFixed(6)}, ${coords.longitude.toFixed(6)}`;
    gpsAltitude.textContent = coords.altitude === null ? "Ikke tilgjengelig" : `${Math.round(coords.altitude * 10) / 10} m`;
    gpsSpeed.textContent = coords.speed === null ? "Ikke tilgjengelig" : `${Math.round(coords.speed * 3.6 * 10) / 10} km/t`;
    gpsHeading.textContent = coords.heading === null ? "Ikke tilgjengelig" : `${Math.round(coords.heading)} grader`;
    gpsTimestamp.textContent = new Date(position.timestamp).toLocaleTimeString("no-NO", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
    gpsSatellites.textContent = "Ikke tilgjengelig i nettleser";
}

function addDraftPoint() {
    if (!currentPosition) {
        return;
    }
    draftPositions.push([
        currentPosition.coords.longitude,
        currentPosition.coords.latitude,
    ]);
    refreshDraft();
}

function refreshDraft() {
    if (draftLayer) {
        map.removeLayer(draftLayer);
        draftLayer = null;
    }

    const geometry = buildGeometry();
    saveButton.disabled = !geometry;
    draftStatus.textContent = `${draftPositions.length} kladdpunkt${draftPositions.length === 1 ? "" : "er"}`;

    if (!geometry) {
        return;
    }

    draftLayer = L.geoJSON({ type: "Feature", geometry }, {
        pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
            radius: 9,
            color: "#a6422a",
            weight: 3,
            fillColor: "#df765e",
            fillOpacity: 0.9,
        }),
        style: {
            color: "#a6422a",
            weight: 4,
            fillColor: "#df765e",
            fillOpacity: 0.2,
        },
    }).addTo(map);
}

function buildGeometry() {
    const type = geometryInput.value;
    if (type === "Point") {
        if (draftPositions.length < 1) return null;
        return { type, coordinates: draftPositions[draftPositions.length - 1] };
    }
    if (type === "LineString") {
        if (draftPositions.length < 2) return null;
        return { type, coordinates: draftPositions };
    }
    if (type === "Polygon") {
        if (draftPositions.length < 3) return null;
        const ring = [...draftPositions, draftPositions[0]];
        return { type, coordinates: [ring] };
    }
    return null;
}

function clearDraft() {
    draftPositions = [];
    refreshDraft();
}

async function saveDraft(event) {
    event.preventDefault();
    const geometry = buildGeometry();
    if (!geometry) {
        return;
    }
    const formData = new FormData(featureForm);
    const payload = {
        name: formData.get("name"),
        feature_type: formData.get("feature_type"),
        hole_number: formData.get("hole_number"),
        geometry,
        accuracy_m: currentPosition ? currentPosition.coords.accuracy : null,
        notes: formData.get("notes"),
    };

    saveButton.disabled = true;
    const response = await fetch(featuresUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        alert(data.error || "Kunne ikke lagre målingen.");
        saveButton.disabled = false;
        return;
    }
    clearDraft();
    featureForm.reset();
    geometryInput.value = "Point";
    await loadFeatures();
}

async function loadFeatures() {
    const response = await fetch(featuresUrl);
    const data = await response.json();
    const features = data.features || [];
    savedLayer.clearLayers();
    savedLayer.addData(features);
    renderFeatureList(features);
}

function renderFeatureList(features) {
    if (!features.length) {
        featureList.innerHTML = '<p class="muted">Ingen målinger lagret ennå.</p>';
        return;
    }
    featureList.innerHTML = features.map((feature) => {
        const props = feature.properties || {};
        const hole = props.hole_number ? `Hull ${props.hole_number}` : "Uten hull";
        const accuracy = props.accuracy_m ? `+-${props.accuracy_m} m` : "ukjent nøyaktighet";
        return `
            <article class="feature-item">
                <div class="feature-title">
                    <span>${escapeHtml(props.name || "Måling")}</span>
                    <button class="danger" type="button" data-delete-id="${feature.id}">Slett</button>
                </div>
                <div class="feature-meta">${escapeHtml(props.feature_type || "")} · ${hole} · ${feature.geometry.type} · ${accuracy}</div>
            </article>
        `;
    }).join("");

    featureList.querySelectorAll("[data-delete-id]").forEach((button) => {
        button.addEventListener("click", async () => {
            const id = button.getAttribute("data-delete-id");
            await fetch(`${featuresUrl}/${id}`, { method: "DELETE" });
            await loadFeatures();
        });
    });
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
