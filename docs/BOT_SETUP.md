# Telegram Bot Setup (5 minutes)

If you already have a Telegram bot, skip this. You just need the bot token to paste during install.

## 1. Talk to BotFather

1. Open Telegram on your phone or desktop.
2. Search for `@BotFather` and start a chat with the verified one (blue checkmark).
3. Send `/newbot`.
4. BotFather asks for a **name** — what appears in chats. Anything works. Example: `Pager`.
5. BotFather asks for a **username** — must end in `bot`. Example: `my_pager_bot`.
6. BotFather replies with a **token** that looks like `1234567890:AAH...`. **Copy it**. This is what you paste during Pager install.

## 2. Start a chat with your bot

1. Open the link BotFather sent you (`t.me/your_username_bot`) or search for the username.
2. Hit **Start** at the bottom of the chat.
3. Send any message (e.g. "hi") so the bot has a chat ID to find you on.

## 3. Find your chat ID

The Pager listener will pick this up automatically the first time you message your bot, but if you want to lock the allowlist before running, you can grab it manually:

```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
```

Look for `"chat":{"id":12345678,...}` in the JSON. That number is your chat ID.

Add it to the allowlist:

```bash
echo "12345678" >> ~/.local/share/pager/allowlist
```

Without an allowlist entry, your bot will silently reject all incoming messages — that's the security default.

## 4. Optional: bot picture and description

Back in BotFather:

- `/setuserpic` — upload an avatar (your AI agent's logo)
- `/setdescription` — short description shown above the chat
- `/setabouttext` — longer "about" shown when someone taps the bot's profile

These don't affect functionality but they make the bot feel real.

## Troubleshooting

- **Bot doesn't respond at all:** check `~/.local/share/pager/listen.log`. Common cause: no allowlist entry for your chat_id.
- **Voice notes arrive but don't transcribe:** check whisper-cpp install (`which whisper-cli`) and the model file at `~/.local/share/whisper/ggml-base.en.bin`.
- **Voice bubbles don't render correctly on the recipient end:** Telegram needs Opus OGG, not WAV. Confirm `which opusenc` returns a path.
- **"Conflict: terminated by other getUpdates request":** another listener is polling the same bot. Stop one of them.

## Why a fresh bot is best

Don't reuse a bot you already have hooked into another tool — Telegram only delivers each update to one `getUpdates` consumer. Two listeners on the same token will fight and drop messages randomly. New bot per integration.
