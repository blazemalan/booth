# Telegram Bot Setup (5 minutes)

If you already have a Telegram bot wired into your MCP bridge (Claude Code Channels, OpenClaw Telegram, etc.), **use the same token for Booth**. Booth doesn't poll Telegram — it only sends voice and transcribes audio you hand it — so it doesn't conflict with whatever's already polling.

If you don't have a bot yet:

## 1. Talk to BotFather

1. Open Telegram on your phone or desktop.
2. Search for `@BotFather` and start a chat with the verified one (blue checkmark).
3. Send `/newbot`.
4. BotFather asks for a **name** — what appears in chats. Anything works. Example: `Booth`.
5. BotFather asks for a **username** — must end in `bot`. Example: `my_booth_bot`.
6. BotFather replies with a **token** that looks like `1234567890:AAH...`. **Copy it.** This is what you paste during Booth install (and what you'd give your MCP bridge plugin).

## 2. Start a chat with your bot

1. Open the link BotFather sent (`t.me/your_username_bot`) or search for the username.
2. Hit **Start** at the bottom of the chat.
3. Send any message (e.g. "hi") so the bot has a chat to send back to.

## 3. Find your chat ID

`booth say` needs to know which chat to send voice bubbles to. Get your chat ID:

```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
```

Look for `"chat":{"id":12345678,...}` in the JSON. That number is your chat ID.

> If your MCP bridge is actively polling, this `getUpdates` call may return empty results because the MCP already consumed them. In that case, send a fresh message and check your MCP plugin's logs — it usually exposes the chat ID there. Or temporarily stop the bridge, run getUpdates, then restart.

Drop the chat ID into Booth's default destinations file:

```bash
echo "12345678" >> ~/.local/share/booth/chat_ids
```

That's it. From then on, `booth say "hello"` defaults to sending there. You can override with `--chat-id`.

## 4. Optional: bot picture and description

Back in BotFather:

- `/setuserpic` — upload an avatar (the Booth logo lives in the repo at `app/icon.png`)
- `/setdescription` — short description shown above the chat
- `/setabouttext` — longer "about" shown when someone taps the bot's profile

## Troubleshooting

- **`booth say` errors with "No default chat configured":** add a chat ID to `~/.local/share/booth/chat_ids` per step 3.
- **Voice bubble arrives as an audio document instead of a round bubble:** Telegram needs Opus OGG, not WAV. Confirm `which opusenc` returns a path; if not, `brew install opus-tools`.
- **`booth transcribe` fails:** check whisper-cpp install (`which whisper-cli`) and the model file at `~/.local/share/whisper/ggml-base.en.bin`.
- **Telegram returns "Conflict: terminated by other getUpdates":** something else is polling your bot. Booth itself never polls — this is an MCP bridge issue, not Booth's. Make sure only one bridge process is running.

## Architecture note

Booth deliberately does NOT call `getUpdates` on your bot. That's the job of whichever MCP bridge you're using. Booth only:

- POSTs to `sendVoice` (outbound) — doesn't conflict with anything
- Receives audio file paths from your agent (which got them via the MCP bridge's `download_attachment` or equivalent) and transcribes them locally

This is intentional, so you can keep using your existing chat bridge unchanged.
