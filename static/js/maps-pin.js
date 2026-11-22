// Lets a hotel or NGO drop a map pin when a Google Maps key is configured.
// If this never runs (no key), the typed address alone is enough to register.
function fbInitPinMap() {
  var mapEl = document.getElementById("fb-pin-map");
  if (!mapEl || typeof google === "undefined") {
    return;
  }
  var latInput = document.querySelector('input[name="latitude"]');
  var lngInput = document.querySelector('input[name="longitude"]');
  if (!latInput || !lngInput) {
    return;
  }
  var start = {
    lat: parseFloat(latInput.value) || 12.9716,
    lng: parseFloat(lngInput.value) || 77.5946,
  };
  mapEl.textContent = "";
  var map = new google.maps.Map(mapEl, { center: start, zoom: 12 });
  var hasPin = !!(latInput.value && lngInput.value);
  var marker = new google.maps.Marker({
    position: start,
    map: map,
    draggable: true,
    visible: hasPin,
  });

  function setPosition(latLng) {
    latInput.value = latLng.lat();
    lngInput.value = latLng.lng();
    marker.setPosition(latLng);
    marker.setVisible(true);
  }

  map.addListener("click", function (event) {
    setPosition(event.latLng);
  });
  marker.addListener("dragend", function () {
    setPosition(marker.getPosition());
  });

  var addressInput = document.querySelector('[name="address"]');
  if (addressInput && google.maps.places) {
    var autocomplete = new google.maps.places.Autocomplete(addressInput);
    autocomplete.bindTo("bounds", map);
    autocomplete.addListener("place_changed", function () {
      var place = autocomplete.getPlace();
      if (place.geometry && place.geometry.location) {
        map.setCenter(place.geometry.location);
        map.setZoom(15);
        setPosition(place.geometry.location);
      }
    });
  }
}
