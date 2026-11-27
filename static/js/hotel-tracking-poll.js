// Hotel Dashboard AJAX Polling for Live Incoming Recipient GPS
(function () {
  "use strict";

  var maps = {};
  var markers = {};
  var pollInterval = null;

  window.fbInitHotelTrackingMaps = function () {
    // Maps API loaded callback
    pollAllActive();
  };

  function updateCard(box, data) {
    if (!data.active) {
      box.style.display = "none";
      return;
    }
    box.style.display = "block";

    var badge = box.querySelector(".trk-status-badge");
    var distEta = box.querySelector(".trk-dist-eta");
    var lastUp = box.querySelector(".trk-last-update");

    if (badge) {
      badge.textContent = data.status_display || "Active";
      badge.className = data.is_stale ? "badge bg-warning text-dark me-2 trk-status-badge" : "badge bg-success me-2 trk-status-badge";
    }
    if (distEta && data.distance_meters !== null) {
      var d = data.distance_meters > 1000 ? (data.distance_meters / 1000).toFixed(1) + " km" : data.distance_meters + " m";
      distEta.textContent = d + " away";
    }
    if (lastUp) {
      lastUp.textContent = "Updated " + data.last_updated_human + (data.is_stale ? " (stale)" : "");
    }

    // Update map marker if Google Maps is loaded
    var reqId = box.getAttribute("data-request-id");
    var mapEl = document.getElementById("hotel-map-" + reqId);
    if (mapEl && typeof google !== "undefined" && data.latitude && data.longitude) {
      var pos = new google.maps.LatLng(data.latitude, data.longitude);
      if (!maps[reqId]) {
        maps[reqId] = new google.maps.Map(mapEl, {
          center: pos,
          zoom: 14,
          gestureHandling: "cooperative"
        });
        markers[reqId] = new google.maps.Marker({
          position: pos,
          map: maps[reqId],
          title: data.recipient_name,
          icon: "https://maps.google.com/mapfiles/ms/icons/blue-dot.png"
        });
      } else {
        markers[reqId].setPosition(pos);
        maps[reqId].panTo(pos);
      }
    }
  }

  function pollSingle(box) {
    var reqId = box.getAttribute("data-request-id");
    var url = "/api/requests/" + reqId + "/tracking/status/";

    window.fbFetch(url).then(function (data) {
      updateCard(box, data);
    }).catch(function (e) {
      console.warn("Tracking poll error for req " + reqId, e);
    });
  }

  function pollAllActive() {
    if (document.hidden) return; // Pause polling when tab is hidden to save battery & data
    var boxes = document.querySelectorAll(".hotel-live-tracking-box");
    boxes.forEach(pollSingle);
  }

  document.addEventListener("DOMContentLoaded", function () {
    pollAllActive();
    pollInterval = setInterval(pollAllActive, 6000);
  });

  window.addEventListener("beforeunload", function () {
    if (pollInterval) clearInterval(pollInterval);
  });
})();
