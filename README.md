# Skin Watcher

Skin Watcher monitors CS2 listings on PirateSwap and SkinsMonkey and sends
Discord notifications when matching listings appear.

## How to launch

1. Put all Skin Watcher files in a folder named `skin-watcher`.
2. Open the `skin-watcher` folder.
3. Make sure this folder contains:
   - `start-dedicated-browser.bat`
   - `chrome-extension`
4. Run `start-dedicated-browser.bat`.
5. A dedicated Chrome window will open.
6. Open Skin Watcher from the browser extensions page/menu.
7. Paste your Discord webhook URL and click `Test Discord`.
8. Select PirateSwap, SkinsMonkey, or both.
9. Add the skins you want to watch.
10. Click `Start watching`.

Keep the dedicated browser window open while Skin Watcher is running. It can stay
behind your normal browser window.

## Supported browsers

- Google Chrome

## Resetting Skin Watcher

The launcher creates a `.skin-watcher-profile` folder inside `skin-watcher`.
This stores the dedicated browser profile and Skin Watcher settings.

To reset everything:

1. Close the dedicated browser.
2. Delete `.skin-watcher-profile`.
3. Run the launcher again.

## Notes

- The first scan creates a baseline. Discord alerts are sent only for listings
  found after that baseline.
- If notifications do not arrive, check the Discord webhook URL and use
  `Test Discord`.
- If a site stops updating, stop watching and start watching again.
- If the browser opens but Skin Watcher is missing, close every dedicated Skin
  Watcher browser window and run `start-dedicated-browser.bat` again. Chrome can
  ignore extension-loading flags when the same profile is already open.
