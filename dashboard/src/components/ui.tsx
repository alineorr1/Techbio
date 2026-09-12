import { type ButtonHTMLAttributes, type ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-none font-medium tracking-[0.14em] uppercase transition-colors duration-150 disabled:opacity-40 disabled:pointer-events-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wine",
  {
    variants: {
      variant: {
        default: "bg-wine text-ivory hover:bg-oxblood",
        ghost: "bg-transparent text-mute hover:text-ink hover:bg-champagne/60",
        outline: "border border-wine/30 text-wine hover:bg-champagne/70",
        danger: "border border-terra/50 bg-transparent text-terra hover:bg-terra/10",
      },
      size: {
        sm: "h-7 px-2.5 text-[10px]",
        md: "h-9 px-3 text-[11px]",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export function Button({
  className,
  variant,
  size,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export function Badge({
  children,
  tone = "muted",
  className,
}: {
  children: ReactNode;
  tone?: "muted" | "wine" | "rose" | "terra" | "champagne";
  className?: string;
}) {
  const tones = {
    muted: "bg-transparent text-mute border-wine/20",
    wine: "bg-wine/8 text-wine border-wine/25",
    rose: "bg-rose/12 text-mucosa border-rose/35",
    terra: "bg-terra/10 text-terra border-terra/30",
    champagne: "bg-champagne/80 text-oxblood border-wine/20",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-none border px-1.5 py-0.5 font-sans text-[9px] font-medium uppercase tracking-[0.16em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
