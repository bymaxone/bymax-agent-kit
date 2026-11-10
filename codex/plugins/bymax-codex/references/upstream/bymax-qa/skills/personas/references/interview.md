# Interview

Every choice the repository cannot settle is asked, never assumed. Ask with
`AskUserQuestion`: at most four questions per call, two to four options each,
the recommended option first with "(Recommended)" at the end of its label,
and a one-line description saying what the choice costs or covers. The human
can always answer "Other". Where no question tool exists (a headless
run), ask in plain text with numbered options and wait for the reply.

Before asking, read the repository so the options are this app's options, not
generic ones: its platform, its locales, its flows, its existing research.
State in a question what you found that led to the recommendation ("The app
ships pt-BR, en and es"). Record every question, the options shown and the
answer in `.claude/qa/personas/interview.md`.

## Round 1 — before research (`init`)

| Question | Options to offer | How to pick the recommendation |
| --- | --- | --- |
| Where will the personas use the app? | iPhone Simulator · Android emulator · both, one persona per platform mix · browser | Expo/React Native or native project: "both" when the market's platform share is mixed (read it from StatCounter for that country), the platform the project targets first otherwise. A web framework with no native target: "browser". |
| How many personas? | 3 (quick, core flows only) · 5 · 7 (every flow covered at least twice) | Count the app's distinct flows: up to ~8 flows → 3; up to ~15 → 5; more, or several locales or accessibility profiles → 7. Say the flow count you found. |
| Which markets and languages? | the app's locales, grouped into two or three choices (e.g. "Brazil only", "Brazil + US", "Brazil, US, UK, Germany") | The locales the app ships; the country the spec names first. |
| How deep should the research go? | Deep: web, trusted studies, competitor store reviews, forums · Reuse the project's existing research and fill gaps · Quick: listings and standards only | Deep, unless `docs/research/` already holds labelled audience research from the last six months, then "reuse and fill gaps". |

## Round 2 — after research, before personas (`init`)

| Question | Options to offer | Recommendation |
| --- | --- | --- |
| Which competitors should shape the personas? (multiSelect) | the top apps the discovery found, by store presence, with their rating count | the four with the most reviews in the target markets, plus any app from the target country |
| Which accessibility profiles must be covered? (multiSelect) | large text (iOS AX sizes / Android font scale 2.0) · early presbyopia (font scale 1.3) · screen reader · Reduce Motion · dark theme · one-handed or imprecise touch | large text and early presbyopia always: the research on 40+ users makes them the most common real need |
| How many days should each persona live with the app? | 30 · 14 · 7 · a single session | 30 when the app has anything that happens over time (streaks, reminders, reviews, trials, subscriptions); a single session for a one-shot tool |
| Open points the research left | one question per real gap (an audience the research could not size, a region with no data) | as the evidence suggests, saying it is inferred |

## Round 3 — before the plan (`plan`)

Mobile:

| Question | Options | Recommendation |
| --- | --- | --- |
| Which iOS device? | the simulators `xcrun simctl list devices available` returns, newest first, plus one small-screen model | a small-screen model for a large-text persona, the newest for the rest |
| Which Android device? | the AVDs `emulator -list-avds` returns; offer to create one if none | an AVD with a recent API level; display size at its largest for a low-vision persona |
| Which build is installed? | development client on Metro · a local release build · an EAS/TestFlight build | the development client, because the clock seam is dev-only |
| The clock seam is missing: what now? (only when `time-travel.md` found none) | hand off a request and wait · run same-day sessions only · stop | hand off and wait, when the app has anything that happens over days |

Web — always asked, because there is no safe default for how to reach a web
app:

| Question | Options | Recommendation |
| --- | --- | --- |
| Where does the app run? | the local dev server the repository's scripts start (name the script) · a staging URL · a preview deployment | local, when a dev script exists |
| Which browser drives it? | the Claude Browser pane (the human watches) · the `agent-browser` CLI · the project's Playwright | the Browser pane when the session has it; otherwise the project's Playwright when its config exists, because it can move the clock |
| How does a persona sign in? | registration through the app, as a new user would · named test accounts · no sign-in | registration through the app |
| How should time move? | the app's own dev clock · Playwright's clock control · no time travel, same-day sessions | the app's own clock when one exists |
| Which viewports? (multiSelect) | phone 390×844 · tablet 820×1180 · desktop 1440×900 · 320-wide reflow (WCAG 1.4.10) | the persona's own device, plus 320-wide for a low-vision persona |

A host the human names that looks like production (the public domain, no
`staging`/`preview`/`localhost`) is asked about once more, and refused when it
is production.

## During the run

Ask only what the plan could not settle, and keep the run moving otherwise:

- after each persona: start the next one now, or after the fixes land;
- a product decision seen during the run (a font size, a step that should not
  exist): record it under "Needs a human" and ask at the end of the persona,
  not mid-day;
- a blocker that stops the persona (a crash on launch, a flow with no way
  forward): ask whether to hand it off and wait, or skip that flow and
  continue.
