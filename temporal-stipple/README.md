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
| **Subject: Off / Plate / Focus / Center** | Which part of the source is allowed to hold dots. See *Isolating a subject* below. |
| **Capture background** | Plate mode only. Counts down three seconds, then freezes the current frame as the reference background. |
| **Cutoff / Edge softness** | Matte threshold and how hard its edge is. In Center mode, cutoff is the radius. |
| **Show matte** | Tints the dropped region so the matte can be tuned by eye. The readout beside it says how much of the frame is kept. |
| **Export 1× / 2× / 4×** | Multiplier for the PNG export, relative to the on-screen size. |
| **PNG** | Saves what you see, re-rendered at the chosen scale. |
| **HTML** | Saves a standalone copy of this sketch with the current settings as its defaults. |
| **Copy settings** | The current parameters as a JS object literal. |
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

## Isolating a subject

The goal is the iPhone effect: only the person in front of the camera becomes
dots, everything behind them drops out. What the phone does is *semantic
segmentation* — a neural network that knows what a person is. It does not look
at focus, and it needs a model of a few megabytes. Nothing here loads a model:
the file stays self-contained, and an artifact-hosted copy could not fetch one
anyway. So the sketch offers three cheap proxies instead, each good in a
different situation.

**Plate** — background subtraction. Point a fixed camera at the empty scene,
press *Capture background*, step in. Every pixel is compared to the reference
frame in RGB; what changed is the subject. Two blur passes close the small holes
where a subject happens to match the wall behind it, and feather the silhouette.
This is the one to use for a webcam: it is exact, instant, and gives a crisper
edge than a segmentation model would. It needs the camera and the lighting to
hold still — bump the tripod and you re-capture.

**Focus** — local high-frequency energy. An in-focus region carries fine detail;
a defocused one is smooth. Blur that detail map into regions and threshold it.
This works on photographs that already have real depth of field — a portrait
from a phone or an SLR. It will not help with a webcam, which has everything in
focus from 30cm to the far wall, and it will not help with a flat graphic.

**Center** — a radial falloff. No subject detection at all, just a spotlight.
Useful when neither of the others applies and you want the frame to fade out.

The matte multiplies the density field, so a dropped region holds no dots at
all rather than fewer — the CDF floor is masked too. If a matte ends up keeping
nothing, seeding falls back to uniform placement and the stray recycler stands
down, so the sketch degrades quietly instead of piling every dot in one corner.

## Exporting

**PNG** re-renders the current frame into an offscreen canvas at 1×, 2× or 4× the
on-screen size — 4× on a large window is around 3600px square, enough to print.

**HTML** writes a standalone copy of the whole sketch with the current settings
baked in as its defaults, so you can hand someone a single file that opens
looking exactly like your screen. It is rebuilt from the sketch's own style,
markup and script rather than from `document.outerHTML`, so nothing belonging to
an embedding host is carried along, and the transient UI state (which input mode
you were in, what the hints said) is reset in the copy.

**Copy settings** gives the parameters alone, as a JS object literal.

Saving takes whichever route the page actually has. Opened locally it is a plain
download. In the claude.ai artifact viewer a page may never start its own
download, so the page asks for the `downloads` capability and the viewer confirms
each save. In any other embedding — a cross-origin iframe elsewhere — neither
route exists and the host drops the download silently, so the buttons open a
panel with the image or the code in it, to save or copy by hand. The exported
standalone copy carries the same logic and falls back to the plain download.

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
- Ships at 21,000 dots, 4.5px, 2 sub-steps — a bold, poster-like setting where the
  dots merge into solid black in the shadows. For a finer, more classical stipple,
  drop the dot size toward 1.5 and raise the damping. 60,000 dots at 4 sub-steps is
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
