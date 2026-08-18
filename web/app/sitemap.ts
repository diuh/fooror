import type { MetadataRoute } from "next";
import { site, nav, services, projects, posts } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const url = (path: string) => `${site.url}${path}`;

  const staticPages = ["/", ...nav.map((n) => n.href), "/about"].map((path) => ({
    url: url(path),
    lastModified: now,
    changeFrequency: "monthly" as const,
    priority: path === "/" ? 1 : 0.7,
  }));

  const dynamic = [
    ...services.map((s) => `/services/${s.slug}`),
    ...projects.map((p) => `/work/${p.slug}`),
    ...posts.map((p) => `/journal/${p.slug}`),
  ].map((path) => ({
    url: url(path),
    lastModified: now,
    changeFrequency: "weekly" as const,
    priority: 0.6,
  }));

  return [...staticPages, ...dynamic];
}
