let map;
let cluster;
let sites = [];
let markersByCode = new Map();
let currentGoogleUrl = "";

const searchInput = document.getElementById("searchInput");
const searchResults = document.getElementById("searchResults");
const clearBtn = document.getElementById("clearBtn");
const detailPanel = document.getElementById("detailPanel");
const loading = document.getElementById("loading");

const redIcon = L.divIcon({
    className: "",
    html: '<div class="site-pin"></div>',
    iconSize: [18, 18],
    iconAnchor: [9, 18],
    popupAnchor: [0, -18]
});

function initMap() {
    map = L.map("map", {
        zoomControl: false,
        preferCanvas: true
    }).setView([13.7563, 100.5018], 7);

    L.control.zoom({
        position: "bottomright"
    }).addTo(map);

    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }
    ).addTo(map);

    cluster = L.markerClusterGroup({
        chunkedLoading: true,
        chunkInterval: 100,
        chunkDelay: 20,
        maxClusterRadius: 55,
        disableClusteringAtZoom: 15,
        showCoverageOnHover: false
    });

    map.addLayer(cluster);
}

function popupHtml(site) {
    return `
        <div style="min-width:190px">
            <b>${escapeHtml(site.site_code)}</b><br>
            <span>${escapeHtml(site.name)}</span><br>
            <small>${escapeHtml(site.amphur)} ${escapeHtml(site.province)}</small>
        </div>
    `;
}

function createMarker(site) {
    const marker = L.marker([site.lat, site.lon], {
        icon: redIcon,
        title: site.site_code
    });

    marker.bindPopup(popupHtml(site));

    marker.on("click", () => {
        showDetail(site);
    });

    markersByCode.set(site.site_code, marker);
    return marker;
}

async function loadSites() {
    try {
        const response = await fetch("/api/sites");
        sites = await response.json();

        const markers = [];
        for (const site of sites) {
            markers.push(createMarker(site));
        }

        cluster.addLayers(markers);

        loading.style.display = "none";
    } catch (error) {
        loading.innerHTML = "ไม่สามารถโหลดข้อมูล Site Base ได้";
        console.error(error);
    }
}

function showDetail(site) {
    document.getElementById("detailCode").textContent = site.site_code;
    document.getElementById("detailName").textContent = site.name || "-";
    document.getElementById("detailTumbol").textContent = site.tumbol || "-";
    document.getElementById("detailAmphur").textContent = site.amphur || "-";
    document.getElementById("detailProvince").textContent = site.province || "-";
    document.getElementById("detailLat").textContent = site.lat.toFixed(6);
    document.getElementById("detailLon").textContent = site.lon.toFixed(6);

    currentGoogleUrl =
        `https://www.google.com/maps?q=${site.lat},${site.lon}`;

    detailPanel.style.display = "block";
}

function goToSite(site) {
    const marker = markersByCode.get(site.site_code);

    map.flyTo([site.lat, site.lon], 17, {
        duration: 1.2
    });

    setTimeout(() => {
        if (marker) {
            cluster.zoomToShowLayer(marker, () => {
                marker.openPopup();
                showDetail(site);
            });
        }
    }, 700);

    searchResults.style.display = "none";
}

function renderResults(results) {
    searchResults.innerHTML = "";

    if (!results.length) {
        searchResults.innerHTML =
            `<div class="result"><div class="result-name">ไม่พบ Site ที่ค้นหา</div></div>`;
        searchResults.style.display = "block";
        return;
    }

    for (const site of results) {
        const div = document.createElement("div");
        div.className = "result";

        div.innerHTML = `
            <div class="result-code">${escapeHtml(site.site_code)}</div>
            <div class="result-name">${escapeHtml(site.name || "-")}</div>
            <div class="result-location">
                ${escapeHtml(site.amphur || "-")} · ${escapeHtml(site.province || "-")}
            </div>
        `;

        div.addEventListener("click", () => goToSite(site));
        searchResults.appendChild(div);
    }

    searchResults.style.display = "block";
}

let searchTimer = null;

async function searchSites() {
    const q = searchInput.value.trim();

    clearBtn.style.display = q ? "block" : "none";

    if (!q) {
        searchResults.style.display = "none";
        return;
    }

    clearTimeout(searchTimer);

    searchTimer = setTimeout(async () => {
        const response = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const results = await response.json();
        renderResults(results);
    }, 180);
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

searchInput.addEventListener("input", searchSites);

clearBtn.addEventListener("click", () => {
    searchInput.value = "";
    clearBtn.style.display = "none";
    searchResults.style.display = "none";
    searchInput.focus();
});

document.getElementById("closeDetail").addEventListener("click", () => {
    detailPanel.style.display = "none";
});

document.getElementById("googleBtn").addEventListener("click", () => {
    if (currentGoogleUrl) {
        window.open(currentGoogleUrl, "_blank");
    }
});

document.getElementById("locateBtn").addEventListener("click", () => {
    if (!navigator.geolocation) {
        alert("เบราว์เซอร์ไม่รองรับการระบุตำแหน่ง");
        return;
    }

    navigator.geolocation.getCurrentPosition(
        position => {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;

            map.flyTo([lat, lon], 16, {
                duration: 1.2
            });

            L.circleMarker([lat, lon], {
                radius: 8,
                color: "#1677d2",
                fillColor: "#1677d2",
                fillOpacity: 0.85
            })
            .addTo(map)
            .bindPopup("ตำแหน่งของคุณ")
            .openPopup();
        },
        () => alert("ไม่สามารถเข้าถึงตำแหน่งของคุณได้")
    );
});

document.addEventListener("click", event => {
    if (!event.target.closest(".control-panel")) {
        searchResults.style.display = "none";
    }
});

initMap();
loadSites();
