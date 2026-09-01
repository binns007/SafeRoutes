(function () {
  const mapEl = document.getElementById("route-map");
  if (!mapEl) return;

  const map = L.map("route-map").setView([10.4, 76.4], 8);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 13,
  }).addTo(map);

  function worstAlert(alerts) {
    const unseen = alerts.filter((a) => !a.acknowledged);
    if (!unseen.length) return null;
    const critical = unseen.find((a) => a.severity === "critical");
    return critical || unseen[0];
  }

  function maybeShowAlertPopup(data) {
    const alert = worstAlert(data.alerts || []);
    if (!alert) return;

    const extraCount = data.alerts.filter((a) => !a.acknowledged).length - 1;
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

  fetch(`/api/routes/${ROUTE_ID}/`)
    .then((r) => r.json())
    .then((data) => {
      maybeShowAlertPopup(data);
      const bounds = [];

      // planned path
      const planned = data.waypoints.map((wp) => [wp[0], wp[1]]);
      L.polyline(planned, { color: "#1E2A4A", weight: 3, dashArray: "6 6" }).addTo(map);
      planned.forEach((p) => bounds.push(p));

      // start / end markers
      L.marker(planned[0]).addTo(map).bindPopup(`<strong>${data.source}</strong> (start)`);
      L.marker(planned[planned.length - 1]).addTo(map).bindPopup(`<strong>${data.destination}</strong> (end)`);

      // actual GPS pings
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
    });
})();