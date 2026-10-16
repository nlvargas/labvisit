const mapsConfig = document.querySelector("[data-maps]");

function setupAddressField(field, libs) {
  const input = field.querySelector("input[name=address]");
  const lat = field.querySelector("input[name=latitude]");
  const lng = field.querySelector("input[name=longitude]");
  const placeId = field.querySelector("input[name=address_place_id]");
  const current = field.querySelector("[data-address-current]");
  const currentText = field.querySelector("[data-address-text]");
  const slot = field.querySelector("[data-autocomplete-slot]");
  const mapBox = field.querySelector("[data-address-map]");
  const mapHint = field.querySelector("[data-map-hint]");

  const changed = () => input.dispatchEvent(new Event("change", { bubbles: true }));

  input.addEventListener("input", () => {
    lat.value = "";
    lng.value = "";
    placeId.value = "";
  });

  if (!libs) return;
  const { places, maps, marker } = libs;

  const labLat = Number(mapsConfig.dataset.labLat);
  const labLng = Number(mapsConfig.dataset.labLng);
  const options = { includedRegionCodes: ["cl"] };
  if (labLat && labLng) {
    options.locationBias = { center: { lat: labLat, lng: labLng }, radius: 30000 };
  }
  const autocomplete = new places.PlaceAutocompleteElement(options);
  autocomplete.style.colorScheme = "light";
  autocomplete.id = `${input.id}-autocomplete`;
  slot.append(autocomplete);
  input.hidden = true;

  let map = null;
  let pin = null;
  const showMap = (position) => {
    mapBox.hidden = false;
    mapHint.hidden = false;
    if (!map) {
      map = new maps.Map(mapBox, {
        center: position,
        zoom: 17,
        mapId: mapsConfig.dataset.mapId || "DEMO_MAP_ID",
        disableDefaultUI: true,
        zoomControl: true,
        gestureHandling: "cooperative",
      });
      pin = new marker.AdvancedMarkerElement({ map, position, gmpDraggable: true });
      pin.addListener("dragend", () => {
        const moved = pin.position;
        lat.value = typeof moved.lat === "function" ? moved.lat() : moved.lat;
        lng.value = typeof moved.lng === "function" ? moved.lng() : moved.lng;
        changed();
      });
    } else {
      map.setCenter(position);
      pin.position = position;
    }
  };

  const showCurrent = (text) => {
    currentText.textContent = text;
    current.hidden = !text;
    slot.hidden = Boolean(text);
  };
  showCurrent(input.value);
  if (input.value && lat.value && lng.value) {
    showMap({ lat: Number(lat.value), lng: Number(lng.value) });
  }

  field.querySelector("[data-address-change]").addEventListener("click", () => showCurrent(""));

  autocomplete.addEventListener("gmp-select", async ({ placePrediction }) => {
    const place = placePrediction.toPlace();
    await place.fetchFields({ fields: ["formattedAddress", "location"] });
    input.value = place.formattedAddress;
    lat.value = place.location.lat();
    lng.value = place.location.lng();
    placeId.value = place.id;
    showCurrent(place.formattedAddress);
    showMap({ lat: place.location.lat(), lng: place.location.lng() });
    changed();
  });
}

window.initAddressFields = async () => {
  try {
    const [places, maps, marker] = await Promise.all([
      google.maps.importLibrary("places"),
      google.maps.importLibrary("maps"),
      google.maps.importLibrary("marker"),
    ]);
    document.querySelectorAll("[data-address-field]").forEach((field) => setupAddressField(field, { places, maps, marker }));
  } catch (error) {
    console.error("Google Maps could not load", error);
  }
};

document.querySelectorAll("[data-address-field]").forEach((field) => setupAddressField(field, null));

if (mapsConfig?.dataset.key && document.querySelector("[data-address-field]")) {
  const params = new URLSearchParams({
    key: mapsConfig.dataset.key,
    loading: "async",
    libraries: "places,marker",
    language: "es",
    region: "CL",
    callback: "initAddressFields",
  });
  const script = document.createElement("script");
  script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
  script.async = true;
  document.head.append(script);
}
