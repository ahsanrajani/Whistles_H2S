"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import {Link} from "@/components/tenant-link";
import {useMemo, useState} from "react";
import {MapContainer, Marker, Popup, TileLayer, Tooltip} from "react-leaflet";
import {ClusterLayer, FlyTo} from "./branch-map-clusters";
import type {BranchMapPage, BranchMapPoint} from "@/lib/types";
import {Card} from "./ui/card";

const BAND_COLOR: Record<string, string> = {
  high: "#e11d48", elevated: "#d97706", watch: "#6d5ef6", none: "#a1a1aa",
};
const BAND_LABEL: Record<string, string> = {
  high: "High", elevated: "Elevated", watch: "Tracked", none: "Unscored",
};

function badgeIcon(color: string, size = 26, mark = true) {
  const markSize = Math.max(9, Math.round(size / 2));
  const border = size >= 24 ? 2 : 1.5;
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};` +
      "display:flex;align-items:center;justify-content:center;" +
      `box-shadow:0 1px 4px rgba(0,0,0,.30);border:${border}px solid #fff;">` +
      (mark ? '<img src="/brand/alfalah-mark.png" alt="" ' +
        `style="width:${markSize}px;height:${markSize}px;filter:brightness(0) invert(1);display:block;"/>` : "") +
      "</div>",
    iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2],
  });
}

function jubileeIcon(color: string, size = 26, complaint = false) {
  const radius = Math.max(6, Math.round(size * 0.28));
  const asset = complaint ? "/brand/jubilee-life-red.png" : "/brand/jubilee-marker.png";
  const alertClass = complaint ? " jubilee-map-marker-alert" : "";
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size}px;border-radius:${radius}px;` +
      `background:${color};padding:2px;box-sizing:border-box;display:flex;` +
      "align-items:center;justify-content:center;border:2px solid #fff;" +
      'box-shadow:0 1px 5px rgba(0,0,0,.34);">' +
      `<div class="jubilee-map-marker${alertClass}" style="width:100%;height:100%;` +
      `border-radius:${Math.max(4, radius - 3)}px;background:${complaint ? "#d20a3c" : "#fff"};` +
      'overflow:hidden;display:flex;align-items:center;justify-content:center;">' +
      `<img src="${asset}" alt="" ` +
      'style="width:100%;height:auto;display:block;"/></div></div>',
    iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2],
  });
}

function Legend({color, label}: {color: string; label: string}) {
  return <span className="inline-flex items-center gap-1.5">
    <span className="inline-block size-2.5 rounded-full" style={{background: color}}/>{label}
  </span>;
}

function FlaggedPopup({branch}: {branch: BranchMapPoint}) {
  return <div className="min-w-52 text-xs">
    <p className="mb-0.5 text-sm font-semibold text-foreground">{branch.name}</p>
    <p className="mb-2 text-muted-foreground">{branch.city}{branch.kind ? "" : ` · branch ${branch.code}`}</p>
    <p className="mb-1 text-foreground">
      {branch.google_rating != null
        ? <>Google: <span className="font-semibold">{branch.google_rating.toFixed(1)}★</span>
            {branch.google_reviews != null && ` (${branch.google_reviews} reviews)`}
            <br /></>
        : branch.kind ? <>Google rating: unknown<br /></> : null}
      {branch.mean_rating != null ? `${branch.mean_rating.toFixed(1)}★` : "no reviews"} ·{" "}
      <span className={branch.complaints ? "font-semibold text-danger" : ""}>
        {branch.complaints} complaints
      </span>
      {branch.critical > 0 && <span className="text-danger"> · {branch.critical} critical</span>}
    </p>
    {branch.top_issue && <p className="mb-2 text-muted-foreground">
      Top issue: {branch.top_issue.replace(/_/g, " ")}
    </p>}
    {branch.key && <Link href={`/branches?branch=${branch.key}&city=${encodeURIComponent(branch.city)}`}
                         className="font-semibold text-primary">
      View mentions for this branch →
    </Link>}
  </div>;
}

function PlainTooltip({branch}: {branch: BranchMapPoint}) {
  return <div className="max-w-56 text-xs">
    <p className="mb-0.5 font-semibold text-foreground">{branch.name}</p>
    <p className="mb-0.5 text-muted-foreground">{branch.city}</p>
    <p className="m-0 truncate text-muted-foreground" title={branch.address}>{branch.address}</p>
    {branch.google_rating != null
      ? <p className="m-0 mt-0.5 text-foreground">
          Google: <span className="font-semibold">{branch.google_rating.toFixed(1)}★</span>
          {branch.google_reviews != null && ` (${branch.google_reviews} reviews)`}
        </p>
      : branch.kind && <p className="m-0 mt-0.5 text-muted-foreground">Google rating: unknown</p>}
    {branch.has_atm && <p className="m-0 mt-0.5 text-muted-foreground">Has ATM</p>}
  </div>;
}

export function BranchMap({data}: {data: BranchMapPage}) {
  // The Alfalah logo mark is only right for the Bank Alfalah catalogue; a
  // workspace's own locations (they carry a `kind`) get a plain badge.
  const own = data.branches.some(b => b.kind);
  const jubilee = own && data.focus_brand?.toLowerCase().includes("jubilee");
  const icons = useMemo(() => ({
    high: jubilee ? jubileeIcon(BAND_COLOR.high, 30) : badgeIcon(BAND_COLOR.high, 26, !own),
    elevated: jubilee ? jubileeIcon(BAND_COLOR.elevated, 30) : badgeIcon(BAND_COLOR.elevated, 26, !own),
    watch: jubilee ? jubileeIcon(BAND_COLOR.watch, 26) : badgeIcon(BAND_COLOR.watch, 20, !own),
    none: jubilee ? jubileeIcon(BAND_COLOR.none, 22) : badgeIcon(BAND_COLOR.none, own ? 14 : 18, !own),
  }), [jubilee, own]);
  const complaintIcons = useMemo(() => ({
    high: jubileeIcon(BAND_COLOR.high, 30, true),
    elevated: jubileeIcon(BAND_COLOR.elevated, 30, true),
    watch: jubileeIcon(BAND_COLOR.watch, 26, true),
    none: jubileeIcon(BAND_COLOR.none, 22, true),
  }), []);
  const iconFor = (branch: BranchMapPoint) =>
    jubilee && branch.complaints > 0 ? complaintIcons[branch.band] : icons[branch.band];
  const flagged = useMemo(() => data.branches
    .filter(b => b.band === "high" || b.band === "elevated")
    .sort((a, b) => b.score - a.score || b.complaints - a.complaints), [data.branches]);
  // Frame the network itself, not a fixed centre — Pakistan is tall, so the
  // map is tall too and the spare width holds the flagged list.
  const bounds = useMemo(() => data.branches.length
    ? L.latLngBounds(data.branches.map(b => [b.lat, b.lng] as [number, number])).pad(0.05)
    : null, [data.branches]);
  const [focus, setFocus] = useState<{lat: number; lng: number} | null>(null);

  const renderMarker = (branch: BranchMapPoint) => {
    const isFlagged = branch.band === "high" || branch.band === "elevated";
    return <Marker key={branch.code} position={[branch.lat, branch.lng]} icon={iconFor(branch)}
                   zIndexOffset={isFlagged ? 1000 : 0}>
      {isFlagged
        ? <Popup><FlaggedPopup branch={branch}/></Popup>
        : <Tooltip direction="top" offset={[0, -4]}><PlainTooltip branch={branch}/></Tooltip>}
    </Marker>;
  };

  return <Card className="overflow-hidden p-0">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
      <div className="flex items-center gap-3">
        {jubilee &&
          // eslint-disable-next-line @next/next/no-img-element
          <img src="/brand/jubilee-life-red.png" alt="Jubilee Life Insurance" className="h-9 rounded-sm"/>}
        <div>
        <h2 className="m-0 text-base font-semibold">Branch network</h2>
        <p className="m-0 text-xs text-muted-foreground">
          {data.summary.total.toLocaleString()} {data.focus_brand ?? ""} {own ? "located branches" : "branches"} · {data.summary.flagged} flagged for attention
        </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-[0.6875rem] text-muted-foreground">
        {(["high", "elevated", "watch", "none"] as const).map(band =>
          <Legend key={band} color={BAND_COLOR[band]} label={BAND_LABEL[band]}/>)}
      </div>
    </div>
    <div className="grid lg:grid-cols-[minmax(0,1fr)_300px]">
      <MapContainer {...(bounds ? {bounds, boundsOptions: {padding: [16, 16]}} : {center: [30.3753, 69.3451], zoom: 5})}
                    scrollWheelZoom wheelPxPerZoomLevel={120} preferCanvas zoomSnap={0.25}
                    className="h-[26.25rem] w-full sm:h-[37.5rem]">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
        <ClusterLayer points={data.branches} colors={BAND_COLOR} renderMarker={renderMarker}/>
        <FlyTo target={focus}/>
      </MapContainer>
      <aside className="flex max-h-[37.5rem] flex-col border-t lg:border-l lg:border-t-0">
        <p className="m-0 border-b px-4 py-2.5 text-xs font-semibold text-muted-foreground">
          Needs attention · {flagged.length}
        </p>
        {flagged.length === 0
          ? <p className="m-0 p-4 text-xs text-muted-foreground">No branch is flagged high or elevated.</p>
          : <ul className="m-0 flex-1 list-none divide-y overflow-y-auto p-0">
            {flagged.map(branch => <li key={branch.code}>
              <button type="button" onClick={() => setFocus({lat: branch.lat, lng: branch.lng})}
                      className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-muted focus-visible:bg-muted">
                <span className="mt-1 inline-block size-2.5 shrink-0 rounded-full" style={{background: BAND_COLOR[branch.band]}}/>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{branch.name}</span>
                  <span className="block text-[0.6875rem] text-muted-foreground">
                    {branch.city} · {branch.complaints} complaints{branch.critical ? ` · ${branch.critical} critical` : ""}
                  </span>
                </span>
                <span className="numeric text-xs text-muted-foreground">{branch.score}</span>
              </button>
            </li>)}
          </ul>}
      </aside>
    </div>
  </Card>;
}
