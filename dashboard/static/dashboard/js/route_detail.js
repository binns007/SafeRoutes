(function () {
  const mapEl = document.getElementById("route-map");
  if (!mapEl) return;

  const map = L.map("route-map").setView([10.4, 76.4], 8);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 13,
  }).addTo(map);

  const liveBtn = document.getElementById("live-track-btn");
  const liveStatus = document.getElementById("live-track-status");
  let liveMarker = null;
  let liveWatchId = null;
  let lastPingAt = 0;
  const MIN_PING_INTERVAL_MS = 4000; // don't hammer the server on jittery GPS updates

  function getCsrfToken() {
    const input = document.querySelector("#sr-csrf-form input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function worstAlert(alerts) {
    const unseen = alerts.filter((a) => !a.acknowledged);
    if (!unseen.length) return null;
    const critical = unseen.find((a) => a.severity === "critical");
    return critical || unseen[0];
  }

  function showAlertPopup(alert, extraCount) {
    window.SafeRoutesAlertModal.show({
      severity: alert.severity,
      title: alert.severity === "critical" ? "You're in a high-risk zone" : "Route deviation detected",
      message: alert.message,
      subtext: extraCount > 0
        ? `+ ${extraCount} more alert${extraCount === 1 ? "" : "s"} on this journey.`
        : "This alert is shown to you only. SafeRoutes does not contact anyone on your behalf.",
      onReroute: () => {
        window.SafeRoutesAlertModal.postAction(`/api/routes/${ROUTE_ID}/reroute/`)
          .then(() => window.location.reload());
      },
      onContinue: () => {
        window.SafeRoutesAlertModal.postAction(`/api/routes/${ROUTE_ID}/acknowledge/`, "continued")
          .then(() => window.location.reload());
      },
      onDismiss: () => {
        window.SafeRoutesAlertModal.postAction(`/api/routes/${ROUTE_ID}/acknowledge/`, "dismissed")
          .then(() => window.location.reload());
      },
    });
  }

  function maybeShowAlertPopup(data) {
    const alert = worstAlert(data.alerts || []);
    if (!alert) return;
    const extraCount = data.alerts.filter((a) => !a.acknowledged).length - 1;
    showAlertPopup(alert, extraCount);
  }

  function renderStaticRoute(data) {
    const bounds = [];

    // planned path
    const planned = data.waypoints.map((wp) => [wp[0], wp[1]]);
    L.polyline(planned, { color: "#1E2A4A", weight: 3, dashArray: "6 6" }).addTo(map);
    planned.forEach((p) => bounds.push(p));

    // start / end markers
    L.marker(planned[0]).addTo(map).bindPopup(`<strong>${data.source}</strong> (start)`);
    L.marker(planned[planned.length - 1]).addTo(map).bindPopup(`<strong>${data.destination}</strong> (end)`);

    // actual GPS pings (simulated and/or live, whichever have been recorded)
    const actualPath = [];
    data.pings.forEach((p) => {
      actualPath.push([p.lat, p.lon]);
      const color = p.in_unsafe_zone ? "#E8546B" : "#35C4A1";
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: p.in_unsafe_zone ? 9 : 5,
        color,
        fillColor: color,
        fillOpacity: 0.8,
        weight: p.in_unsafe_zone ? 3 : 1,
      }).addTo(map);
      marker.bindPopup(`
        Ping #${p.sequence}<br/>
        Nearest: ${p.nearest_district ?? "-"}<br/>
        Safety score: ${p.safety_score ? p.safety_score.toFixed(1) : "-"}<br/>
        ${p.in_unsafe_zone ? "<strong style='color:#E8546B'>Deviation into unsafe zone</strong>" : "On safe path"}
      `);
      bounds.push([p.lat, p.lon]);
    });

    if (actualPath.length) {
      L.polyline(actualPath, { color: "#F2A65A", weight: 3 }).addTo(map);
    }

    if (bounds.length) map.fitBounds(bounds, { padding: [30, 30] });
  }

  // ---------- live location tracking (navigator.geolocation) ----------

  function sendLivePing(lat, lon) {
    return fetch(`/api/routes/${ROUTE_ID}/live-ping/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ lat, lon }),
    }).then((r) => r.json());
  }

  function updateLiveMarker(lat, lon, inUnsafeZone) {
    const color = inUnsafeZone ? "#E8546B" : "#35C4A1";
    if (!liveMarker) {
      liveMarker = L.circleMarker([lat, lon], {
        radius: 10,
        color: "#fff",
        weight: 2,
        fillColor: color,
        fillOpacity: 0.95,
      }).addTo(map);
      liveMarker.bindPopup("Your live location");
    } else {
      liveMarker.setLatLng([lat, lon]);
      liveMarker.setStyle({ fillColor: color });
    }
    map.panTo([lat, lon]);
  }

  function handlePosition(position) {
    const { latitude, longitude } = position.coords;
    updateLiveMarker(latitude, longitude, false);

    const now = Date.now();
    if (now - lastPingAt < MIN_PING_INTERVAL_MS) return;
    lastPingAt = now;

    sendLivePing(latitude, longitude).then((data) => {
      if (!data || data.error) return;
      updateLiveMarker(latitude, longitude, data.ping.in_unsafe_zone);
      if (data.alert) showAlertPopup(data.alert, 0);
    });
  }

  function handlePositionError(err) {
    if (liveStatus) liveStatus.textContent = "Couldn't get your location: " + err.message;
    stopLiveTracking();
  }

  function startLiveTracking() {
    if (!("geolocation" in navigator)) {
      if (liveStatus) liveStatus.textContent = "Geolocation isn't supported on this device.";
      return;
    }
    liveWatchId = navigator.geolocation.watchPosition(handlePosition, handlePositionError, {
      enableHighAccuracy: true,
      maximumAge: 5000,
      timeout: 15000,
    });
    if (liveBtn) {
      liveBtn.textContent = "Stop live tracking";
      liveBtn.classList.add("btn-ghost");
    }
    if (liveStatus) {
      liveStatus.textContent = "Live tracking on \u2014 your location stays on this device and this route only.";
    }
  }

  function stopLiveTracking() {
    if (liveWatchId !== null) {
      navigator.geolocation.clearWatch(liveWatchId);
      liveWatchId = null;
    }
    if (liveBtn) {
      liveBtn.textContent = "Track my live location";
      liveBtn.classList.remove("btn-ghost");
    }
  }

  if (liveBtn) {
    liveBtn.addEventListener("click", () => {
      if (liveWatchId !== null) {
        stopLiveTracking();
        if (liveStatus) liveStatus.textContent = "Live tracking stopped.";
      } else {
        startLiveTracking();
      }
    });
  }

  fetch(`/api/routes/${ROUTE_ID}/`)
    .then((r) => r.json())
    .then((data) => {
      maybeShowAlertPopup(data);
      renderStaticRoute(data);
    });
})();
