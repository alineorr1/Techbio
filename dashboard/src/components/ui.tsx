import { type ButtonHTMLAttributes, type ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-none bg-transparent font-sans text-sm font-medium disabled:opacity-40 disabled:pointer-events-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
  {
    variants: {
      variant: {
        default: "text-ink underline decoration-1 underline-offset-4",
        ghost: "text-mute hover:text-ink",
        outline: "border border-line px-3 text-ink hover:border-ink",
        danger: "border border-line px-3 text-ink hover:border-ink",
      },
      size: {
        sm: "h-8 text-[13px]",
        md: "h-9 text-sm",
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
  tone?: "muted" | "ink" | "hairline";
  className?: string;
}) {
  const tones = {
    muted: "text-mute",
    ink: "text-ink",
    hairline: "border border-line px-1.5 py-0.5 text-mute",
  };
  return (
    <span className={cn("inline-flex items-center font-mono text-[11px]", tones[tone], className)}>
      {children}
    </span>
  );
}
