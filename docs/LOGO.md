# Logo direction

> Locked artwork goes in `app/icon.png` (1024×1024) and `app/icon.icns` (multi-resolution Mac bundle).
> This file is the design brief.

## Concept

Booth is "the radio booth your AI broadcasts from." The icon should evoke: a small vintage broadcast booth, the ON AIR red-light sign, the warmth of analog radio. Not a microphone (we ship to one — we are not one). Not a generic chat bubble.

Cohesive sibling to Claudible: same warm orange background, same illustrated beige/cream rendering style, similar lighting. Reads as "the same author made these two."

## Style spec

- **Format:** 1024×1024 PNG → ICNS pipeline. Rounded square corner radius matching macOS icon norms.
- **Vibe:** soft illustrated, modern flat with subtle shading. Not pixel art. Not photorealistic.
- **Background:** warm orange gradient `#ff8c4d` → `#ff6b35` (matches Claudible's bg).
- **Subject:** a small beige (`#f5e6cc`) vintage broadcast scene. Pick one of:
  - **Option 1:** An ON AIR rectangular sign with a glowing red dot.
  - **Option 2:** A retro radio mic on a stand, soft drop shadow.
  - **Option 3:** A small radio booth window with a person silhouette inside (more illustrative).
- **Accent light:** a single `#3aff3a` green LED somewhere on the subject — keeps the "live" feel and bridges to Booth's "I am on" indicator semantics in the menu bar.

## Menu bar template (separate file)

`app/menubarTemplate.png` — 22×22 black-on-transparent monochrome. macOS auto-inverts in dark mode. The shape: minimal silhouette of the chosen subject. Strict 1px stroke, no fills.

## What it should NOT look like

- ❌ A glowing brain
- ❌ A speech bubble
- ❌ A waveform
- ❌ A neural-network node graph
- ❌ Anything with the word "AI" in the icon
- ❌ A microphone alone with no booth context (too generic)

## Reference touchstones

- The classic ON AIR neon/light sign in any film about radio
- The warm illustrated style of modern macOS dock icons (Mail, Messages, Music)
- The Claudible icon, for direct sibling-app cohesion
