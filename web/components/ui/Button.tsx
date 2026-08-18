import Link from "next/link";
import { IconArrowUpRight } from "@tabler/icons-react";
import type { ComponentType } from "react";

type Tone = "accent" | "ink" | "onDark";
type Size = "sm" | "md" | "lg";

const toneClass: Record<Tone, string> = {
  accent: "text-accent",
  ink: "text-ink",
  onDark: "text-[var(--text-on-dark)]",
};

const sizeClass: Record<Size, string> = {
  sm: "text-[16px]",
  md: "text-[clamp(18px,2vw,24px)]",
  lg: "text-[clamp(22px,2.6vw,32px)]",
};

export function Button({
  href,
  children,
  tone = "ink",
  size = "md",
  icon: Icon = IconArrowUpRight,
  className = "",
}: {
  href: string;
  children: React.ReactNode;
  tone?: Tone;
  size?: Size;
  icon?: ComponentType<{ size?: number; stroke?: number }> | null;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={`group inline-flex items-center gap-3 t-label t-label-sm ${toneClass[tone]} ${sizeClass[size]} ${className}`}
    >
      <span className="link-ul">{children}</span>
      {Icon ? (
        <span className="transition-transform duration-300 group-hover:translate-x-1 group-hover:-translate-y-1">
          <Icon size={size === "lg" ? 28 : 22} stroke={2} />
        </span>
      ) : null}
    </Link>
  );
}
