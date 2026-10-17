"use client";
import dynamic from "next/dynamic";
import {Suspense} from "react";

const LoginForm = dynamic(() => import("@/components/login-form"), {
  ssr: false,
  loading: () => <main className="grid min-h-screen place-items-center">Loading sign in…</main>,
});

export default function LoginPage() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center">Loading sign in…</main>}><LoginForm/></Suspense>;
}
