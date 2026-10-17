import {Slot} from "@radix-ui/react-slot";
import {cva, type VariantProps} from "class-variance-authority";
import type {ButtonHTMLAttributes} from "react";
import {cn} from "@/lib/utils";

// Pills everywhere. Primary is the violet gradient with a specular top edge; every variant lifts 1px on
// hover and presses in on click, on the shared 160ms ease-out.
const variants = cva(
  "inline-flex h-10 items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold hover:-translate-y-px active:translate-y-0 active:scale-[.97] disabled:pointer-events-none disabled:opacity-50",
  {variants: {variant: {
    default: "bg-[linear-gradient(135deg,#8173ff,var(--primary)_55%,#5a4be3)] text-white shadow-[inset_0_1px_0_rgba(255,255,255,.35),0_0.5rem_1.375rem_rgba(109,94,246,.34)] hover:brightness-110 hover:shadow-[inset_0_1px_0_rgba(255,255,255,.4),0_0.75rem_1.75rem_rgba(109,94,246,.42)]",
    outline: "border bg-card shadow-[inset_0_1px_0_rgba(255,255,255,.5)] hover:bg-muted hover:shadow-[0_0.375rem_1.125rem_rgba(72,56,170,.10)]",
    ghost: "hover:bg-muted",
    danger: "bg-[linear-gradient(135deg,#f4506c,var(--danger))] text-white shadow-[inset_0_1px_0_rgba(255,255,255,.3),0_0.5rem_1.375rem_rgba(225,29,72,.28)] hover:brightness-110",
  }}, defaultVariants: {variant: "default"}},
);
export function Button({className, variant, asChild, ...props}: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof variants> & {asChild?: boolean}) {
  const Component = asChild ? Slot : "button";
  return <Component className={cn(variants({variant}), className)} {...props}/>;
}
