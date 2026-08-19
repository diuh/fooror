"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IconMenu2, IconX } from "@tabler/icons-react";
import { nav, site } from "@/lib/site";
import { Band } from "./ui/Container";
import { Logo } from "./Logo";

function useLocalTime() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () =>
      setTime(
        new Intl.DateTimeFormat("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: true,
          timeZone: site.timezone,
        }).format(new Date())
      );
    tick();
    const id = setInterval(tick, 15_000);
    return () => clearInterval(id);
  }, []);
  return time;
}

export function Header() {
  const time = useLocalTime();
  const [open, setOpen] = useState(false);
  const [city, country] = site.location.split(", ");

  return (
    // sticky: the pill floats and pins to the top on scroll
    <Band as="header" className="sticky top-0 z-40 pt-5 pb-2.5">
      {/* uniform 10px padding on every side, exactly like the macket */}
      <div className="rounded-[60px] bg-page p-2.5">
        {/* desktop: 1fr / 3fr / 1fr grid, exactly as the macket */}
        <div className="flex items-center justify-between gap-5 md:grid md:grid-cols-[1fr_3fr_1fr]">
          {/* col 1 — logo + tagline */}
          <div className="flex items-center justify-between gap-6">
            <Logo />
            <p className="hidden w-[210px] text-right text-[14px] leading-[0.9] tracking-[-0.02em] lg:block">
              Revenue-driven<br />design studio
            </p>
          </div>

          {/* col 2 — primary nav */}
          <nav className="hidden items-center justify-center gap-10 md:flex">
            {nav.map((item) => (
              <Link key={item.href} href={item.href} className="nav-link text-[16px]">
                {item.label}
              </Link>
            ))}
          </nav>

          {/* col 3 — locale + local time + menu (menu always pinned far right) */}
          <div className="flex items-center justify-end gap-6">
            <div className="hidden items-center gap-6 pr-4 text-[14px] leading-[0.9] tracking-[-0.02em] whitespace-nowrap lg:flex">
              <p>
                {city},<br />{country}
              </p>
              <p className="text-right tabular-nums">
                Local time<br />{time || "—"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              className="grid size-10 shrink-0 place-items-center rounded-full bg-inverse text-[var(--text-on-dark)] transition-transform hover:scale-95"
            >
              {open ? <IconX size={22} stroke={2} /> : <IconMenu2 size={22} stroke={2} />}
            </button>
          </div>
        </div>

        {/* dropdown menu (all breakpoints — the macket's menu button is always present) */}
        {open && (
          <nav className="mt-2.5 flex flex-col gap-2 border-t border-line px-3 py-6">
            {nav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="t-display w-fit text-[clamp(28px,4vw,40px)] transition-colors hover:text-[var(--text-accent)]"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        )}
      </div>
    </Band>
  );
}
