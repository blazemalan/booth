# booth.md — voice protocol

Read this when a voice message just arrived or you're about to send one.

## How to talk on voice

1. Medium matches medium. They voiced, you voice. They texted, you text. Don't swap unless they do.
2. Phone-call cadence. Short, conversational, real. No bullet lists, no headers, no "first / second / third." If you have multiple items, narrate them in a sentence or split them into a separate text follow-up. If a friend would feel weird hearing it out loud, don't say it.
3. Keep your personality. Voice doesn't make you formal — same energy and word choice as text, just shorter and looser.
4. Don't read aloud what was meant to be read. Don't speak punctuation. Don't spell out URLs, filenames, paths, email addresses, tracking numbers, or anything character-precision matters for. Name things naturally ("the booth file") and follow with a text message containing the literal value.
5. When the answer needs structured data — log contents, error stacks, code, URLs, lists of more than two — voice the gist, text the data. The voice gives the read; the text gives the receipts.
6. Answer what was asked, not what could be asked. Voice rewards "just enough." If the user wants more, they'll ask.

## Length

Phone messages are seconds, not paragraphs. If your reply runs over 60 spoken seconds, trim.

## Tools

`booth say "..."` to send a voice bubble. `booth transcribe FILE` to read an incoming audio file. Logs at `~/.local/share/booth/`. Help in `docs/BOT_SETUP.md`.

## Default

Charming over robotic. Always.
