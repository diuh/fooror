"use client";

import { useEffect, useRef } from "react";

/**
 * A living stipple portrait — the studio's signature (see /temporal-stipple).
 * A silhouette is drawn offscreen, its luminance becomes a density field, and
 * particles are seeded against it by rejection sampling. Each frame the dots
 * jitter around their home position, so the portrait breathes without ever
 * resolving into a still image. Mono black on the plate ground.
 *
 * No photo asset required — the density source is drawn procedurally, so the
 * hero has no external dependency and renders identically everywhere.
 */
export function StippleCanvas({
  className = "",
  density = 1.35,
  dot = 2.7,
}: {
  className?: string;
  density?: number;
  dot?: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0, H = 0, raf = 0;
    let hx = new Float32Array(0), hy = new Float32Array(0), ph = new Float32Array(0);
    let n = 0;

    // luminance sampler of a head-and-shoulders silhouette
    const sw = 180;
    let sh = 180;
    const sample = document.createElement("canvas");
    const sctx = sample.getContext("2d", { willReadFrequently: true })!;
    let lum: Float32Array = new Float32Array(0);

    function buildField() {
      sh = Math.max(120, Math.round((sw * H) / Math.max(1, W)));
      sample.width = sw; sample.height = sh;
      sctx.clearRect(0, 0, sw, sh);
      sctx.fillStyle = "#fff";
      sctx.fillRect(0, 0, sw, sh);

      const cx = sw * 0.5;
      const headR = sw * 0.2;
      const headCy = sh * 0.4;
      // shoulders
      sctx.fillStyle = "#111";
      sctx.beginPath();
      sctx.moveTo(cx - headR * 2.6, sh);
      sctx.bezierCurveTo(cx - headR * 2.4, sh * 0.72, cx - headR * 1.5, headCy + headR * 1.2, cx, headCy + headR * 1.15);
      sctx.bezierCurveTo(cx + headR * 1.5, headCy + headR * 1.2, cx + headR * 2.4, sh * 0.72, cx + headR * 2.6, sh);
      sctx.closePath();
      sctx.fill();
      // head, shaded darker on one side so the stipple has tonal range
      const g = sctx.createRadialGradient(cx - headR * 0.4, headCy - headR * 0.4, headR * 0.1, cx, headCy, headR * 1.35);
      g.addColorStop(0, "#6a6a72");
      g.addColorStop(0.6, "#222");
      g.addColorStop(1, "#000");
      sctx.fillStyle = g;
      sctx.beginPath();
      sctx.ellipse(cx, headCy, headR, headR * 1.2, 0, 0, Math.PI * 2);
      sctx.fill();

      const data = sctx.getImageData(0, 0, sw, sh).data;
      lum = new Float32Array(sw * sh);
      for (let i = 0, p = 0; i < sw * sh; i++, p += 4) {
        lum[i] = 1 - (0.2126 * data[p] + 0.7152 * data[p + 1] + 0.0722 * data[p + 2]) / 255;
      }
    }

    function seed() {
      const target = Math.round(density * (W * H) / 900);
      n = Math.min(target, 40000);
      hx = new Float32Array(n); hy = new Float32Array(n); ph = new Float32Array(n);
      let i = 0, guard = 0;
      while (i < n && guard < n * 60) {
        guard++;
        const sx = (Math.random() * sw) | 0;
        const sy = (Math.random() * sh) | 0;
        const d = lum[sy * sw + sx];
        if (Math.random() < d * d) {
          hx[i] = (sx + Math.random()) * (W / sw);
          hy[i] = (sy + Math.random()) * (H / sh);
          ph[i] = Math.random() * Math.PI * 2;
          i++;
        }
      }
      n = i;
    }

    function resize() {
      const r = canvas!.getBoundingClientRect();
      W = Math.max(1, r.width); H = Math.max(1, r.height);
      canvas!.width = Math.round(W * dpr);
      canvas!.height = Math.round(H * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildField();
      seed();
      if (reduce) draw(0);
    }

    function draw(t: number) {
      ctx!.fillStyle = "#e5e5ed";
      ctx!.fillRect(0, 0, W, H);
      ctx!.fillStyle = "#000";
      const o = dot * 0.5;
      const wob = reduce ? 0 : 1;
      for (let i = 0; i < n; i++) {
        const a = ph[i] + t;
        const x = hx[i] + Math.cos(a) * 1.6 * wob;
        const y = hy[i] + Math.sin(a * 1.3) * 1.6 * wob;
        ctx!.fillRect(x - o, y - o, dot, dot);
      }
    }

    let start = performance.now();
    function loop(now: number) {
      draw((now - start) / 1000);
      raf = requestAnimationFrame(loop);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    if (!reduce) raf = requestAnimationFrame(loop);

    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [density, dot]);

  return <canvas ref={ref} className={className} aria-hidden />;
}
