// Directions & Live GPS Tracking Client Module
(function () {
  "use strict";

  var data = window.FB_PICKUP_DATA || {};
  var map, directionsService, directionsRenderer;
  var userMarker, hotelMarker;
  var watchId = null;
  var wakeLock = null;
  var lastLat = null, lastLng = null;

  var banner = document.getElementById("fb-privacy-banner");
  var startBtn = document.getElementById("btn-start-journey");
  var stopBtn = document.getElementById("btn-stop-sharing");
  var getDirectionsBtn = document.getElementById("btn-get-directions");
  var statusBox = document.getElementById("gps-status-box");
  var statusLabel = document.getElementById("gps-status-label");
  var lastUpdateLabel = document.getElementById("gps-last-update");
  var statsBadge = document.getElementById("route-stats");

  // ---- Initialize Directions Map --------------------------------------------
  window.fbInitDirectionsMap = function () {
    var mapEl = document.getElementById("directions-map");
    if (!mapEl || typeof google === "undefined") return;

    var hotelPos = {
      lat: data.hotelLat || 12.9716,
      lng: data.hotelLng || 77.5946
    };

    map = new google.maps.Map(mapEl, {
      center: hotelPos,
      zoom: 13,
      gestureHandling: "cooperative"
    });

    directionsService = new google.maps.DirectionsService();
    directionsRenderer = new google.maps.DirectionsRenderer({
      map: map,
      suppressMarkers: false
    });

    hotelMarker = new google.maps.Marker({
      position: hotelPos,
      map: map,
      title: data.hotelName,
      icon: "https://maps.google.com/mapfiles/ms/icons/red-dot.png"
    });

    if (data.hasActiveSession) {
      startWatching();
    }
  };

  // ---- Fallback Route Calculation -------------------------------------------
  function calculateRoute(origin) {
    if (!directionsService || !directionsRenderer || !data.hotelLat || !data.hotelLng) {
      if (statsBadge) statsBadge.textContent = "External Maps link ready";
      return;
    }

    var dest = new google.maps.LatLng(data.hotelLat, data.hotelLng);
    directionsService.route(
      {
        origin: origin,
        destination: dest,
        travelMode: google.maps.TravelMode.DRIVING
      },
      function (result, status) {
        if (status === google.maps.DirectionsStatus.OK) {
          directionsRenderer.setDirections(result);
          var leg = result.routes[0].legs[0];
          if (statsBadge) {
            statsBadge.textContent = leg.distance.text + " · " + leg.duration.text + " drive";
          }
        } else {
          if (statsBadge) statsBadge.textContent = "Route unavailable";
        }
      }
    );
  }

  // ---- Geolocation & Live Journey -------------------------------------------
  function requestWakeLock() {
    if ("wakeLock" in navigator && !wakeLock) {
      navigator.wakeLock.request("screen").then(function (lock) {
        wakeLock = lock;
      }).catch(function (e) {
        console.warn("Screen Wake Lock error:", e);
      });
    }
  }

  function releaseWakeLock() {
    if (wakeLock) {
      wakeLock.release().then(function () { wakeLock = null; });
    }
  }

  function sendLocation(lat, lng, accuracy) {
    // Skip tiny movement (<10m) to save bandwidth
    if (lastLat && lastLng) {
      var d = Math.hypot(lat - lastLat, lng - lastLng);
      if (d < 0.0001) return;
    }
    lastLat = lat;
    lastLng = lng;

    window.fbFetch(data.updateLocationUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ latitude: lat, longitude: lng, accuracy: accuracy })
    }).then(function (res) {
      if (statusBox) statusBox.style.display = "block";
      if (statusLabel) {
        statusLabel.className = "badge bg-success";
        statusLabel.textContent = "Live Sharing";
      }
      if (lastUpdateLabel) {
        lastUpdateLabel.textContent = new Date().toLocaleTimeString();
      }
    }).catch(function (err) {
      if (statusLabel) {
        statusLabel.className = "badge bg-warning text-dark";
        statusLabel.textContent = "Retrying...";
      }
      console.warn("Location push error:", err);
    });
  }

  function startWatching() {
    if (!navigator.geolocation) {
      alert("Geolocation is not supported by your browser.");
      return;
    }
    requestWakeLock();
    if (banner) banner.style.display = "flex";
    if (startBtn) startBtn.disabled = true;

    watchId = navigator.geolocation.watchPosition(
      function (pos) {
        var lat = pos.coords.latitude;
        var lng = pos.coords.longitude;
        var userLatLng = new google.maps.LatLng(lat, lng);

        if (!userMarker && map) {
          userMarker = new google.maps.Marker({
            position: userLatLng,
            map: map,
            title: "Your location",
            icon: "https://maps.google.com/mapfiles/ms/icons/blue-dot.png"
          });
        } else if (userMarker) {
          userMarker.setPosition(userLatLng);
        }

        calculateRoute(userLatLng);
        sendLocation(lat, lng, pos.coords.accuracy);
      },
      function (err) {
        console.warn("Geolocation watch error:", err);
        if (statusLabel) {
          statusLabel.className = "badge bg-danger";
          statusLabel.textContent = "GPS Unavailable";
        }
      },
      {
        enableHighAccuracy: true,
        maximumAge: 10000,
        timeout: 10000
      }
    );
  }

  function stopWatching() {
    if (watchId !== null) {
      navigator.geolocation.clearWatch(watchId);
      watchId = null;
    }
    releaseWakeLock();
    if (banner) banner.style.display = "none";
    if (startBtn) startBtn.disabled = false;
    if (statusBox) statusBox.style.display = "none";

    window.fbFetch(data.stopTrackingUrl, {
      method: "POST"
    }).then(function () {
      alert("Live location sharing stopped.");
    }).catch(function (err) {
      console.warn("Stop error:", err);
    });
  }

  // Visibility change handling
  document.addEventListener("visibilitychange", function () {
    if (document.hidden && watchId !== null) {
      if (statusLabel) {
        statusLabel.className = "badge bg-warning text-dark";
        statusLabel.textContent = "Location update delayed (backgrounded)";
      }
    }
  });

  // Buttons
  if (startBtn) {
    startBtn.addEventListener("click", function () {
      window.fbFetch(data.startTrackingUrl, { method: "POST" })
        .then(function () {
          startWatching();
        })
        .catch(function (err) {
          alert("Could not start tracking: " + err.message);
        });
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener("click", stopWatching);
  }

  if (getDirectionsBtn) {
    getDirectionsBtn.addEventListener("click", function () {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition(function (pos) {
        var userLatLng = new google.maps.LatLng(pos.coords.latitude, pos.coords.longitude);
        calculateRoute(userLatLng);
      });
    });
  }
})();
