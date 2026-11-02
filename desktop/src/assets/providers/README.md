# Provider marks

Bundled on 2026-11-02 for identifying the corresponding provider in navigation and account cards. These assets remain the property of their respective owners; they are not Agent Fleet branding or an endorsement.

- `codex.png`: original Codex app icon exported without redrawing or recoloring from the official signed macOS app's `Contents/Resources/app.icns`. Signing identity: OpenAI, Team ID `2DC432GLL2`, bundle ID `com.openai.codex`. ICNS → PNG conversion used Apple's `sips`; the packaged asset needs no installed Codex app or machine-specific path. Product: https://openai.com/codex/ · Brand: https://openai.com/brand/.
- `claude.svg`: unchanged original icon served by https://claude.com/icon.svg, including its `#D97757` color and original geometry. Product: https://claude.com/.

Both source assets are imported into the frontend bundle and work offline. On 2026-11-02 Johannes requested monochrome marks matching the surrounding text. `ProviderLogo` renders the unchanged source geometry through an alpha mask filled with `currentColor`; the Codex mask removes the white icon background and terminal cutouts. This follows the existing foreground colors without introducing a separate logo palette.
