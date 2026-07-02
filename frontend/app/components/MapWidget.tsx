import { MapContainer, TileLayer, Marker, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";

// Fix ikony leafleta z Next.js
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function MapPicker({ lat, lng, onChange }: { lat: number; lng: number; onChange: (l: { lat: number; lng: number }) => void }) {
  useMapEvents({
    click(e) {
      onChange({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
  });
  return <Marker position={[lat, lng]} />;
}

export default function MapWidget({ lat, lng, onChange }: { lat: number; lng: number; onChange: (l: { lat: number; lng: number }) => void }) {
  useEffect(() => {
    window.dispatchEvent(new Event("resize"));
  }, []);

  return (
    <div className="h-[120px] w-full overflow-hidden rounded-lg bg-zinc-900 light:bg-zinc-100">
      <MapContainer center={[lat, lng]} zoom={11} style={{ height: "100%", width: "100%", zIndex: 1 }}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <MapPicker lat={lat} lng={lng} onChange={onChange} />
      </MapContainer>
    </div>
  );
}
