"use client";
import {Moon, Sun} from "lucide-react";
import {useTheme} from "next-themes";
import {Button} from "@/components/ui/button";

export default function ThemeToggle() {
  const {resolvedTheme, setTheme} = useTheme();
  const dark = resolvedTheme === "dark";
  return <Button variant="ghost" className="size-10 p-0" aria-label="Toggle theme" onClick={() => setTheme(dark ? "light" : "dark")}>{dark ? <Sun/> : <Moon/>}</Button>;
}
