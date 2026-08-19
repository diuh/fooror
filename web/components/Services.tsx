"use client";

import { useState } from "react";
import Link from "next/link";
import { IconAsterisk, IconArrowUpRight } from "@tabler/icons-react";
import { services } from "@/lib/site";

export function Services() {
  const [open, setOpen] = useState(0);

  return (
    <div className="border-t border-line">
      {services.map((s, i) => {
        const isOpen = i === open;
        return (
          <div key={s.slug} className="border-b border-line bg-page">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? -1 : i)}
              aria-expanded={isOpen}
              className="flex w-full items-center gap-6 px-6 py-8 text-left md:px-10"
            >
              <IconAsterisk
                size={22}
                stroke={2}
                className={`shrink-0 text-muted transition-transform duration-500 ${isOpen ? "rotate-90 text-accent" : ""}`}
              />
              <span className="hidden w-[280px] shrink-0 md:block" aria-hidden />
              <span className="t-display d-110 flex-1">{s.title}</span>
              <IconArrowUpRight
                size={28}
                stroke={2}
                className={`shrink-0 transition-opacity duration-300 ${isOpen ? "opacity-100 text-accent" : "opacity-30"}`}
              />
            </button>
            <div
              className="grid transition-[grid-template-rows] duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
              style={{ gridTemplateRows: isOpen ? "1fr" : "0fr" }}
            >
              <div className="overflow-hidden">
                <div className="flex flex-col gap-6 px-6 pb-10 md:flex-row md:items-end md:pl-[308px] md:pr-10">
                  <p className="max-w-[460px] flex-1 text-[16px] text-muted">{s.blurb}</p>
                  <Link
                    href={`/services/${s.slug}`}
                    className="group inline-flex items-center gap-3 t-label t-label-sm text-[16px] text-accent"
                  >
                    <span className="link-ul">More information</span>
                    <IconArrowUpRight size={22} stroke={2} className="transition-transform duration-300 group-hover:translate-x-1 group-hover:-translate-y-1" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
