# Running a persona on the iOS Simulator or Android emulator

The persona uses the app through the simulator's screen, its settings and its
notifications. Maestro drives the taps; screenshots and the view hierarchy are
what you read before deciding the next one.

## Preflight

| Check | Command | On failure |
| --- | --- | --- |
| Maestro installed | `maestro --version` | stop; point to `https://maestro.mobile.dev` and its install line |
| iOS: a device is booted | `xcrun simctl list devices booted` | offer `/bymax-mobile:sim-ios` |
| Android: an emulator is attached | `adb devices` lists one `device` | offer `/bymax-mobile:sim-android` |
| the app is installed | iOS `xcrun simctl listapps booted` names the bundle id; Android `adb shell pm list packages` names the package | build and install through the project's own scripts, or the `sim-*` commands |
| a development client reaches Metro | the app opens past the dev launcher | start the project's dev server; `expo-development-client/?url=…` deep link reconnects |
| the host will not sleep | run long sessions under `caffeinate -dims` | a Mac that sleeps freezes the driver mid-day and the day fails for no app reason |

## Apply the persona's settings

Apply them before day 1, from the persona's device line, and screenshot the
settings screen as evidence.

iOS Simulator (`xcrun simctl ui <device> …`):

| Setting | Command |
| --- | --- |
| text size | `content_size <size>`: `large` is the default; `accessibility-medium` is AX1, `accessibility-large` AX2, up to `accessibility-extra-extra-extra-large` AX5 |
| theme | `appearance dark` or `appearance light` |
| Increase Contrast | `increase_contrast enabled` |
| Bold Text, Reduce Motion, VoiceOver, Button Shapes | in the simulator's Settings › Accessibility, as the person would set them |

Android emulator (`adb shell …`):

| Setting | Command |
| --- | --- |
| font scale | `settings put system font_scale 1.3` (or `2.0`) |
| display size | `wm density <dpi>` above the device default makes everything larger; read the default with `wm density` first and restore it after |
| theme | `cmd uimode night yes` or `no` |
| remove animations | `settings put global animator_duration_scale 0` (and `transition_animation_scale`, `window_animation_scale`) |
| TalkBack, high-contrast text | in Settings › Accessibility, as the person would set them |

Restore every setting when the persona ends, so the next persona starts from
its own.

## Interactive days

Onboarding, every first use of a flow, every periodic screen and every day in
the failure script are driven step by step:

1. Screenshot: iOS `xcrun simctl io booted screenshot <file>`, Android
   `adb exec-out screencap -p > <file>`, into `runs/P<n>/shots/`.
2. Read the image, and `maestro hierarchy` when you need what is on screen
   but not visible (a label, a control scrolled away, an accessibility name).
3. Decide as the persona: what they see first, what they would tap, what
   they would type and how. Prefer `tapOn: text:` with the words the persona
   reads on screen; a `tapOn: id:` is allowed only for a control visible in
   the last screenshot.
4. Write the one to three commands to a step file under
   `runs/P<n>/steps/` and run it with `maestro test <file>`.
5. Screenshot again and compare: did the tap do what the persona expected?

A control that needs a scroll the persona would not think of, a label they
cannot read at their text size, or a target their slip would miss is the
observation itself. Record it, then do what the persona would do next:
scroll, retry, give up on that step.

## Scripted days

Days with nothing new (log as usual, miss, do the minimum) can be generated
and run in order. Write a config for the persona:

```json
{
  "appId": "com.example.app.dev",
  "persona": "p4",
  "first_date": "2026-11-05",
  "first_day": 2,
  "offset": "-03:00",
  "clock": "07:30",
  "late_clock": "00:30",
  "pin_flow": "../../flows/pin-clock.yaml",
  "actions": {
    "N": {"id": "today-done-.*"},
    "M": {"id": "today-min-.*"},
    "X": {"id": "today-miss-.*", "then": "../../flows/miss-reason.yaml"}
  },
  "plan": ["NN", "N-", "XX", "@NM"],
  "extras": {"8": ["../../flows/weekly-review.yaml"]}
}
```

- `pin_flow` is a flow you write in the workspace that pins the app's clock
  through its dev control and brings the app back to the foreground; it reads
  `${PERSONA_STAMP}`, `${PERSONA_DATE}` and `${PERSONA_TIME}`.
- `plan` has one string per day; each letter is one pending item, in the order
  the screen lists them. `-` leaves an item alone, and later actions skip past
  the items left; an action with `"own_index": true` targets a separate list
  and always takes its first match. A day starting with `@` pins `late_clock`.
- `then` runs a flow after the action (a reason sheet); `extras` adds flows at
  the end of a day.
- A tap is **not optional** unless its action says `"optional": true`. A
  button that is not there fails the day, which is what you want to look at:
  optional taps once hid a whole run in which every button had fallen below
  the fold.
- Relative paths are resolved from the config file.

Generate the flows, then run them one by one:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/persona-days.py" \
  .claude/qa/personas/runs/P4/days.json .claude/qa/personas/runs/P4/flows
caffeinate -dims bash "${CLAUDE_PLUGIN_ROOT}/scripts/persona-run-days.sh" \
  .claude/qa/personas/runs/P4/flows
```

The runner runs one file per `maestro test` call, in file order, copies the
screenshots each day took into `flows/shots/`, appends `flows/run-log.tsv`,
and stops at the first failed day. Never run `maestro test <folder>`: it does
not keep the order, the pinned clock goes backwards, and later days are
already reconciled when earlier ones run. `MAESTRO` overrides the command (a
project wrapper such as `bash scripts/maestro.sh`), `PERSONA_DEVICE` passes
`--device`, and `PERSONA_BEFORE_DAY` runs a command before each day with
`PERSONA_DAY` set (a time-zone change for a trip).

Look at every scripted day's screenshots after the run. A scripted day that
passed can still show a defect.

## Traps measured on simulators

- A restart of the app drops a clock held only in memory; pin every day.
- A native switch or picker may need a press of 0.2 s or more; retry with a
  longer press before calling it broken.
- A Metro reload in the middle of a flow can swallow the last write; repeat
  the step without a reload before reporting lost data.
- A permission already granted cannot be revoked by Maestro on iOS; only a
  fresh install returns it to "not asked".
- A second screen mounted while another is on top may not animate in;
  navigate as the persona would (back to the screen) before concluding it is
  blank, and record that it was blank when they arrived.
