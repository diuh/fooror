# Fooror — design system

Built in Figma from the desktop macket, then mirrored here as tokens.
Figma file `CHI3cmn5hgf3KleaFW5mdX`, page **◆ Design System**.

## What is in Figma

| | |
|---|---|
| Variable collections | 4 — Primitives, Color, Spacing, Sizing |
| Variables | 40, every one scoped and carrying `var()` code syntax |
| Text styles | 16 — Display ×5, Label ×5, Body ×6 |
| Components | 16 sets / 46 variants |
| Hardcoded colours in components | 0 |

## Decisions worth knowing

**The typeface changed.** The macket was set in Nimbus Sans and Nimbus Sans Cond L.
Neither exists in Figma's cloud catalogue — `loadFontAsync` fails outright, and a scan of
all 1939 available families returns no match for nimbus, urw or helvetica. They are local
fonts on the designer's machine. Replaced everywhere with **Archivo Narrow** (display and
labels) and **Archivo** (body): one superfamily, on Google Fonts, so Figma, the site and
any future collaborator all resolve the same thing.

**Leading is 90% on everything**, body copy included. Verified against every text node in
the macket, not assumed.

**Tracking follows the size, in percent**: display −4%, uppercase labels at 20/24/32 −5%,
everything else −2%. Percent rather than pixels, so it holds at any size.

**Labels are always uppercase.** The condensed bold face is only ever used uppercase in the
macket; the text styles enforce it rather than leaving it to whoever types the layer.

**Two radii, nothing between**: 0 and pill.

**Page structure**: the ground is the plate `#E5E5ED`; sections are white bands 1880 wide
inset by a 20px gutter; content sits in a 1168 column at 376 margins.

**Spacing keeps numeric names** — 10, 12, 20, 24, 30, 32, 40, 50, 60, 80, 120, 160. The steps
are irregular, so `xs/sm/md` would imply a ratio that is not there.

## Defects found in the macket

- The `icons` set (`50:847`) had `arrow-down`, `arrow-up`, `arrow-right` and `arrow-left` all
  containing the **same** `corner-right-down` glyph. Four of five were duplicates. The new
  Icon set uses real Tabler outline geometry.
- Two duplicate `Button` component sets (`30:69`, `51:1020`), variants named
  `Property 1=Default` / `Variant2`. Superseded by the new Button — safe to delete, left in
  place pending the owner's go-ahead.
- Footer copy reads "All Rights Reserver". Corrected to "All rights reserved" in the component.
- No drop shadows exist anywhere in the macket; `rgba(0,0,0,.2)` is faded text in the
  testimonial carousel, so it is a text token (`text/faded`), not an effect style.

## Still to do

Mobile and tablet frames — the macket is desktop-only at 1920. Page layouts for work, case,
journal, article, services, service, contact, about, legal and 404.
