// Draws one marker per nearby listing (window.FB_LISTINGS, set by the page).
function fbInitListingsMap() {
  var mapEl = document.getElementById("fb-listings-map");
  if (!mapEl || typeof google === "undefined") {
    return;
  }
  var points = window.FB_LISTINGS || [];
  var center = points.length ? points[0] : { lat: 12.9716, lng: 77.5946 };
  var map = new google.maps.Map(mapEl, { center: center, zoom: 12 });
  var bounds = new google.maps.LatLngBounds();

  points.forEach(function (point) {
    var marker = new google.maps.Marker({ position: { lat: point.lat, lng: point.lng }, map: map, title: point.name });
    // Build the pop-up from DOM nodes (not an HTML string) so a hotel name can never inject markup.
    var box = document.createElement("div");
    var strong = document.createElement("strong");
    strong.textContent = point.name;
    var link = document.createElement("a");
    link.href = point.url;
    link.textContent = "View and request";
    box.appendChild(strong);
    box.appendChild(document.createElement("br"));
    box.appendChild(link);
    var info = new google.maps.InfoWindow({ content: box });
    marker.addListener("click", function () {
      info.open(map, marker);
    });
    bounds.extend(marker.getPosition());
  });

  if (points.length > 1) {
    map.fitBounds(bounds);
  }
}
