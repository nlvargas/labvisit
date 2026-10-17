const box = document.querySelector("[data-panel-map]");

window.initPanelMap = async () => {
  const data = JSON.parse(document.getElementById("map-points").textContent);
  const { Map, Polyline } = await google.maps.importLibrary("maps");
  const { AdvancedMarkerElement, PinElement } = await google.maps.importLibrary("marker");
  const { LatLngBounds } = await google.maps.importLibrary("core");
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#1f6f5c";
  const map = new Map(box, { mapId: box.dataset.mapId, streetViewControl: false, mapTypeControl: false, colorScheme: "LIGHT" });
  const bounds = new LatLngBounds();
  const add = (point, glyph, color, title) => {
    const pin = new PinElement({ glyph, background: color, borderColor: "#ffffff", glyphColor: "#ffffff" });
    new AdvancedMarkerElement({ map, position: point, content: pin.element, title });
    bounds.extend(point);
  };
  if (data.lab) add(data.lab, "L", "#555555", "Laboratorio");
  if (data.route && data.paths && data.paths.length) {
    let index = 0;
    data.paths.forEach((path) => {
      const color = data.paths.length > 1 ? path.color : accent;
      let number = 0;
      path.points.slice(1, -1).forEach((point) => {
        const isLab = data.lab && point.lat === data.lab.lat && point.lng === data.lab.lng;
        if (!isLab) {
          number += 1;
          add(point, String(number), color, data.stops[index]?.title);
          index += 1;
        }
      });
      new Polyline({ map, path: path.points, strokeColor: color, strokeOpacity: 0.85, strokeWeight: 3 });
    });
  } else {
    data.stops.forEach((stop) => add(stop, "", accent, stop.title));
  }
  if (data.stops.length + (data.lab ? 1 : 0) > 1) {
    map.fitBounds(bounds, 40);
  } else {
    map.setCenter(bounds.getCenter());
    map.setZoom(15);
  }
};

if (box?.dataset.key) {
  const params = new URLSearchParams({ key: box.dataset.key, loading: "async", libraries: "marker", language: "es",
                                       region: "CL", callback: "initPanelMap" });
  const script = document.createElement("script");
  script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
  script.async = true;
  document.head.append(script);
}
