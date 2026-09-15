---
description: 'Record a UI flow as a video artifact for human reviewers — a ticket or PR reviewer asking "can I see it work", a multi-step flow where screenshots cannot show the interaction, a demo for a manager. Drives the flow with the project''s own Playwright setup, forces video on for just that run (test.use, no config edits), slows actions to human-followable pacing (slowMo 1000-1500ms with the timeout resized to match), then post-processes: trims the blank first-paint lead-in and verifies the first frame, gates pacing with ffprobe, and lands the file in the project''s artifact convention with a plain-text step-by-step walkthrough derived from the spec that actually ran. Optional: --mp4 (universally previewable H.264 copy), --headed (watch live), --keep-spec (keep a throwaway spec as permanent coverage). Complements /bymax-web-verify:verify (screenshots) — one extra artifact, not a replacement. Triggers: "record a video of this flow", "video evidence", "record the flow", "gravar um video do fluxo", "video do teste", "/bymax-web-verify:record".'
argument-hint: "[flow-description] [--mp4] [--headed] [--keep-spec]"
---

# /bymax-web-verify:record — record a UI flow as reviewable video evidence

Screenshot tools cannot show *interaction* — a reviewer watching a multi-step flow
needs to see each click land. Playwright can record video; this command uses the
**project's own Playwright setup**, forces recording on for a single run, and turns
the raw capture into something a human can actually follow. The deliverable is
three things together: the video, the walkthrough text (Step 7), and a PASS/FAIL
report — a silent screen recording alone is not a deliverable.

**When NOT to use:** the flow is trivial to screenshot (use
`/bymax-web-verify:verify`); the change is API-only (no UI to film); the project
has no Playwright and adding it is out of scope — say so and stop, never bolt a
new E2E stack onto a repo to produce one video.

## Step 0 — Discover the project's setup (read, don't assume)

1. **Playwright config** — find `playwright.config.(ts|js|mjs)`. Read from it:
   `testDir` (where specs live), `outputDir` (scratch for artifacts), the current
   `video` setting, and the `projects` list — for the project you will run:
   its `testMatch`/`testIgnore` (Step 2's copy must still be matched), and its
   authentication wiring — a `setup` project only *writes* the state file; what
   makes a run authenticated is the selected project declaring
   `use.storageState` plus a dependency on that setup. Read both ends before
   assuming a session exists. No config → report what is missing and stop.
2. **Dev servers** — same discovery as `/bymax-web-verify:test`: map the layout
   (single app or monorepo), read each `package.json` for the dev script, note
   ports from `.env`/config. If the config has a `webServer` block, Playwright
   manages the server itself — skip Step 1 entirely.
3. **Artifact convention** — where does this repo keep review evidence? Reuse an
   existing tracked `artifacts/`-style directory and its naming if one exists;
   otherwise default to `artifacts/<YYYY-MM-DD>-<flow-slug>/`.
4. **Tooling** — `ffmpeg`/`ffprobe` on PATH? Without them Step 5's trim and pacing
   gate degrade (publish raw, with a warning and the install hint) — say so up
   front, not after recording.
5. **The flow** — from the arguments if given, else from conversation context,
   `git diff --stat`, or the ticket's acceptance criteria. Write the golden-path
   steps as a numbered list *before* touching anything — it becomes the test
   plan and the Step 7 narration.

## Step 1 — Servers (only when the config has no `webServer`)

Follow the project's own dev-server rules (CLAUDE.md / AGENTS.md) if stated.
Otherwise, the same lifecycle as `/bymax-web-verify:test`: probe the discovered
port first — a **healthy listener is reused**, never killed (it may be the
user's own server); an unhealthy or unidentified listener is reported and the
user decides — this command never terminates a process it did not start. Only
on a free port: launch the discovered dev script(s) with
`run_in_background: true` and poll readiness with a capped loop — never a blind
sleep. Step 6 kills exactly the processes this command started, nothing else.

## Step 2 — Locate or create the spec

1. Search `<testDir>` for a spec already covering the flow. **Never edit an
   existing spec in place for a recording** — the `test.use` video/`slowMo`
   overrides, the raised timeout and the final hold are recording-only edits
   that would otherwise be left behind, permanently slowing that test. Copy the
   spec into `<testDir>/.record-tmp/<run-id>/` (fixing relative imports for the new
   depth), apply
   the recording overrides to the copy, and delete it in Step 6 like any other
   throwaway. The original stays byte-identical. In the copy, keep **only the
   intended test** (plus the imports/hooks it needs) — sibling tests would run
   too, slowly and with their own side effects, and produce extra videos; if
   trimming them out is impractical, add `-g '<exact test title>'` to the Step 3
   run so only the intended test executes. While editing the copy, wrap each
   golden-path step in `test.step('<n>. <description>', …)` if the original
   didn't — Step 6's per-step statuses are read from the reporter, and an
   uninstrumented copy leaves it nothing to read (in which case report at test
   level and say so, never invent step statuses).
2. If none exists, decide the spec's fate **now**:
   - **Throwaway** (evidence only) → write it under `<testDir>/.record-tmp/<run-id>/<slug>.spec.ts`
     — a per-run directory, so overlapping recording sessions cannot delete each
     other's specs — removed in Step 6.
   - **Permanent coverage** (`--keep-spec`, or the flow verifies a new feature
     that deserves regression coverage) → write the **clean** spec at its real
     location, obeying the project's E2E conventions (fixtures/seeds committed
     alongside — check the repo's own rules; "it's just for the video" is not an
     exemption) — then record from a `.record-tmp/<run-id>/` copy exactly as in
     item 1. The permanent spec never carries recording overrides.
3. Force video and human pacing **in the temp copy only** — whatever the spec's
   origin, the overrides live and die with `.record-tmp/<run-id>/`; no config
   edits, no permanent spec touched:

   ```ts
   import { test, expect } from '@playwright/test';
   test.use({ video: 'on', launchOptions: { slowMo: 1500 } });

   test('...', async ({ page }) => {
     test.setTimeout(180_000); // slowMo is real wall-clock per action — the default 30s dies fast
     ...
     await page.waitForTimeout(2000); // hold the final state so the ending isn't cut mid-read
   });
   ```

   `slowMo` inserts a real pause after every action, so the recording shows each
   click and fill landing instead of jump-cutting between static states.
   **1000–1500 ms** is the range a non-technical viewer can follow; 300–500 ms
   still reads as "too fast" once someone tries to track individual form fields.
   Size `test.setTimeout` to the step count — `slowMo` time is added to every
   single action.
4. **Authentication:** reuse the stored session when the selected project
   declares `use.storageState` (verified in Step 0.1) — never re-implement
   login. When the flow *is* login, remember **the camera sees what is typed**:
   the account identifier filled into the form is published in the footage, and
   no caption redaction removes it. Record login only with an account whose
   identifier is synthetic and non-sensitive; if the only available account
   carries a real address, start from the stored session instead and list login
   under "not in this video". Credentials come from the project's env/helpers;
   never reconstruct them through shell interpolation (`grep`/`cut`/`$(...)`) —
   test passwords may carry shell metacharacters that corrupt silently in a
   round-trip.
5. **Click-only navigation:** the only direct `page.goto()` is the flow's true
   entry point. Every other screen is reached by clicking, as a user would. If no
   clickable path exists to a required screen, stop and record it as a gap — a
   `goto()` around it would hide an unreachable feature and defeat the evidence.
6. **`waitForURL` needs a trailing `**`.** Pages that sync tabs/filters into the
   query string on load make `page.waitForURL('**/orders')` wait forever — the
   URL stops literally ending in `/orders` faster than a `slowMo` run can catch
   it, while an un-slowed run may race past and pass. The bug therefore *appears*
   when you add `slowMo` and reads as a `slowMo` problem; it is not. Always
   `page.waitForURL('**/orders**')` (or match on pathname) for any route that
   might append query params.

## Step 3 — Run it, isolated per run

First prove the runner can see the copy — a spec relocated under
`.record-tmp/<run-id>/` can fall outside the project's `testMatch`, and the
symptom ("No tests found") is cheaper to meet before recording than after:

```bash
npx playwright test <spec-path> --project=<project> --list
```

Empty listing → adjust the copy's filename/location until it satisfies the
project's matching (staying inside the run-scoped directory), or pass a
project whose matching covers it. Then run:

```bash
PLAYWRIGHT_LIST_PRINT_STEPS=1 npx playwright test <spec-path> --project=<project> \
  --output <scratch>/record-run-<timestamp> --reporter=list
```

The env var matters: the list reporter does **not** print `test.step` entries by
default (`printSteps` defaults to false), and Step 6's per-step statuses are read
from this output — without it they would have to be invented.

`--output` gives every recording its own directory, so a second run can never
delete the first run's video (Playwright clears its output directory at the start
of each invocation — with a shared one, back-to-back recordings silently destroy
each other). Add `--headed` only when the user asked to watch; headless records
identically. **Confirm the assertions passed** — a failed run still produces a
video, but that video documents a bug, not a verification. On failure: report it
as exactly that, skip Steps 4–5 **and Step 7** (nothing gets published, so there
is no footage to caption — the failure report replaces the walkthrough), and go
**straight to Step 6** — cleanup is unconditional; a failed run must not leave
the temporary spec or command-started servers behind.

## Step 4 — Recover the video

```bash
find <scratch>/record-run-<timestamp> -iname '*.webm'
```

More than one file is normal — retries, multiple browser projects, or a spec
with sibling tests each produce their own. **Never publish "the newest" blind:**
Playwright names each result directory after the test title, project and retry
(`<spec>-<title>-<project>[-retryN]/`), so map the intended test's *successful*
attempt to its directory and take that video; cross-check against the reporter
output when in doubt. Copy the selected file to your scratchpad immediately
(belt and braces — scratch directories are cheap, re-recording is not), then
post-process the copy.

## Step 5 — Post-process before publishing

Requires `ffmpeg`/`ffprobe` (Step 0.4). Without them: publish the raw `.webm`,
state plainly that the lead-in trim and pacing check were skipped and why, and
include the install hint (`brew install ffmpeg` / distro equivalent).

1. **Trim the blank lead-in.** Recording starts when the browser page is created —
   before the first `goto()`, before first paint — so recordings open on ~1–1.5 s
   of blank page, which a correctly slowed video turns into conspicuous dead air:

   ```bash
   ffmpeg -y -ss 1.5 -i raw.webm -c:v libvpx -b:v 1M -crf 10 trimmed.webm
   ```

2. **Verify the trim** — never trust the cut blind:

   ```bash
   ffmpeg -y -i trimmed.webm -update 1 -vframes 1 first-frame.png
   ```

   First frame still blank → raise `-ss` a little; content already cut off →
   lower it. First paint varies a few hundred ms run to run.
3. **Gate the pacing:** `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 trimmed.webm`.
   A multi-step flow under ~15–20 s is still too fast for a human reviewer —
   raise `slowMo` and **re-record**; that is the fix. Stretching
   (`-filter:v "setpts=4.0*PTS"`) only holds static frames longer — a fallback
   when re-recording is impractical, never the preferred path, and always
   applied *after* the trim (stretching the lead-in turns a sub-second blank
   into seconds of dead air).
4. **`--mp4` (optional):** `.webm` does not preview inline everywhere reviewers
   live (issue trackers, chat clients). When asked:

   ```bash
   ffmpeg -y -i trimmed.webm -c:v libx264 -pix_fmt yuv420p flow.mp4
   ```

Copy (don't move) the final file into the Step 0.3 artifact location, named
`<ticket-or-slug>-<flow-description>.<ext>`.

## Step 6 — Report and clean up

- Per-step status **read from the runner, never inferred**: wrap each golden-path
  step in `test.step('<n>. <description>', …)` when writing the spec, so the
  reporter names every step it executed. A step the runner never reached is
  reported **NOT RUN** — a mid-flow failure proves nothing about later steps,
  and inventing their status is worse than omitting it. Then: navigation gaps
  found, and — for a successful, published recording — the artifact path; a
  failed run states plainly that nothing was published, never a scratch path
  dressed up as evidence.
- Delete this run's `<testDir>/.record-tmp/<run-id>/` — only this run's, never
  the whole `.record-tmp/`, which may hold a concurrent recording's spec. If
  permanent,
  confirm its fixtures/seeds are staged alongside it.
- Kill any dev servers Step 1 started.
- **Never commit from this command** — the artifact directory may be tracked, and
  committing is the user's decision, always.

## Step 7 — The companion walkthrough (always, for every published recording)

A video with no caption is unusable — the viewer cannot tell what to watch for.
Every run ends with a **plain-text, English, condensed step-by-step** the user can
paste next to the video. It narrates the *footage*, not the report:

- **The text is the recording, step for step** — derived from the spec that
  actually ran, in execution order, using the literal values typed and the
  literal strings asserted on screen — with one exemption that overrides the
  literal rule: credentials and account identifiers (passwords, emails,
  usernames, tokens) are never transcribed; write the role instead ("the admin
  account's password"). A step cut from the spec goes in a final "not in this
  video" line, never in the numbered list.
- Plain text in the chat reply — no artifact, no file, no code fences (the user
  copies it straight out of the terminal). English regardless of conversation
  language.
- First line: ticket/slug, environment recorded, filename, duration — measured
  by `ffprobe` (Step 5); without it, take the duration from the test's runtime
  in the reporter output (close enough for a caption) and mark it approximate.
- **Identify signed-in users by ROLE, never by email/username** — "sign in as the
  admin account", not the address. The role tells the reader whether behaviour is
  permission-dependent; the address is a credential that would end up pasted into
  chat and tickets. Same for every identity the flow touches.
- Numbered steps, one short line each, matching the video 1:1: what is
  clicked/typed, then what appears — on-screen strings verbatim so the viewer can
  match text to frame.
- Close with notes: anything deliberately left out, and any test data the run
  wrote that needs cleaning up.

Keep it under a screen — it is a caption, not a manual.

## Common mistakes

| Mistake | Consequence |
|---|---|
| Forgetting `test.use({ video: 'on' })` | Silently no video — most configs keep video off locally. |
| `slowMo` skipped or too low (300–500 ms) | Recording too fast for the audience — gate with `ffprobe` before publishing; aim 1000–1500 ms. |
| `slowMo` without raising `test.setTimeout` | The run blows the default 30 s budget mid-flow and fails. |
| Not trimming (and not verifying) the blank lead-in | Ships with dead air up front; a blind `-ss` cut can also decapitate real content — pull the first frame and look. |
| Sharing one output directory across runs | Playwright wipes it per invocation — the previous video is deleted even though its test passed. Use `--output` per run. |
| Bare `waitForURL('**/page')` on a query-param route | Hangs under `slowMo`, may race-pass without it — reads as a `slowMo` bug and isn't. Trailing `**`. |
| `page.goto()` straight to the target screen | An unreachable-by-click feature passes anyway — the evidence lies. |
| Publishing a video from a failed run as verification | The video documents a bug. Say so; don't publish it as proof of working behaviour. |
| Handing over the video without the Step 7 walkthrough | The reviewer gets a silent recording and no idea what to look for. |
| Walkthrough written from the plan instead of the spec that ran | Lists steps the footage doesn't contain; the reader loses sync in seconds. |
| Naming test accounts by email instead of role | Leaks a credential into chat/tickets and tells the reader nothing. |
| Bolting Playwright onto a project that doesn't have it | Out of scope for producing one video — report the gap instead. |
| Editing an existing spec in place to force video/`slowMo` | The recording-only overrides outlive the recording — that test stays slowed and video-enabled for every future run. Record from a `.record-tmp/<run-id>/` copy. |
