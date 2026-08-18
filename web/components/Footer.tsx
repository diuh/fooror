import Link from "next/link";
import { IconAsterisk, IconMail, IconBrandWhatsapp } from "@tabler/icons-react";
import { site, footerColumns } from "@/lib/site";
import { Band } from "./ui/Container";

export function Footer() {
  return (
    <Band as="footer" className="pb-5">
      <div className="bg-plate px-6 pt-20 pb-10 md:px-10">
        <div className="flex flex-col justify-between gap-12 lg:flex-row">
          <div className="flex flex-col gap-5">
            <Link href="/" className="flex items-center gap-2">
              <IconAsterisk size={22} stroke={2} />
              <span className="t-label t-label-sm text-[16px]">{site.name}</span>
            </Link>
            <p className="text-[14px] text-muted">{site.tagline}</p>
          </div>

          <div className="flex flex-wrap gap-12">
            {footerColumns.map((col) => (
              <nav key={col.heading} className="flex flex-col gap-4">
                <span className="t-label t-label-sm text-[14px] text-muted">{col.heading}</span>
                {col.links.map((l) => (
                  <Link key={l.href} href={l.href} className="nav-link text-[14px]">
                    {l.label}
                  </Link>
                ))}
              </nav>
            ))}
            <div className="flex flex-col gap-4">
              <span className="t-label t-label-sm text-[14px] text-muted">Contact</span>
              <a href={`mailto:${site.email}`} className="flex items-center gap-2.5 text-[16px] link-ul">
                <IconMail size={22} stroke={2} /> {site.email}
              </a>
              <a href="#" className="flex items-center gap-2.5 text-[16px] link-ul">
                <IconBrandWhatsapp size={22} stroke={2} /> {site.whatsapp}
              </a>
            </div>
          </div>
        </div>

        <div className="mt-20 flex flex-col justify-between gap-3 border-t border-line pt-6 text-[14px] text-muted sm:flex-row">
          <span>
            {site.name} © {new Date().getFullYear()} All rights reserved
          </span>
          <span>Web design by {site.name}</span>
        </div>
      </div>
    </Band>
  );
}
