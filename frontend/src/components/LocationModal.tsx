import { useEffect, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { api } from "../api";
import { copy } from "../copy.fa";
import type { GeoSuggestion, SlotLocation } from "../types";
import { Sheet } from "./ui";

function PickPoint({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: ({ latlng }) => onPick(latlng.lat, latlng.lng) });
  return null;
}

function ResizeMap() {
  const map = useMap();
  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 0);
    return () => window.clearTimeout(timer);
  }, [map]);
  return null;
}

export function LocationModal({
  open,
  onClose,
  onChoose,
  initialMode = "options",
}: {
  open: boolean;
  onClose: () => void;
  onChoose: (location: SlotLocation) => void;
  initialMode?: "options" | "gps" | "search" | "map";
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeoSuggestion[]>([]);
  const [selected, setSelected] = useState<SlotLocation | null>(null);
  const [mapOpen, setMapOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || query.trim().length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api.geoSearch(query.trim())
        .then((response) => { if (!cancelled) setResults(response.results); })
        .catch(() => { if (!cancelled) setResults([]); });
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  const choose = (location: SlotLocation) => {
    setSelected(location);
    setError(null);
    onChoose(location);
    setMapOpen(false);
    onClose();
  };

  const useGps = () => {
    if (!navigator.geolocation) {
      setError(copy.home.locationError);
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        try {
          const address = await api.geoReverse(coords.latitude, coords.longitude);
          choose({
            label: address.neighbourhood || address.formatted_address || copy.home.selectedMapPoint,
            lat: coords.latitude,
            lon: coords.longitude,
          });
        } catch {
          choose({ label: copy.home.selectedMapPoint, lat: coords.latitude, lon: coords.longitude });
        } finally {
          setLoading(false);
        }
      },
      () => {
        setError(copy.home.locationError);
        setLoading(false);
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const selectMapPoint = (lat: number, lon: number) => {
    setError(null);
    setSelected({ label: copy.home.selectedMapPoint, lat, lon });
    api.geoReverse(lat, lon)
      .then((address) => {
        const hood = address.neighbourhood || address.label;
        const label = address.label || (hood ? `نزدیک ${hood}` : copy.home.selectedMapPoint);
        setSelected({ label, lat, lon });
      })
      .catch(() => undefined);
  };

  useEffect(() => {
    if (!open) return;
    if (initialMode === "gps") useGps();
    if (initialMode === "map") setMapOpen(true);
    if (initialMode === "search") window.setTimeout(() => document.getElementById("hood-search")?.focus(), 0);
  // The initial mode is an instruction for this opening only.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialMode]);

  return (
    <Sheet open={open} onClose={onClose} title={copy.home.location}>
      <div className="space-y-3">
        <button onClick={useGps} disabled={loading} className="w-full rounded-xl bg-brand-bg p-3 text-right text-[13px] font-bold">
          {loading ? copy.common.loading : copy.home.useGps}
        </button>
        <label className="block text-[12px] font-medium text-brand-muted" htmlFor="hood-search">
          {copy.home.typeLocation}
        </label>
        <input
          id="hood-search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setError(null);
          }}
          placeholder={copy.home.locationPlaceholder}
          className="w-full rounded-xl border border-brand-border px-3 py-2.5 text-[13px] outline-none focus:border-brand-red"
        />
        {results.length ? (
          <div className="max-h-40 overflow-y-auto rounded-xl border border-brand-border">
            {results.map((item) => (
              <button
                key={`${item.name_fa}-${item.lat}`}
                onClick={() => choose({ label: item.name_fa, lat: item.lat, lon: item.lon })}
                className="block w-full border-b border-brand-border px-3 py-2 text-right text-[13px] last:border-0"
              >
                📍 {item.name_fa}
              </button>
            ))}
          </div>
        ) : null}
        <button onClick={() => setMapOpen((value) => !value)} className="w-full rounded-xl border border-brand-border p-3 text-right text-[13px] font-bold">
          🗺️ {copy.home.pickMap}
        </button>
        {mapOpen ? (
          <div className="h-[300px] overflow-hidden rounded-xl border border-brand-border">
            <MapContainer center={[selected?.lat ?? 35.70, selected?.lon ?? 51.42]} zoom={12} className="h-full w-full">
              <ResizeMap />
              <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap" />
              <PickPoint onPick={selectMapPoint} />
              {selected ? <Marker position={[selected.lat, selected.lon]} /> : null}
            </MapContainer>
          </div>
        ) : null}
        {selected && mapOpen ? (
          <button onClick={() => choose(selected)} className="w-full rounded-xl bg-brand-red p-3 text-[13px] font-bold text-white">
            {selected.label}
          </button>
        ) : null}
        {error ? <p className="text-[12px] text-brand-red">{error}</p> : null}
      </div>
    </Sheet>
  );
}
