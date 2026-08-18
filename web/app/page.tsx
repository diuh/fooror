import Link from "next/link";
import { IconArrowUpRight, IconCornerRightDown } from "@tabler/icons-react";
import { Header } from "@/components/Header";
import { Marquee } from "@/components/Marquee";
import { StippleCanvas } from "@/components/StippleCanvas";
import { Services } from "@/components/Services";
import { WorkCard } from "@/components/WorkCard";
import { Footer } from "@/components/Footer";
import { Band, Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";
import { stats, projects, posts, testimonial, site } from "@/lib/site";

export default function Home() {
  return (
    <>
      <Header />

      {/* ---------------- Hero ---------------- */}
      <Band as="section" aria-label="Intro">
        <div className="relative overflow-hidden bg-plate">
          <div className="relative h-[46vh] min-h-[320px] w-full md:h-[58vh]">
            <StippleCanvas className="absolute inset-0 h-full w-full" />
            <div className="pointer-events-none absolute left-6 top-6 md:left-10 md:top-10">
              <span className="t-label t-label-sm rounded-full bg-inverse px-4 py-2 text-[13px] text-[var(--text-on-dark)]">
                Revive with the camera
              </span>
            </div>
          </div>

          <div className="grid gap-10 bg-page px-6 py-14 md:grid-cols-12 md:px-10 md:py-20">
            <h1 className="t-display d-hero md:col-span-7">
              Revenue-driven<br />design ecosystems
            </h1>
            <div className="flex flex-col gap-8 md:col-span-5 md:pt-2">
              <p className="max-w-[420px] text-[clamp(18px,1.5vw,24px)] leading-tight">
                We build scalable branding and websites for e-commerce brands and
                digital products.
              </p>
              <Button href="/contact" tone="accent" size="lg" icon={IconCornerRightDown}>
                Book a free session
              </Button>
            </div>
          </div>
        </div>
      </Band>

      <div className="px-[var(--gutter)]">
        <div className="mx-auto max-w-[1880px]">
          <Marquee text={site.tagline} />
        </div>
      </div>

      {/* ---------------- Stats ---------------- */}
      <Band as="section" aria-label="By the numbers" className="pt-5">
        <div className="grid gap-10 bg-page px-6 py-16 md:grid-cols-3 md:px-10 md:py-20">
          {stats.map((s) => (
            <div key={s.caption} className="flex items-end gap-5">
              <span className="t-display d-80">{s.value}</span>
              <span className="mb-2 max-w-[200px] text-[15px] leading-tight text-muted">
                {s.caption}
              </span>
            </div>
          ))}
        </div>
      </Band>

      {/* ---------------- Featured Work ---------------- */}
      <Band as="section" aria-label="Featured work" className="pt-5">
        <div className="bg-page px-6 pt-16 pb-20 md:px-10">
          <div className="mb-10 flex items-end justify-between gap-6">
            <div>
              <span className="t-label t-label-sm text-[16px] text-accent">Portfolio</span>
              <h2 className="t-display d-80 mt-3">Featured Work</h2>
            </div>
            <Button href="/work" tone="ink" size="md">Explore more</Button>
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            {projects.slice(0, 4).map((p) => (
              <WorkCard key={p.slug} project={p} />
            ))}
          </div>
        </div>
      </Band>

      {/* ---------------- Services ---------------- */}
      <Band as="section" aria-label="Services" className="pt-5">
        <div className="bg-page px-6 pt-16 md:px-10">
          <div className="mb-12 grid gap-6 md:grid-cols-12">
            <h2 className="t-display d-80 md:col-span-6">
              Find the service<br />you need
            </h2>
            <p className="max-w-[420px] text-[16px] text-muted md:col-span-6 md:pt-2">
              We specialize in branding, digital strategy, web design and marketing
              across real estate, fashion, hospitality and architecture.
            </p>
          </div>
        </div>
        <Services />
      </Band>

      {/* ---------------- Journal ---------------- */}
      <Band as="section" aria-label="Design journal" className="pt-5">
        <div className="bg-page px-6 pt-20 pb-20 md:px-10">
          <div className="mb-10 flex flex-wrap items-baseline justify-between gap-6">
            <h2 className="t-display d-mega text-center leading-[0.85]">Design Journal</h2>
            <Button href="/journal" tone="ink" size="md">All posts</Button>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
            {posts.map((post) => (
              <Link
                key={post.slug}
                href={`/journal/${post.slug}`}
                className="group flex flex-col gap-6 bg-page"
              >
                <div className="flex items-center justify-between">
                  <span className="t-label t-label-sm text-[13px] text-muted">{post.category}</span>
                  <IconArrowUpRight size={20} stroke={2} className="opacity-40 transition-opacity group-hover:opacity-100" />
                </div>
                <div className="flex flex-col gap-2">
                  <span className="t-label t-label-sm text-[13px] text-muted">{post.date}</span>
                  <h3 className="text-[20px] leading-tight">{post.title}</h3>
                </div>
                <div
                  className="mt-auto aspect-[3/4] w-full"
                  style={{ background: "radial-gradient(120% 120% at 30% 10%, #2a2a32, #0c0c10)" }}
                />
              </Link>
            ))}
          </div>
        </div>
      </Band>

      {/* ---------------- Testimonial ---------------- */}
      <Band as="section" aria-label="Client feedback" className="pt-5">
        <div className="bg-page px-6 py-24 md:px-10">
          <Container>
            <span className="t-label t-label-sm block text-center text-[14px] text-accent">
              What our clients say
            </span>
            <blockquote className="mt-10 text-center text-[clamp(24px,3vw,40px)] leading-tight">
              “{testimonial.quote}”
            </blockquote>
            <div className="mt-12 flex items-center justify-center gap-4">
              <span className="size-12 rounded-full bg-plate" aria-hidden />
              <span>
                <span className="block text-[16px] font-bold">{testimonial.name}</span>
                <span className="block text-[14px] text-muted">{testimonial.role}</span>
              </span>
            </div>
          </Container>
        </div>
      </Band>

      {/* ---------------- CTA band ---------------- */}
      <Band as="section" aria-label="Start a project" className="pt-5">
        <div className="bg-accent px-6 py-28 md:px-[clamp(40px,10vw,192px)]">
          <h2 className="t-display d-110 max-w-[16ch]">
            <span className="block">Our main goal —</span>
            <span className="block text-[var(--text-faded)]">deliver design services</span>
            <span className="block">help your business become better</span>
          </h2>
          <div className="mt-14">
            <Button href="/contact" tone="ink" size="lg">Start new project</Button>
          </div>
        </div>
      </Band>

      <Footer />
    </>
  );
}
