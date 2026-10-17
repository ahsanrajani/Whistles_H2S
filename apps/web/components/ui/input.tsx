import type {InputHTMLAttributes} from "react";
import {cn} from "@/lib/utils";
export function Input({className, ...props}: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("h-10 rounded-full border bg-card px-4 text-sm placeholder:text-muted-foreground shadow-[inset_0_1px_0_rgba(255,255,255,.45)] outline-none focus:border-primary/60 focus:shadow-[0_0_0_0.25rem_color-mix(in_oklab,var(--primary)_16%,transparent)]", className)} {...props}/>;
}
