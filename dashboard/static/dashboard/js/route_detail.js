(function () {
  const mapEl = document.getElementById("route-map");
  if (!mapEl) return;

  const map = L.map("route-map").setView([10.4, 76.4], 8);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 13,
  }).addTo(map);

  fetch(`/api/routes/${ROUTE_ID}/`)
    .then((r) => r.json())
    .then((data) => {
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
