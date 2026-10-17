import {Suspense} from "react";
import {ContentCalendarView} from "@/components/content-calendar-view";

export default function ContentPage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}>
      <ContentCalendarView/>
    </Suspense>
  );
}
