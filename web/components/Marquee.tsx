import { IconAsterisk } from "@tabler/icons-react";

export function Marquee({ text, count = 8 }: { text: string; count?: number }) {
  const unit = Array.from({ length: count });
  return (
    <div className="overflow-hidden bg-inverse py-6 text-[var(--text-on-dark)]">
      <div className="marquee-track" aria-hidden>
        {/* duplicated once so the -50% keyframe loops seamlessly */}
        {[0, 1].map((g) => (
          <div className="marquee-track" key={g} style={{ animation: "none" }}>
            {unit.map((_, i) => (
              <span key={i} className="flex items-center gap-10">
                <span className="t-label t-label-lg text-[clamp(20px,2vw,24px)]">{text}</span>
                <IconAsterisk size={22} stroke={2} className="text-accent" />
              </span>
            ))}
          </div>
        ))}
      </div>
      <span className="sr-only">{text}</span>
    </div>
  );
}
