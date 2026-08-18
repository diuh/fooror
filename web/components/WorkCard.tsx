import Link from "next/link";
import { IconArrowUpRight } from "@tabler/icons-react";
import type { Project } from "@/lib/site";

/** Fooror hover-reveal card: image only at rest; on hover the mask lifts and
 *  the image scales, revealing the project name + its SEO descriptor. */
export function WorkCard({ project }: { project: Project }) {
  return (
    <Link
      href={`/work/${project.slug}`}
      className="workcard block aspect-[3/2] w-full"
      aria-label={`${project.title} — ${project.descriptor}`}
    >
      <div className="info flex items-start justify-between gap-4 bg-page p-6" style={{ minHeight: 132 }}>
        <div>
          <h3 className="text-[clamp(18px,1.6vw,24px)] leading-none">{project.title}</h3>
          <p className="t-label t-label-sm mt-2 text-[13px] text-muted">{project.descriptor}</p>
        </div>
        <IconArrowUpRight size={22} stroke={2} className="shrink-0" />
      </div>
      <div className="mask">
        <span
          className="ph"
          style={{
            background:
              "radial-gradient(120% 120% at 30% 20%, #d3d3de 0%, #c2c2cf 45%, #a9a9b8 100%)",
          }}
        />
      </div>
    </Link>
  );
}
