# 📱 Bymax Mobile

> One-shot booters for **iOS Simulator** and **Android Emulator** on Expo / React Native projects. Auto-detects whether to reattach Metro (fast) or rebuild + install (slow).

## Install

```bash
claude plugin marketplace add bymaxone/bymax-agent-kit
claude plugin install bymax-mobile@bymax-agent-kit
```

### Also in Codex

The same procedures ship in the Codex package as `bymax-sim-ios`, `bymax-sim-android` (namespaced `bymax-codex:<name>`). Install it with `./scripts/install-codex.sh` from a checkout — see [CODEX.md](../../CODEX.md) for the entrypoints and the capability boundaries, which are not full parity.

## What you get

| Command          | Platform | What it does                                                                                                                                                |
| ---------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/bymax-mobile:sim-ios`       | iOS      | Boots `iPhone 17` (or `$BYMAX_SIM_IOS`), runs `expo start` if app already built, else `expo run:ios`. macOS only.                                            |
| `/bymax-mobile:sim-android`   | Android  | Boots the first AVD listed by `emulator -list-avds` (or `$BYMAX_SIM_ANDROID`), runs `expo start` if app already built, else `expo run:android`. macOS / Linux. |

Both commands:

- Auto-detect the package manager (`pnpm` if `pnpm-lock.yaml`, else `yarn`, else `npm`).
- Auto-detect run mode (start vs run) from build artifacts in `ios/` or `android/` — no Expo config parsing.
- Honor `$APP_VARIANT` if set in the env (Expo build flavor — `development` / `preview` / `production`).
- Pre-flight tooling and project shape; bail with a clear, actionable error if something is missing.
- Never ask the user a question — every step is decided up front.

## Environment overrides

| Var                                   | Default                          | What                                                |
| ------------------------------------- | -------------------------------- | --------------------------------------------------- |
| `BYMAX_SIM_IOS`                       | `iPhone 17`                      | iOS simulator name (e.g., `iPhone 16 Pro`)          |
| `BYMAX_SIM_ANDROID`                   | first `emulator -list-avds`      | AVD name (e.g., `Pixel_8_API_34`)                   |
| `APP_VARIANT`                         | unset (production)               | `development` / `preview` / `production` — Expo flavor |
| `ANDROID_HOME` / `ANDROID_SDK_ROOT`   | `~/Library/Android/sdk` (macOS)  | Android SDK location                                |

## Prerequisites

### iOS (`/bymax-mobile:sim-ios`)

- macOS.
- Xcode command-line tools (`xcode-select --install`).
- The simulator named `iPhone 17` (or whatever you set in `$BYMAX_SIM_IOS`) registered in `xcrun simctl list devices available`.

### Android (`/bymax-mobile:sim-android`)

- Android Studio (for AVD Manager) — or, headless, the command-line tools.
- `platform-tools` (for `adb`) — `brew install --cask android-platform-tools`.
- At least one AVD created in Android Studio's Device Manager.
- `$ANDROID_HOME/emulator` and `$ANDROID_HOME/platform-tools` on your `$PATH` — typical `~/.zshrc` snippet:

  ```bash
  export ANDROID_HOME="$HOME/Library/Android/sdk"
  export PATH="$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools"
  ```

### Project (both)

- Any Expo project — managed or bare. Detected by the presence of `app.config.ts`, `app.config.js`, or `app.json` in the current working directory.

## Run-mode heuristic

The command picks `start` (fast — only the JS bundler) vs `run` (slow — rebuild native + install + launch) based on build artifacts on disk. **No config parsing**, so it's fast and resilient:

| `<platform>/` folder | Build artifact present?                      | Mode             |
| -------------------- | -------------------------------------------- | ---------------- |
| no (managed Expo)    | n/a                                          | `start`          |
| yes                  | `ios/build` or `ios/Pods`                    | `start`          |
| yes                  | none                                         | **`run`**        |
| yes                  | `android/app/build/outputs`                  | `start`          |
| yes                  | none                                         | **`run`**        |

If the heuristic guesses wrong (e.g., you deleted the app from the simulator manually), just re-run with `--mode run` semantics — easiest fix is to delete `ios/build/` or `android/app/build/` and run `/bymax-mobile:sim-ios` (or `/bymax-mobile:sim-android`) again, which will fall into `run` mode.

## License

MIT — see [root LICENSE](../../LICENSE).
