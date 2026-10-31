# Furby Remote (iPhone)

A small SwiftUI app that connects to the show's ESP32 over Bluetooth and shows what it's doing: who's connected, errors, and the live log. It also has buttons to play a greeting, any scene, or any single clip. With the app in the background it stays connected, and an error (a Furby dropping, say) pops up as a notification.

The board side is [`firmware/remote.py`](../firmware/remote.py), switched on by `REMOTE = True` in [`firmware/main.py`](../firmware/main.py). Its docstring is the protocol: newline-terminated JSON over the Nordic UART Service (NUS). Because NUS is a common standard, [nRF Connect](https://apps.apple.com/app/nrf-connect-for-mobile/id1054362403) can also talk to the board, with no app to build: connect to "Furby Show", subscribe to the TX characteristic, and write `greet` to RX.

## What's here

- [`project.yml`](project.yml): the Xcode project, as code. [XcodeGen](https://github.com/yonaskolb/XcodeGen) turns it into `FurbyRemote.xcodeproj`, which isn't committed.
- [`FurbyRemote/`](FurbyRemote): the app.
  - `BoardLink.swift` handles Bluetooth: finding, connecting to and listening to the board.
  - `ContentView.swift` is the screen.
  - `Assets.xcassets` holds the app icon, drawn by [`tools/app_icon.py`](../tools/app_icon.py): change the script and run `uv run tools/app_icon.py` rather than editing the PNG.
- [`FurbyRemoteKit/`](FurbyRemoteKit): the protocol: message types, joining Bluetooth chunks back into lines, and commands. It's a Swift package so it can be tested without an iPhone: `swift test --package-path ios/FurbyRemoteKit`.

## Build it onto your iPhone

You need a Mac with Xcode and a free Apple account. A free account's apps stop opening after 7 days: plug in and run again from Xcode to renew.

### One-time setup

1. **Install Xcode** from the Mac App Store (`mas install 497799835`). It's large. Open it once to let it finish installing, and accept the license: `sudo xcodebuild -license accept`.
2. **Install XcodeGen:** `brew install xcodegen`.
3. **Add your Apple ID to Xcode:** Xcode → Settings → Accounts → **+** → Apple ID. This creates a free "Personal Team".
4. **Tell the project your team.** Copy `Local.xcconfig.example` to `Local.xcconfig` and put in your team ID. `security find-identity -v -p codesigning` shows it in parentheses once Xcode has made your signing certificate. `Local.xcconfig` isn't committed.
5. **On the iPhone, turn on Developer Mode:** Settings → Privacy & Security → Developer Mode. It only appears after the phone has been plugged into a Mac running Xcode. The phone restarts.
6. **Plug the iPhone into the Mac** and tap **Trust** on the phone.

### Build and run

```sh
cd ios
xcodegen                  # makes FurbyRemote.xcodeproj from project.yml
open FurbyRemote.xcodeproj
```

In Xcode, pick your iPhone in the device menu at the top (next to "FurbyRemote"), then press **▶** (Run).

The first time, the phone refuses to open the app until you trust yourself as a developer: Settings → General → VPN & Device Management → your Apple ID → Trust. Run again.

Run `xcodegen` again whenever `project.yml` changes or you add a Swift file. Xcode's project is generated, so changes made in Xcode's project settings are lost on the next run. Put them in `project.yml` instead.

### Using it

Turn on `REMOTE` on the board (it's on by default) and deploy with `firmware/deploy.sh`. Open the app near the porch. It finds "Furby Show" by itself, and pulling down on the screen asks for a fresh status.

- **Greet** plays a greeting, as the board's button does.
- **Scenes** and **Clips** play the one you tap as soon as the current scene ends.
- **Errors** shows the latest problems first. **Full log** shows everything the board has said since it started (the last 50 lines from before you connected, then everything live).

Anyone within Bluetooth range with an app like nRF Connect could press the same buttons. The worst they can do is make a Furby talk.

## Turning it off

Set `REMOTE = False` in [`firmware/main.py`](../firmware/main.py) and run `firmware/deploy.sh`. The board then neither loads the remote nor advertises it, and the show runs exactly as it did before the remote existed.
