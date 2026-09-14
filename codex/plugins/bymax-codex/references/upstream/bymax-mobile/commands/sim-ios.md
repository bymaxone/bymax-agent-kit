---
description: Boot the iOS Simulator (default "iPhone 17") and run the app from the current Expo project. Auto-detects whether `expo start` is enough (Metro reattach — app already installed) or `expo run:ios` is needed (first time, or native code changed). Reads no native config — heuristic based on `ios/` folder + build artifacts. Honors `$BYMAX_SIM_IOS` and `$APP_VARIANT`. macOS only — needs Xcode + xcrun simctl. Triggers, "abrir simulator iphone", "rodar no ios", "sim ios", "ios simulator", "boot iphone", "test on iphone", "iniciar simulador ios", "/bymax-mobile:sim-ios".
---

# /bymax-mobile:sim-ios — boot iOS Simulator and run the Expo app

Boot the iOS Simulator and run the current Expo project. Execute every step **in sequence, without asking the user any questions**.

## Step 0 — Pre-flight

1. **macOS only.** If `uname` is not `Darwin`, abort with: `iOS Simulator only works on macOS. Aborting.`

2. **Xcode CLI tools.** Run `command -v xcrun`. If missing, abort with: `Xcode command-line tools not found. Install with: xcode-select --install`

3. **Expo project root.** At least one of `app.config.ts`, `app.config.js`, or `app.json` must exist in the current working directory. If none, abort with: `Not in an Expo project root. cd into the project first.`

4. **Package manager.** In order of priority: `pnpm` if `pnpm-lock.yaml`, else `yarn` if `yarn.lock`, else `npm`. Use this as `<PM>` in the run step.

## Step 1 — Pick the device

Device name (in priority order):

- `$BYMAX_SIM_IOS` if set in env.
- Else: `iPhone 17` (no `Pro`, `Max`, or `e` suffix).

Verify it exists:

```bash
xcrun simctl list devices available | grep -E "iPhone 17( \(|$)" | head -1
```

If the requested device is not registered, fall back to the first available iPhone:

```bash
xcrun simctl list devices available | awk '/^-- iOS/{p=1; next} /^--/{p=0} p && /^[[:space:]]+iPhone/{print; exit}'
```

Capture the `<DEVICE_NAME>` and `<UDID>` from the line (format: `iPhone 17 (UDID) (Shutdown|Booted)`).

## Step 2 — Boot the simulator if needed

`xcrun simctl boot` is idempotent — it returns non-zero if already booted, but that's harmless. Wrap in a check:

```bash
if ! xcrun simctl list devices booted | grep -F "<UDID>" >/dev/null 2>&1; then
  xcrun simctl boot "<UDID>"
fi
open -a Simulator
```

## Step 3 — Decide run mode

Heuristic — no config parsing:

```bash
if [ ! -d ios ] || [ -d ios/build ] || [ -d ios/Pods ]; then
  MODE=start
else
  MODE=run
fi
```

- **`start`**: managed Expo workflow (no `ios/`), or `ios/` exists with `build`/`Pods` present (already built once).
- **`run`**: `ios/` exists but never built locally — needs `expo run:ios`.

## Step 4 — Run

### MODE=start

```bash
<PM> expo start
```

Then tell the user verbatim:

> Press **`i`** in the Metro terminal to open the app on **`<DEVICE_NAME>`**.

Do not press `i` for them — Claude has no terminal interactivity here.

### MODE=run

```bash
<PM> expo run:ios --device "<DEVICE_NAME>"
```

This rebuilds, installs, and launches automatically. Wait for it to print `BUILD SUCCEEDED` and the Metro URL, then stop.

## Hard rules

- **macOS only.** Refuse on Linux/Windows.
- **Never `cd`.** Never edit project files. Only spawn shell commands.
- **Device default is `iPhone 17`.** Override only via `$BYMAX_SIM_IOS`.
- **Do not pass `--variant` flags.** Honor whatever `$APP_VARIANT` is already in the env.
- **Never ask the user.** Every decision is rule-based above.

## Troubleshooting (for the user)

| Symptom                                       | Fix                                                                     |
| --------------------------------------------- | ----------------------------------------------------------------------- |
| `iPhone 17` not in `simctl list devices`      | Open Xcode → Settings → Platforms → install latest iOS runtime.         |
| Simulator boots but app doesn't open with `i` | App not installed → re-run with `MODE=run` (delete `ios/build/`).       |
| `expo run:ios` fails on Pods                  | `cd ios && pod install --repo-update && cd -`, then re-run.             |
| Metro picks wrong device                      | `$ env BYMAX_SIM_IOS="iPhone 16 Pro"` or pass `--device` explicitly.    |

## Cleanup helpers

To wipe the app from the simulator before re-running:

```bash
xcrun simctl uninstall booted <bundle-id>
```

To shut everything down:

```bash
xcrun simctl shutdown all
osascript -e 'quit app "Simulator"'
```
