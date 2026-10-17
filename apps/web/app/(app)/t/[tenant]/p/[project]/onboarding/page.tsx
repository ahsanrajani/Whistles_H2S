import {Suspense} from "react";
import {OnboardingView} from "@/components/onboarding-view";
export default function OnboardingPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><OnboardingView/></Suspense>;}
