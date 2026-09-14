---
description: Boot the Android emulator (first AVD listed, or `$BYMAX_SIM_ANDROID`) and run the app from the current Expo project. Auto-detects whether `expo start` is enough (Metro reattach) or `expo run:android` is needed (rebuild + install + launch). Detects Android SDK at `$ANDROID_HOME` / `~/Library/Android/sdk`. If SDK or AVD is missing, prints exact install steps and stops. Honors `$APP_VARIANT`. Triggers, "rodar no android", "abrir emulador android", "sim android", "android emulator", "boot avd", "test on android", "iniciar emulador android", "/bymax-mobile:sim-android".
---

# /bymax-mobile:sim-android — boot Android emulator and run the Expo app

Boot an Android emulator and run the current Expo project. Execute every step **in sequence, without asking the user any questions**.

## Step 0 — Pre-flight

1. **Android SDK.** Detect in this order, capturing `<ANDROID_SDK>`:
   - `$ANDROID_HOME` if set and points to an existing dir.
   - `$ANDROID_SDK_ROOT` if set and points to an existing dir.
   - `$HOME/Library/Android/sdk` (default Android Studio install on macOS).
   - `/opt/homebrew/share/android-commandlinetools` (Homebrew on Apple Silicon).
   - `/usr/local/share/android-commandlinetools` (Homebrew on Intel).

   If none of those exist, abort with this message exactly:

   ```
   Android SDK not found. Install with:
     brew install --cask android-platform-tools     # adb
     brew install --cask android-studio              # SDK Manager + AVD Manager + emulator
   Then in Android Studio → SDK Manager, install Android 14 (API 34) or newer.
   Create an AVD via Android Studio → Device Manager → Create device.
   Finally, add to your shell profile (~/.zshrc):
     export ANDROID_HOME="$HOME/Library/Android/sdk"
     export PATH="$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools"
   Re-source the shell or open a new tab, then re-run /bymax-mobile:sim-android.
   ```

2. **Required binaries.** Verify these exist (use `<ANDROID_SDK>` from step 1):
   - `<ANDROID_SDK>/emulator/emulator`
   - `<ANDROID_SDK>/platform-tools/adb`

   If either is missing, print the same install hint and abort.

3. **Expo project root.** At least one of `app.config.ts`, `app.config.js`, or `app.json` must exist. If not, abort with: `Not in an Expo project root. cd into the project first.`

4. **Package manager.** Same detection as `/bymax-mobile:sim-ios`: `pnpm` if `pnpm-lock.yaml`, else `yarn` if `yarn.lock`, else `npm`. Use as `<PM>`.

## Step 1 — Pick the AVD

Name (in priority order):

- `$BYMAX_SIM_ANDROID` if set.
- Else: the first AVD returned by:

  ```bash
  "<ANDROID_SDK>/emulator/emulator" -list-avds | head -1
  ```

If the list is empty, abort with:

```
No AVDs configured. Open Android Studio → Device Manager → Create device.
Recommended starter: Pixel 8, API 34, 2 GB RAM, 4 GB storage.
After creating the AVD, re-run /bymax-mobile:sim-android.
```

Capture as `<AVD_NAME>`.

## Step 2 — Boot the emulator if needed

Check for an already-running emulator:

```bash
"<ANDROID_SDK>/platform-tools/adb" devices | awk '/emulator-[0-9]+\s+device$/{print $1; exit}'
```

If a device id is returned, capture as `<SERIAL>` and skip to Step 3.

Otherwise, boot in the background (don't block the shell):

```bash
nohup "<ANDROID_SDK>/emulator/emulator" -avd "<AVD_NAME>" -no-snapshot-load >/tmp/bymax-emulator.log 2>&1 &
```

Then wait for boot to finish (typically 20–60 s on cold boot):

```bash
"<ANDROID_SDK>/platform-tools/adb" wait-for-device shell 'while [[ "$(getprop sys.boot_completed)" != "1" ]]; do sleep 1; done'
```

Re-query the serial for the run step:

```bash
"<ANDROID_SDK>/platform-tools/adb" devices | awk '/emulator-[0-9]+\s+device$/{print $1; exit}'
```

## Step 3 — Decide run mode

```bash
if [ ! -d android ] || [ -d android/app/build/outputs ]; then
  MODE=start
else
  MODE=run
fi
```

- **`start`**: managed Expo workflow (no `android/`), or build artifacts present.
- **`run`**: `android/` exists but never built — needs `expo run:android`.

## Step 4 — Run

### MODE=start

```bash
<PM> expo start
```

Then tell the user verbatim:

> Press **`a`** in the Metro terminal to open the app on the emulator (`<AVD_NAME>`).

### MODE=run

```bash
<PM> expo run:android
```

This rebuilds, installs, and launches automatically. Wait for `BUILD SUCCESSFUL` and the Metro URL.

## Hard rules

- **macOS + Linux supported.** SDK detection covers both.
- **Never `cd`.** Never edit project files. Only spawn shell commands.
- **AVD default is the first listed.** Override only via `$BYMAX_SIM_ANDROID`.
- **Do not create AVDs programmatically.** Always direct the user to Android Studio's Device Manager — programmatic AVD creation is fragile across SDK versions.
- **Do not pass `--variant` flags.** Honor whatever `$APP_VARIANT` is already in the env.
- **Never ask the user.** Every decision is rule-based above.

## Troubleshooting (for the user)

| Symptom                              | Fix                                                                              |
| ------------------------------------ | -------------------------------------------------------------------------------- |
| `adb: command not found`             | `brew install --cask android-platform-tools`, then add to `$PATH`.               |
| `emulator: command not found`        | SDK installed but PATH missing — re-read the abort message and add the exports. |
| AVD boots but stays on lockscreen    | `adb shell input keyevent 82` to swipe up.                                       |
| Metro can't find emulator            | Ensure ONE emulator running; or set `$ANDROID_SERIAL=<emulator-id>`.             |
| `adb` reports device offline         | `adb kill-server && adb start-server`, then re-run.                              |
| `expo run:android` SDK location err  | Add `sdk.dir=$ANDROID_HOME` to `android/local.properties`.                       |

## Cleanup helpers

To uninstall the app from the emulator:

```bash
"<ANDROID_SDK>/platform-tools/adb" uninstall <package-name>
```

To kill the emulator:

```bash
"<ANDROID_SDK>/platform-tools/adb" emu kill
```
