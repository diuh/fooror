/**
 * Single source of content for the marketing pages.
 * Everything here is shaped the way the Payload collections will return it,
 * so swapping this static module for CMS queries later is a drop-in change.
 */

export const site = {
  name: "Fooror",
  tagline: "Revenue-driven design studio",
  description:
    "Fooror is a revenue-driven design studio. We build scalable branding and websites for e-commerce brands and digital products.",
  url: "https://fooror.com",
  email: "info@fooror.com",
  whatsapp: "+380 00 000 00 00",
  location: "Ukraine",
  timezone: "Europe/Kyiv",
};

export const nav = [
  { label: "Services", href: "/services" },
  { label: "Work", href: "/work" },
  { label: "Journal", href: "/journal" },
  { label: "Contact", href: "/contact" },
];

export const stats = [
  { value: "$50M", caption: "in revenue helped generate for our clients" },
  { value: "126", caption: "projects completed" },
  { value: "10", caption: "years of experience in ux/ui, web and branding" },
];

export type Project = {
  slug: string;
  title: string;
  descriptor: string; // SEO-semantic short line, e.g. "UX/UI for traveling platform"
  category: string;
};

export const projects: Project[] = [
  { slug: "moi-travel", title: "Moї Travel", descriptor: "UX/UI for traveling platform", category: "Design systems" },
  { slug: "bioage", title: "Bioage", descriptor: "Branding for a longevity clinic", category: "Branding" },
  { slug: "extra-violet", title: "Extra Violet", descriptor: "E-commerce for a fashion label", category: "E-commerce" },
  { slug: "smart-payments", title: "Smart Payments", descriptor: "Product design for a fintech app", category: "Web design" },
  { slug: "tanya-timal", title: "Tanya Timal", descriptor: "Art direction & photography site", category: "Branding" },
  { slug: "we-believe", title: "We Believe", descriptor: "Brand identity for a nonprofit", category: "Branding" },
];

export type Service = {
  slug: string;
  title: string;
  blurb: string;
};

export const services: Service[] = [
  { slug: "ux-ui-design", title: "UX/UI Design", blurb: "Interfaces that turn visitors into customers — research, flows, and pixel-level craft." },
  { slug: "web-design", title: "Web Design", blurb: "Editorial, conversion-focused websites for brands that want to stand apart." },
  { slug: "web-development", title: "Web Development", blurb: "Fast, SEO-clean builds on modern stacks, wired to a CMS you can actually run." },
  { slug: "brand-strategy", title: "Brand Strategy", blurb: "Positioning, messaging and naming that give the visuals something to say." },
  { slug: "brand-identity", title: "Brand Identity", blurb: "Logos, systems and guidelines that hold up across every touchpoint." },
  { slug: "e-commerce", title: "E-commerce", blurb: "Storefronts engineered around the numbers that matter — AOV, conversion, retention." },
];

export type Post = {
  slug: string;
  title: string;
  date: string;
  category: string;
};

export const posts: Post[] = [
  { slug: "best-websites-overview-2025", title: "Best websites overview 2025", date: "17 aug 2026", category: "E-commerce" },
  { slug: "best-ux-features-for-ecommerce", title: "Best ux features for ecommerce", date: "11 aug 2026", category: "UX research" },
  { slug: "why-your-checkout-loses-people", title: "Why your checkout loses people", date: "02 aug 2026", category: "E-commerce" },
  { slug: "a-design-system-in-six-weeks", title: "A design system in six weeks", date: "24 jul 2026", category: "Design systems" },
  { slug: "naming-things-so-the-team-agrees", title: "Naming things so the team agrees", date: "15 jul 2026", category: "Design systems" },
];

export const testimonial = {
  quote:
    "What impressed us most was how quickly the team understood our vision and turned it into a unique digital experience. The custom 3D scene became a standout feature of the website, while the overall design feels clean, premium, and professional. We've received great client feedback.",
  name: "Dima Diuh",
  role: "CEO & Design Director",
};

export const footerColumns = [
  { heading: "Navigate", links: nav },
  {
    heading: "Services",
    links: services.map((s) => ({ label: s.title, href: `/services/${s.slug}` })),
  },
  {
    heading: "Legal",
    links: [
      { label: "Cookie Settings", href: "/legal/cookies" },
      { label: "Privacy Policy", href: "/legal/privacy" },
      { label: "Terms of Use", href: "/legal/terms" },
    ],
  },
];
