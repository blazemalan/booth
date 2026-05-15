# Booth as a Claude Code plugin — design doc

**Status:** draft for Blaze's review, 2026-05-15
**Author:** Cinder
**Companion:** `install.sh` (current installer), `scripts/booth_hook.sh` (current UserPromptSubmit hook), `booth.md` (current voice protocol)

---

## Why this doc exists

The current Booth install wires a `UserPromptSubmit` hook that injects `booth.md` into the agent's context when a voice message is detected in the inbound prompt. That works for first-turn voice messages typed by a user, but it **does not work for the common case**: voice messages that arrive via the official Telegram plugin while the Claude Code agent is already running a tool call.

A failed earlier fix tried bundling `booth.md` content into `~/.claude/CLAUDE.md` for always-on loading. That was reverted in commit `f3527a1` because the token cost lands on every Claude Code session, including text-only work that never touches voice. Blaze's call, correctly: that trade isn't worth it.

This doc is the plan for solving bug 2 the right way: package Booth as a Claude Code plugin so the voice protocol loads **only in projects that have Booth enabled** — not globally for every session.

---

## Key technical finding (verified by reading the official Telegram plugin source)

The official Telegram plugin at `~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.6/` is an **MCP server**, not a hook bundle. Its full structure:

```
.claude-plugin/      # plugin metadata (manifest)
.mcp.json            # declares the MCP server entry point
server.ts            # the MCP server itself (1061 lines)
skills/access/       # /telegram:access skill
package.json         # bun-managed deps (grammy + @modelcontextprotocol/sdk)
README.md
```

The critical mechanism (server.ts:986-1006):

```typescript
mcp.notification({
  method: 'notifications/claude/channel',
  params: {
    content: text,
    meta: {
      chat_id, message_id, user, user_id, ts,
      ...(imagePath ? { image_path: imagePath } : {}),
      ...(attachment ? {
        attachment_kind: attachment.kind,        // "voice" for voice messages
        attachment_file_id: attachment.file_id,
        attachment_size, attachment_mime,
      } : {}),
    },
  },
})
```

When a voice message hits Telegram, the plugin emits a **`notifications/claude/channel` MCP notification**. Claude Code renders this as a `<channel source="..." attachment_kind="voice" ...>` block in the agent's context on the agent's next turn. **This is not a hook event.** There is no hook that fires on channel notifications.

That's why our existing `UserPromptSubmit` hook can never catch mid-task voice — the hook isn't on the right surface.

**Equally important finding:** MCP servers ship an `instructions` field in their initialization (`new Server({}, {instructions: '...'})`). Those instructions are loaded into the agent's context **when the MCP server is registered** — which happens at session start, but only for projects that have the plugin enabled. That is the right scope for Booth's voice protocol.

---

## Plugin architecture (proposed)

```
booth/                              # plugin root
├── .claude-plugin/
│   └── plugin.json                 # name, version, description, author
├── .mcp.json                       # registers the "booth" MCP server
├── server.ts                       # booth MCP server (TypeScript + bun)
│                                   # provides tools: booth_say, booth_transcribe,
│                                   # booth_status, booth_voices
│                                   # ships voice protocol in `instructions` field
├── bin/
│   └── booth                       # CLI binary (the same one as today, but
│                                   # plugin's bin/ is auto-added to PATH by
│                                   # Claude Code when plugin is enabled — no
│                                   # more settings.json env.PATH hack)
├── scripts/                        # existing helper scripts kept
├── booth.md                        # voice protocol — feeds server.ts instructions
├── package.json                    # bun deps: @modelcontextprotocol/sdk
└── README.md                       # public-facing readme (unchanged)
```

### Flow when a voice message arrives mid-task

1. Telegram plugin's `bot.on('message:voice')` fires (no change — existing infra)
2. Telegram plugin emits `notifications/claude/channel` with `attachment_kind="voice"` (no change)
3. Claude Code renders the `<channel>` block in the agent's context (no change)
4. **NEW**: Because Booth plugin is enabled in this project, the agent has already loaded Booth's MCP `instructions` at session start — meaning the voice protocol is in context whether the agent looks back at it or not.
5. **NEW**: The agent sees the channel block, knows from Booth's instructions that voice means "use `booth_transcribe` then reply with `booth_say`," and proceeds.

No hooks needed. No mid-task injection needed. Voice protocol is just *there* for projects that opted in.

### Tools the booth MCP server provides

| Tool | Purpose |
|------|---------|
| `booth_transcribe` | Wrap whisper.cpp. Takes file_id or path, returns transcript. |
| `booth_say` | Wrap TTS (Kokoro or ElevenLabs). Sends voice bubble back via Telegram. |
| `booth_status` | Daemon health, model paths, current backend. |
| `booth_voices` | List available voices (kokoro voices + ElevenLabs library). |

`booth_say` would internally call the Telegram MCP's `reply` tool — OR shell out to `booth say` which already handles the multi-bot dispatch. Cleanest is shell-out; the CLI stays the source of truth.

---

## Token economics

| Approach | Token cost | Scope |
|----------|-----------|-------|
| Current `UserPromptSubmit` hook | ~0 always-on; ~600 per voice trigger | All sessions, but only fires on first-turn voice (bug 2) |
| CLAUDE.md injection (reverted) | ~1500 every session, every project | All sessions, every project |
| **Plugin MCP `instructions`** | **~1500 only in projects with plugin enabled** | **Opt-in per project** |
| Plugin + lazy skill (alternative) | ~150 always-on (tool descriptions), full protocol loads only when skill invoked | Opt-in per project, smaller always-on cost |

The plugin's "instructions" approach IS always-on within a project, but the project has to opt in. That maps to user intent — "I want voice in this project" — much better than the global CLAUDE.md.

If the ~1500 token cost is still too high, the lazy-skill variant (tool descriptions point at `/booth:respond` skill that loads protocol on demand) drops always-on to ~150 tokens. Tradeoff: agent might miss a voice protocol nuance if it doesn't invoke the skill on the very first voice message.

**Recommendation:** ship the instructions-based approach in V0. Measure actual usage. Only build the lazy-skill variant if the ~1500-token-per-voice-project cost becomes a real complaint.

---

## Implementation phases

### V0 — Plugin parity with today's install (1 day)

- Convert booth into the plugin directory shape above (`.claude-plugin/`, `.mcp.json`, `server.ts`, `bin/booth`)
- Port the existing `booth` CLI into `bin/booth` (unchanged binary, new location)
- Build minimal `server.ts` that:
  - Declares the MCP server with `booth.md` content in `instructions`
  - Exposes `booth_transcribe` and `booth_say` as MCP tools that shell out to the CLI
- Test locally via `claude --plugin-dir /path/to/booth`
- Verify: a voice message during a tool call now triggers the agent to use `booth_transcribe` correctly with no hook

### V1 — Marketplace publish + install path simplification (0.5 day)

- Publish to the Claude Code plugin marketplace (if eligible) OR ship a `claude plugin add <github-url>` install path
- Simplify `install.sh`:
  - Keep the local `~/.local/bin/booth` symlink for non-Claude-Code agents (Codex CLI, custom)
  - Remove the `~/.claude/settings.json` env.PATH merge from V9b (replaced by plugin's `bin/`)
  - Remove the `scripts/install_claude_hook.sh` flow (replaced by plugin's MCP instructions)
- Update README with new flow: "Claude Code users — `/plugin install booth`. Other agents — `curl | bash` the legacy installer."

### V2 — Lazy skill variant if needed (0.5 day, optional)

- Only build if V0/V1 reveal the always-on instructions cost is a real problem
- Move protocol body into `skills/respond/SKILL.md`
- Trim `instructions` field to a stub pointer (~150 tokens)
- Document trade-off in README

---

## Migration: how `install.sh` changes

**Before plugin lands** — no change. Beta testers run `curl | bash` as documented.

**After plugin lands**:

- README's Claude Code section becomes: "Install Booth as a Claude Code plugin: `/plugin install booth` (or wherever the marketplace command lives). The plugin includes the CLI binary, voice protocol, and MCP tools."
- The legacy `install.sh` stays for non-Claude-Code users (the README is clear it's a fallback).
- The legacy hook (`install_claude_hook.sh`) is deprecated with a note pointing to the plugin.

We don't break any existing installs. Old installs keep working via the hook. New users get the better experience via the plugin.

---

## Open questions / risks

1. **Does Claude Code's plugin marketplace accept third-party plugins yet?** If not, the install path is `claude plugin add <github-url>`, which is a worse UX but functional. **Action:** verify before V1.

2. **Does Claude Code's plugin runtime auto-add `bin/` to PATH for tool calls?** Strong assumption based on the research, but not yet verified by reading the actual plugin loader code. **Action:** verify in V0 spike by building a minimal plugin with a `bin/hello` binary and confirming `bash -c 'hello'` works in a Claude Code session.

3. **What's the cost of running two MCP servers (Telegram + Booth) on session start?** They both spawn `bun` processes. RAM and startup latency could compound. **Action:** measure in V0 — if it's bad, consider a shared daemon process.

4. **Can the Booth MCP server emit its own `notifications/claude/channel` augmentations?** E.g., when voice arrives, the Telegram plugin emits the raw channel block, and Booth's MCP server could emit a follow-up notification with "voice detected — protocol active." This is an alternative path to the always-on instructions approach. **Action:** investigate if MCP servers can listen to other servers' notifications. Probably not — but worth checking.

5. **Versioning the protocol.** If `booth.md` changes, projects pinned to an older plugin version get stale protocol. **Action:** standard semver discipline + a `/booth:version` skill so the user can spot drift.

---

## Decision points for Blaze

Before V0 kicks off, I want explicit go on:

1. **Plugin or no plugin?** Confirm we're committing to this path vs accepting the current hook-only limitation.
2. **Instructions-based vs lazy-skill variant for V0?** I recommend instructions-based — ~1500 tokens per opted-in project, simpler to ship. Tell me if you want lazy-skill from the start.
3. **TypeScript / bun for the MCP server?** The Telegram plugin uses bun + grammy. We'd match. If you prefer Python, we'd need to rebuild on the python MCP SDK, which is a more significant lift.
4. **Maintain back-compat for `curl | bash`?** I assume yes — non-Claude-Code agents (Codex, custom) still need the legacy installer. Confirm.

Once those are answered, V0 is roughly a day of focused work. V1 is half a day. V2 is optional and conditional on observed problems.

— Cinder
