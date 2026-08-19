# Fooror — website

Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS v4.

## Run locally

```bash
cd web
npm install
npm run dev      # http://localhost:3000
```

`npm run build && npm run start` for a production build.

## What's here so far

- **Homepage** (`app/page.tsx`) built from the Figma macket, section for section:
  hero with a live stipple portrait, marquee, stats, featured work, services
  accordion, journal, testimonial, accent CTA band, footer.
- **Design tokens** in `app/globals.css` — a 1:1 mirror of the Figma variable
  collections and `design-system/tokens.css`. Components never hardcode a colour.
- **Type** via `next/font` (Archivo Narrow for display/labels, Archivo for body),
  self-hosted, no external font request at runtime.
- **Content** in `lib/site.ts`, shaped the way the Payload collections will return
  it — swapping this module for CMS queries later is a drop-in change.
- **SEO**: metadata + canonical in `app/layout.tsx`, Organization/WebSite JSON-LD,
  `app/robots.ts` (AI crawlers explicitly allowed), `app/sitemap.ts`.

## Signature detail

The hero portrait is the studio's own **Temporal Stipple** engine (see
`/temporal-stipple`) reduced to a lean client component (`components/StippleCanvas.tsx`).
The density source is drawn procedurally — no photo asset — so the hero renders
identically everywhere and has nothing to fetch. Respects `prefers-reduced-motion`.

The work cards use the fooror.com hover mechanic (`.workcard` in `globals.css`):
image only at rest; on hover the mask lifts and the image scales, revealing the
project name and its SEO descriptor.

## Not built yet

Inner pages (work, case, services, service, journal, article, contact, about,
legal, 404), the Payload CMS layer, and responsive polish below the breakpoints
already handled. Links to those routes 404 until their pages land — expected.
