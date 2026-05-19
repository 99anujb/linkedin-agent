# Phase 3 — Engagement Uplift Design

## Goal

Lift LinkedIn post engagement (reposts, comments) without adding new infra
beyond what Phase 2 already uses. Replace the generic Unsplash image with a
topic-relevant generated image rendered at draft time.

Existing pipeline (draft → email → APPROVE → Buffer → LinkedIn) is preserved.
No changes to the Cloudflare Worker or the `post.yml` workflow.

## Out of scope

- Carousel posts / multi-image
- LinkedIn API direct posting (still via Buffer)
- A/B testing harness for caption variants
- Engagement analytics scraping

## Content changes

### Voice guidelines (`prompts.py`)

Rewrite `VOICE_GUIDELINES` and `_TYPE_INSTRUCTIONS` to push toward
repost-friendly format. Concrete deltas vs current:

- **Hook:** 2 short lines maximum, visible above LinkedIn's "...more" fold.
  Must contain a specific claim, a number, or a contrarian take. Must read
  fine in isolation.
- **Format picker:** Claude picks one of `{hot-take, story, list, framework}`
  per topic. Picker is the first step of the caption prompt — Claude outputs
  the chosen format label, then the caption.
- **Whitespace:** blank line every 1–2 sentences. No long paragraphs.
- **CTA:** ends with a question inviting the reader's experience. A soft
  repost prompt is allowed only when it fits the format; no spammy
  "agree? repost!".
- **Length:** 700–1300 characters (tighter than the current 800–1300).
- **No employer names** rule stays.

Format templates live in `prompts.py` alongside the existing constants. Each
format has its own opener and closer skeleton Claude fills in.

### Hashtags

Unchanged. Existing 5–8 mixed-tag JSON-array generator continues to work.

## Image changes

### Picker

After the caption is generated, the agent picks an image strategy based on
`post_type`:

| `post_type`           | Image strategy        |
|-----------------------|-----------------------|
| `project`, `concept`  | Code/data snippet card |
| `career`              | Quote card             |

Quote cards are the safe fallback when snippet generation fails or returns
empty.

### Code snippet card

1. New `generators/snippet.py` calls Claude with the caption + post_type and
   asks for a ≤15-line code/SQL/data snippet illustrating the technical
   concept, plus the language label. Returns `(snippet_text, language)`.
2. `generators/image_card.py::render_code_card(snippet, language)` renders
   the snippet using Pygments' built-in PIL image formatter with a dark
   theme. Output ~1200×675 px, padded, with a title bar showing the
   language label.

### Quote card

1. `image_card.py::render_quote_card(text)` takes the caption's first 2
   lines (the hook).
2. Renders with Pillow: solid gradient background, bold sans-serif text
   centered, footer showing the handle. ~1200×675 px.

### Fallback chain

```
chosen strategy → render → on exception → quote card → on exception → Unsplash (existing image.py)
```

This preserves the current behavior as a final safety net.

## Hosting + Buffer integration

PNG flow per draft:

1. `draft.py` saves the rendered PNG to `db/images/<draft_id>.png`.
2. New helper `delivery/git_publish.py::commit_and_push(paths, message)`
   runs `git add / commit / push` from inside Python. It is a no-op when
   the `CI` env var is unset (so local dev runs don't push).
3. Once pushed, the file is at
   `https://raw.githubusercontent.com/99anujb/linkedin-agent/main/db/images/<draft_id>.png`.
4. That URL is stored in the existing `image_url` column on the draft
   row, embedded in the preview email, and passed to Buffer's GraphQL
   `assets[0].image.url` on APPROVE.

### Race condition

The current `draft.py` sends the email before CI's `Commit updated state
DB` step pushes anything. The image URL would 404 at email-render time.
Fix: call `git_publish.commit_and_push` for the image **before** the email
send, inside the agent process. The existing CI commit step continues to
handle `db/state.sqlite` after the agent exits.

If `commit_and_push` fails, the draft still proceeds — `image_url` stays
empty, the LinkedIn post goes out without media. No regression beyond
losing the image for that one post.

## Configuration

- `GITHUB_RAW_BASE` — new setting in `config.py`, default
  `https://raw.githubusercontent.com/99anujb/linkedin-agent/main`. Used to
  build raw URLs without hardcoding the owner/repo throughout.

## Code structure

### New files

- `src/agent/generators/snippet.py` — Claude call → `(snippet_text, language)`.
- `src/agent/generators/image_card.py` — `render_code_card`,
  `render_quote_card`, `pick_and_render(post_type, caption, snippet)`.
- `src/agent/delivery/git_publish.py` — `commit_and_push(paths, message)`.
- `assets/fonts/` — bundle one sans-serif font file (Inter Regular + Bold)
  to avoid runtime font discovery on the runner.
- `scripts/preview_card.py` — render sample code and quote cards locally
  to `tmp/preview_*.png` for visual eyeballing.

### Modified files

- `src/agent/generators/prompts.py` — new voice guidelines + format
  picker step.
- `src/agent/draft.py` — call snippet (when applicable) → render card →
  save PNG → commit + push → set `image_url` → email. Unsplash fallback
  inside a `try/except`.
- `src/agent/config.py` — add `GITHUB_RAW_BASE` setting.
- `requirements.txt` — add `Pillow` and `Pygments`.

### Unchanged

- `src/agent/generators/image.py` — kept as Unsplash fallback.
- `.github/workflows/draft.yml` and `post.yml` — unchanged.
- `worker/approval.js` — unchanged.

## Testing

### Unit tests (TDD)

- `test_snippet.py` — Anthropic mocked. Asserts returned tuple shape,
  handles malformed/empty response with retry, asserts language hint
  parsing.
- `test_image_card.py` — calls both renderers with sample inputs, asserts
  output bytes start with PNG magic (`\x89PNG`), asserts dimensions match
  the configured size.
- `test_image_card_picker.py` — `pick_and_render` dispatches correctly per
  `post_type`, falls through to quote on render failure.
- `test_git_publish.py` — subprocess mocked. Asserts correct git command
  sequence, asserts no-op when `CI` env unset.
- `test_draft_pipeline.py` — extended to assert image flow ends with
  `draft.image_url` pointing to a `GITHUB_RAW_BASE`-prefixed URL, and
  that Unsplash fallback triggers when both renderers raise.
- `test_prompts.py` — asserts new voice guidelines text present, format
  picker step present in the message.

### Smoke / preview

- `scripts/preview_card.py` renders three sample cards locally so the
  user can eyeball the design before merging.

## Risk mitigations

- **Font discovery:** bundle Inter (Regular + Bold) under `assets/fonts/`,
  load by absolute path. No reliance on system fonts.
- **Image render failure:** Unsplash fallback preserves current behavior.
- **Git push failure:** caught in `draft.py`, `image_url` stays empty,
  post still goes out without media.
- **Claude returns nonsense snippet:** snippet generator retries once,
  then surfaces an empty snippet; the picker then falls back to quote
  card.

## Done criteria

- Next morning's cron email shows the new voice + a generated image
  embedded inline.
- After APPROVE, the LinkedIn post displays the generated PNG and the new
  caption format.
- Visual eyeball confirms the image is on-brand (legible code or quote,
  no blank renders, no broken fonts).
- Repost and comment counts trend up over 7 days. Measured manually by
  the user, not automated.

## Rollout

Branch off `main`: `phase-3-engagement`. Steps in order:

1. Voice / prompts rewrite.
2. Quote card renderer.
3. Code snippet generator + render.
4. Picker + `draft.py` integration + `git_publish` helper.
5. Tests + preview script.
6. Merge → trigger `draft.yml` manually → eyeball email → APPROVE →
   verify LinkedIn post.
