import {redirect} from "next/navigation";
import {defaultLandingPath} from "@/lib/tenant-server";

export default async function Home() {
  const path = await defaultLandingPath();
  redirect(path ?? "/login");
}
