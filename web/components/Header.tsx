"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IconMenu2, IconX, IconAsterisk } from "@tabler/icons-react";
import { nav, site } from "@/lib/site";
import { Band } from "./ui/Container";

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

  return (
    <Band as="header" className="relative z-30">
      <div className="flex items-center justify-between py-5">
        <Link href="/" className="flex items-center gap-2" aria-label={`${site.name} home`}>
          <IconAsterisk size={22} stroke={2} />
          <span className="t-label t-label-sm text-[16px]">{site.name}</span>
        </Link>

        <nav className="hidden items-center gap-10 md:flex">
          {nav.map((item) => (
            <Link key={item.href} href={item.href} className="t-label t-label-sm text-[14px] link-ul">
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-6">
          <div className="hidden items-center gap-6 lg:flex">
            <span className="t-label t-label-sm text-[14px] text-muted">{site.location}</span>
            <span className="t-label t-label-sm text-[14px] text-muted">
              Local time{" "}
              <span className="text-ink tabular-nums">{time || "—"}</span>
            </span>
          </div>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="flex size-12 items-center justify-center rounded-full bg-inverse text-[var(--text-on-dark)] md:hidden"
          >
            {open ? <IconX size={22} stroke={2} /> : <IconMenu2 size={22} stroke={2} />}
          </button>
        </div>
      </div>

      {open && (
        <nav className="flex flex-col gap-4 border-t border-line py-6 md:hidden">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className="t-label t-label-sm text-[24px]"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </Band>
  );
}
