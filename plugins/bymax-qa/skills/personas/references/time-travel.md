# Moving time

Thirty days of use have to fit in an afternoon, so the clock moves and the
data does not. The only test seam this skill accepts is a control that sets
the app's "now" without touching its data. Seeding a history to reach day 20
skips the nineteen days in which the defects live.

## Find the seam

Look for the single place the app reads the time, and for a development-only
control over it:

- a clock module (`clock.ts`, `now()`, a `Clock` injected into services) that
  every date read goes through;
- a dev panel, a deep link (`<scheme>://_dev/...`) or a debug menu that pins
  or advances it;
- for web: a dev query parameter or local-storage key the app's clock reads,
  or the project's Playwright, whose `page.clock` can fix and advance the
  browser's time (confirm the API in the installed `@playwright/test`
  declarations before planning on it).

Confirm three properties by reading the code, and record each with its
`path:line` in `plan.md`:

1. **It moves time only.** Pinning does not reset or seed data.
2. **It cannot ship.** It is absent from a release build, guarded by a dev
   flag the build sets.
3. **The app notices.** The screens re-read the date when the app returns to
   the foreground (or on navigation, for web), so a pinned day shows without a
   reinstall.

## When the seam is missing or incomplete

Do not add it. Hand it off as a prerequisite, with the three properties above
as its acceptance criteria and a note that it needs its own change, tests and
review. Until it lands, the plan has two honest options, asked in interview
round 3: wait, or run same-day sessions only and mark every multi-day flow
"not exercised: no clock seam".

## A simulated day

1. Pin the clock to the day's first moment (the persona's morning routine),
   then send the app to the background and back.
2. The persona opens the app and acts on that morning's intent.
3. Advance to the evening for a late log or a miss.
4. On days with a periodic moment (a weekly screen, an offer, a trial
   ending), run that flow end to end.
5. A day after midnight (a late log for "yesterday") pins 00:30 or so of the
   next date.

Pin the time **every day**, even when it only advances: a restart can drop an
in-memory clock, and a day that silently runs on the host's real time records
on the wrong date.

## What a pinned clock does not cover

Each needs its own test, planned on a named day:

| Not covered | Why | How to test it |
| --- | --- | --- |
| a real notification firing | the OS schedules on the host's clock | schedule one a few minutes ahead on the real clock, wait, act on the banner and its actions |
| Android battery and Doze | the emulator does not idle by itself | `adb shell dumpsys deviceidle force-idle`, then wait for the reminder; check the exact-alarm permission |
| widget timelines and the day turning on a widget | the widget renders on the system clock | check the widget after each log (the data changes); test the day boundary once in real time |
| time-zone travel | the pinned offset is fixed | change the simulator's or emulator's zone between days (iOS: relaunch the app with `SIMCTL_CHILD_TZ=<zone> xcrun simctl launch --terminate-running-process <device> <bundle-id>`; Android: turn off automatic time zone and pick the zone in Settings › System › Date & time, as a traveller would) |
| weeks of forgetting, notification fatigue | a model does not get tired | not testable here; declared in the report |
| a scratched screen, damp fingers | simulators have neither | measure the touch targets instead, against 44 pt / 48 dp |

Declare these limits in every persona report, with what was done instead.
