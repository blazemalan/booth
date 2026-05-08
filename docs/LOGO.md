# Logo direction

> Locked artwork goes in `app/icon.png` (1024×1024) and `app/icon.icns` (multi-resolution Mac bundle).
> This file is the design brief.

## Concept

A 1990s belt-clip pager, pixel-art style, with a glowing green LED and a single line of text on the screen.

The tone is "I am not impressed by AI hype, I just need the buzz." Dry, retro, confident. The audience is people who've seen too many AI launch videos with neural-network swooshes; they'll respond to something that feels like it was designed by someone who's already over the trend.

## Style spec

- **Format:** square, 1024×1024 SVG → PNG → ICNS pipeline
- **Vibe:** chunky pixel art, low color count
- **Palette:**
  - Background: `#0a0a0a` (matches cinder.works dark)
  - Pager body: `#1a1a1a` outline / `#222` body fill
  - Screen: `#0e1f0e` recessed, with `#3aff3a` text and a soft bloom
  - LED: `#3aff3a` solid, with `#aaffaa` core highlight
  - Accent rim (optional): `#ff6b35` ember (cinder-works brand bridge)
- **Pager screen text:** `PAGER` or single-line message — `MSG FROM CINDER` works as an in-joke variant for screenshots
- **Antenna:** stubby, slightly bent, suggests "this thing has been to war"
- **No gradients on the body.** Flat shapes only. The LED gets a small bloom.

## Menu bar template (separate file)

`app/menubarTemplate.png` is a 22×22 black-on-transparent monochrome glyph used in the macOS menu bar. macOS auto-inverts it for dark mode. The shape: pager silhouette with the LED dot. Strict 1px stroke.

## What it should NOT look like

- ❌ A glowing brain
- ❌ A speech bubble
- ❌ A waveform
- ❌ A neural-network node graph
- ❌ Anything with the word "AI" in the icon
- ❌ A microphone (we ship to one — we are not one)

## Reference touchstones

- The Motorola Bravo Plus (mid-90s alphanumeric pager)
- The minimal LED on early PalmPilots
- The Macintosh System 7 "Welcome to Macintosh" cleanness
- The bone-dry industrial design of a Casio F-91W
