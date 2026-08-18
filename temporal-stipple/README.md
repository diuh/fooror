# Temporal Stipple

A generative stippling sketch: thousands of dots self-organize into the shape of a
source image, video, or webcam feed by following the source's luminance. The dots
converge into a recognizable picture but never fully settle — they keep jittering
and repositioning, like a scanning halftone with a pulse.

Single self-contained file, no build step and no dependencies. Open
`index.html` in a browser.

## Controls

| Control | What it does |
| --- | --- |
| **Image / Video / Camera** | Input mode. Image and Video take a file; Camera asks for `getUserMedia` access. You can also drop an image or video anywhere on the canvas. |
| **Dot count** | Particle count, 500–60,000. Resizes live: growing seeds the new dots from the density field without disturbing the ones already placed. |
| **Dot size** | Side length of each square dot, in CSS pixels. |
| **Dot color** | Fill color in mono mode. |
| **Sample source color** | Off: every dot uses the dot color. On: each dot takes the source's color at its own position. |
| **Contrast (gamma)** | Exponent applied to the density field. Higher values push mid-tones toward the extremes, so dots cluster harder into the dark areas. |
| **Invert luminance** | Flips which end of the tonal range attracts dots. Default is dark = dense. |
| **Attraction** | How hard the density gradient pulls dots toward denser regions. |
| **Repulsion** | Inter-dot spacing pressure. |
| **Jitter** | Random exploration, scaled by how empty a dot's neighbourhood is. |
| **Damping** | Per-frame velocity decay. Low values settle fast; high values keep the field churning. |
| **Sim steps / frame** | Physics sub-steps per animation frame. More steps is smoother and more stable, and costs proportionally more. |
| **Pause / Reseed** | Space toggles play/pause, `R` re-runs the CDF sampling from scratch. |

## How it works

**Source → density field.** The source is drawn into an offscreen canvas scaled so
its long edge is at most 256px, then read once with `getImageData`. That gives a
per-pixel luminance map (Rec. 709 weights) and an RGB copy for color mode. The
density field is `(1 - luminance) ^ contrast`, or `luminance ^ contrast` when
inverted, so dark source areas ask for more dots.

**Gradient.** The density field is box-blurred 3×3 (separably) and differentiated
with central differences. Blurring first matters: gradients taken straight off the
raw field are noisy enough to make the dots buzz.

**Seeding.** A cumulative distribution function is built over every pixel weighted
by density. Each dot is placed by drawing a uniform sample and binary-searching the
CDF, so the very first frame already resembles the source before any physics runs.

**Per frame, per dot.** Attraction along the density gradient (clamped, so hard
luminance edges do not accrete dots into a drawn-looking outline); jitter scaled by
local sparseness; local repulsion; velocity damping; reflection off the canvas edges
with energy loss.

**Repulsion and tone.** Uniform repulsion is what kills a stipple — it spreads every
dot to the same spacing and the picture flattens into noise. Here the rest spacing
is derived from the density field: for the dot field to reproduce tone, the local
areal density of dots must track the source, so `spacing² = (meanDensity · area / N) / density`.
Repulsion is a soft core that falls to exactly zero at that spacing. Dark regions
pack tight, light regions stay open.

**Neighbours.** A spatial hash with a cell size that tracks the mean dot spacing
(around 24px at low dot counts, tighter as the count climbs) keeps each dot's search
to a 3×3 block. Falloff is inverse-square evaluated on the squared distance, so
there is no `sqrt` in the inner loop. Two budgets bound the work per dot per step:
pairs applied and hash entries walked.

**Strays.** A dot adrift in a flat empty region feels no gradient and has no
neighbours close enough to push it, so it would wander forever. Dots below a
density threshold are re-drawn from the CDF at a low rate. That churn is a large
part of what keeps the image alive rather than settled.

**Edges.** Dots reflect off the walls rather than clamping to them, and each dot is
repelled by its own mirror image across any nearby wall. Both matter: clamping parks
every arrival on the exact boundary line, and without the mirror ghost the missing
neighbours outside the canvas leave an all-inward push that crusts dots along the edge.

**Neighbour sweep order.** The 3×3 block is walked starting from the dot's own cell,
then around the ring from a rotating offset. Sweeping top-left to bottom-right meant
that whenever the budget ran out a crowded dot had only felt pushes from above and to
its left, and the whole field drifted down and to the right.

## Performance

- Positions and velocities live in flat `Float32Array`s, never objects. The hash's
  `head`/`next` index arrays are preallocated and reused; nothing is allocated per frame.
- Dots are drawn with `fillRect`, which is far cheaper than `arc` at these counts. In
  color mode the `rgb()` strings are quantized to 5 bits per channel and cached, so
  the loop never builds a string.
- The luminance and density maps are recomputed only when the source changes — and
  for video and camera, only every third frame.
- Comfortable defaults are 18,000 dots at 2 sub-steps. 60,000 dots at 4 sub-steps is
  the heavy end and is meant as a quality ceiling, not a default.

## Notes

- Match the dot count to the source. A picture with a small dark subject on a large
  light field cannot absorb 60,000 dots; the surplus has nowhere legitimate to sit and
  shows up as haze. Drop the count, or raise the contrast, and it cleans up.
- **Camera input needs the page to own the camera permission.** It works when
  `index.html` is opened directly over `https://` or `http://localhost` — for example
  `python3 -m http.server` in this folder, then `http://localhost:8000`. It cannot work
  when the sketch is embedded in someone else's page: a cross-origin or sandboxed
  iframe gets no camera unless the embedder sets `allow="camera"`, and the sketch
  cannot grant that to itself. The Start camera button is disabled up front in that
  case and says so. Some browsers also refuse `getUserMedia` on `file://`.
- Camera failures are reported specifically — permission refused, no device attached,
  device busy, or blocked by the embedding page — rather than as a raw error string.
- Video files are decoded by the browser, so the supported formats are whatever the
  browser supports (mp4/H.264 and webm in practice).
