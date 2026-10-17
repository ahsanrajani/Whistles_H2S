"use client";

import L from "leaflet";
import {useEffect, useMemo, useState, type ReactNode} from "react";
import {Marker, Tooltip, useMap, useMapEvents} from "react-leaflet";
import type {BranchMapPoint} from "@/lib/types";

const RADIUS_PX = 38;        // markers closer than this on screen fold into one bubble
const UNCLUSTER_ZOOM = 13;   // street level: always show every branch
const SEVERITY: Record<string, number> = {high: 3, elevated: 2, watch: 1, none: 0};

type Cluster = {members: BranchMapPoint[]; lat: number; lng: number; worst: string};

/** Greedy screen-space clustering: worst branches seed clusters first, so a
 *  bubble is always centred on (and coloured by) its most urgent branch. */
function cluster(points: BranchMapPoint[], map: L.Map, zoom: number): Cluster[] {
  if (zoom >= UNCLUSTER_ZOOM) {
    return points.map(p => ({members: [p], lat: p.lat, lng: p.lng, worst: p.band}));
  }
  const sorted = [...points].sort((a, b) => (SEVERITY[b.band] ?? 0) - (SEVERITY[a.band] ?? 0));
  const out: (Cluster & {px: L.Point})[] = [];
  for (const p of sorted) {
    const px = map.project([p.lat, p.lng], zoom);
    const home = out.find(c => c.px.distanceTo(px) < RADIUS_PX);
    if (home) home.members.push(p);
    else out.push({members: [p], lat: p.lat, lng: p.lng, worst: p.band, px});
  }
  return out;
}

function bubbleIcon(count: number, color: string, flagged: number) {
  const size = count < 10 ? 30 : count < 50 ? 36 : 42;
  const badge = flagged > 0
    ? `<span style="position:absolute;top:-4px;right:-4px;min-width:16px;height:16px;padding:0 3px;` +
      "border-radius:8px;background:#fff;color:#e11d48;font:700 10px/16px system-ui;text-align:center;" +
      `box-shadow:0 1px 3px rgba(0,0,0,.3);">${flagged}</span>`
    : "";
  return L.divIcon({
    className: "",
    html: `<div style="position:relative;width:${size}px;height:${size}px;border-radius:50%;` +
      `background:${color};color:#fff;border:2px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.35);` +
      `display:flex;align-items:center;justify-content:center;font:600 12px system-ui;">${count}${badge}</div>`,
    iconSize: [size, size], iconAnchor: [size / 2, size / 2],
  });
}

export function ClusterLayer({points, colors, renderMarker}: {
  points: BranchMapPoint[];
  colors: Record<string, string>;
  renderMarker: (branch: BranchMapPoint) => ReactNode;
}) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());
  useMapEvents({zoomend: () => setZoom(map.getZoom())});
  const clusters = useMemo(() => cluster(points, map, zoom), [points, map, zoom]);

  return <>{clusters.map(c => {
    if (c.members.length === 1) return renderMarker(c.members[0]);
    const flagged = c.members.filter(m => m.band === "high" || m.band === "elevated").length;
    const bounds = L.latLngBounds(c.members.map(m => [m.lat, m.lng] as [number, number]));
    const cities = Array.from(new Set(c.members.map(m => m.city))).slice(0, 3).join(", ");
    return <Marker key={`c-${c.members[0].code}-${c.members.length}`} position={[c.lat, c.lng]}
                   icon={bubbleIcon(c.members.length, colors[c.worst] ?? colors.none, flagged)}
                   eventHandlers={{click: () => {
                     // identical coordinates can't separate by zooming — jump to street level
                     if (bounds.getNorthEast().equals(bounds.getSouthWest())) map.setView(bounds.getCenter(), UNCLUSTER_ZOOM);
                     else map.fitBounds(bounds, {padding: [48, 48], maxZoom: UNCLUSTER_ZOOM});
                   }}}>
      <Tooltip direction="top" offset={[0, -14]}>
        <span className="text-xs"><b>{c.members.length} branches</b>{flagged ? ` · ${flagged} flagged` : ""}<br/>{cities}</span>
      </Tooltip>
    </Marker>;
  })}</>;
}

/** Imperative handle so the side list can fly the map to a branch. */
export function FlyTo({target}: {target: {lat: number; lng: number} | null}) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const zoom = Math.max(map.getZoom(), UNCLUSTER_ZOOM);
    if (still) map.setView([target.lat, target.lng], zoom);
    else map.flyTo([target.lat, target.lng], zoom, {duration: 0.8});
  }, [map, target]);
  return null;
}
