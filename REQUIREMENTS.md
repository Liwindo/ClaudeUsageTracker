# Requirements

The behavioural contract both variants of Claude Usage Tracker
([`python/`](python/) and [`csharp/`](csharp/)) must satisfy. It exists because
many of these requirements are **invisible** — they are not obvious from the UI
and were each learned from a bug. When only one variant encoded such a rule (in
a code comment or a `CHANGELOG` line), re-implementing the other variant silently
lost it. The peak-hour banner shifting the widget's position (fixed in the Python
variant back in 1.4.0/1.4.1, missing from the C# port until it was reported) is
the canonical example. This file is the single, shared source of truth so that
can't happen again.

Each requirement has a stable ID (`R-<area>-<n>`). Use it in commit messages,
test names, and PR descriptions so a requirement and its proof stay linked.

## Keeping this file complete

**This is the part that matters most.** A requirement that lives only in one
variant's head will be lost again.

1. **Every behavioural change adds or updates a requirement here — in the same
   commit/PR.** New feature, bug fix that establishes an invariant, or a
   deliberate behaviour change: edit this file as part of the change, never
   afterwards.
2. **Cross-variant requirements MUST be implemented in both variants,** or
   explicitly marked `variant-specific` with the reason. A change to shared
   behaviour that touches only one variant is incomplete.
3. **Every requirement that can be tested MUST cite its test** under
   *Verified by*. If it can only be verified by running the app (GUI/OS/timing),
   say so under *Verified by* — do not leave it unproven.
4. The pull-request template ([`.github/pull_request_template.md`](.github/pull_request_template.md))
   carries this as a checklist item; CI and review should treat an un-updated
   `REQUIREMENTS.md` on a behavioural change as a defect.
5. Keywords **MUST / MUST NOT / SHOULD** are used in the RFC 2119 sense.

---

## 1. Cross-variant parity & versioning

- **R-parity-1** — The two variants MUST present the same usage information and
  read the same claude.ai session (the user's Firefox cookies). Anything a user
  can observe about *what* is reported MUST match; *how* it is rendered may
  differ (the C# variant has a settings dialog, clickable toasts, animations).
- **R-parity-2** — The variants share one version number and ship in lockstep:
  one tag `vX.Y.Z` builds all release assets. Neither variant's version moves
  without the other's. *Origin: 2.1.0 (monorepo).*
- **R-parity-3** — The two variants MUST run side by side without interfering:
  separate config directories (`%APPDATA%\claude-usage-monitor` vs.
  `claude-usage-tracker-cs`), separate autostart entries, and separate
  single-instance mutexes. *Verified by: distinct constants in `AppPaths`,
  `Autostart`, `Program` (C#) / `config.py`, `autostart.py`, `__main__.py` (Py).*
- **R-parity-4** — Translations have a single source: the Python locale catalogs.
  The C# catalogs are generated (`scripts/export_locales.py`) and CI fails on
  drift. C#-only strings (settings dialog, toast hints) are the only strings
  maintained directly in the JSONs, and MUST exist in all nine languages.

## 2. Data source — Firefox cookies

- **R-cookie-1** — Cookies MUST be read **read-only** from Firefox's
  `cookies.sqlite` (SQLite read-only open), never copied and never written.
  *Verified by: `SqliteOpenMode.ReadOnly` (C#) / `mode=ro` URI (Py).*
- **R-cookie-2** — Default-container cookies MUST win over per-container cookies
  for the same name, so a container login can't shadow the real session.
  *Verified by: `FirefoxCookies` container sort (C#) / cookie merge (Py).*
- **R-cookie-3** — Profile selection MUST honour `profiles.ini`: an
  `[Install…]` default first, then a `[Profile*]` with `Default=1`, then any
  existing profile.
- **R-cookie-4** — Reading cookies MUST NOT require Firefox to be closed
  (WAL journal mode allows concurrent read-only access).

## 3. Networking & resilience

- **R-net-1** — The app talks only to: `claude.ai` (usage data),
  `api.github.com` / `github.com` (update check + opening the release page), and
  — only when the user starts an in-app update (§13) — the GitHub release asset
  hosts `github.com` / `*.githubusercontent.com` to download the signed manifest
  and installer. No other outbound requests. See also §10. *Origin: Privacy section.*
- **R-net-2** — claude.ai endpoints and response schemas are **reverse-engineered
  and undocumented**; code touching them MUST stay marked `REVERSE-ENGINEERED`
  and MUST degrade gracefully (no crash) when the schema changes.
- **R-net-3** — On HTTP 429 the poller MUST back off exponentially (double the
  effective interval per consecutive 429, capped; reset to normal on success).
  *Verified by: `PollerTests` / `NextBackoffFactor` (C#) / poller backoff tests (Py).*
- **R-net-4** — A `user_agent` config override MUST let a user fix a Cloudflare
  block after a Firefox update without a rebuild. *Origin: 1.3.0.*
- **R-net-5** — *variant-specific (build):* The **Python** release EXE MUST be
  built with the pinned Python (`.python-version`), whose OpenSSL TLS
  fingerprint Cloudflare accepts; the runner's default Python is blocked. The
  **C#** variant MUST use the WinHTTP handler at runtime for the same reason
  (the .NET sockets handler's fingerprint gets a Cloudflare 403). *Origin: 1.5.1.*
- **R-net-6** — The first poll result MUST be shown as soon as it arrives, not
  after a fixed delay (no lingering "connecting…"). *Origin: 1.3.0.*

## 4. Usage-response parsing

- **R-parse-1** — A response object is a real usage bucket **iff it carries a
  non-null `utilization`**. Sibling metadata objects (`extra_usage`, `spend`, …)
  MUST be ignored so they never surface as a bogus "Unknown (…)" bucket.
  *Origin: 2.1.1. Verified by: `test_from_api_response_skips_metadata_objects_*`
  (Py) / `FromApiResponseSkipsMetadataObjectsWithoutUtilization` (C#).*
- **R-parse-2** — Unknown *bucket* keys (a new codename with a real utilization)
  MUST still be shown with a generic "Unknown (…)" label rather than dropped, so
  a new Anthropic limit never silently disappears.
- **R-parse-3** — The 5-hour session bucket is `five_hour`; the weekly value is
  the highest non-session bucket. Bucket display order is stable (session first,
  then weekly buckets); unknown buckets sort last by ordinal key.
- **R-parse-4** — `utilization` MUST be parsed both as a plain number (current
  API) and from the older `{parsedValue|source}` object form. *Origin: pre-2026-05.*

## 5. Widget geometry & rendering

- **R-widget-1** — The widget's **bottom edge is anchored**. When runtime content
  changes its height — the peak-hour banner appearing/disappearing, or footer
  status text wrapping — the bottom edge MUST stay put and the top MUST move; the
  window MUST NOT grow downward. A peak/non-peak transition MUST NOT shift the
  widget's resting position. *Origin: 1.4.1 (Py) / this file (C# port gap).
  Verified by: `WidgetGeometryTests` + real-window harness (C#) / widget refit
  logic (Py).*
- **R-widget-2** — The saved position MUST be **height-invariant** (persist the
  bottom-edge anchor, not the live top), so restarting while the peak banner is
  showing cannot drift the widget. Legacy top-only saved files MUST migrate to a
  bottom anchor on first layout. *Verified by: `WidgetGeometryTests` (C#).*
- **R-widget-3** — Long text (footer status line, peak banner) MUST wrap to as
  many lines as needed for the current width and the window MUST grow to keep
  every line visible, shrinking back when the text gets shorter — never clipped
  at the right edge. *Origin: 1.2.0 / 1.4.2 / 1.5.1.*
- **R-widget-4** — A saved position on a monitor that no longer exists MUST be
  clamped back into the virtual desktop so the widget is never unreachable.
  *Origin: 1.3.0. Verified by: `WidgetGeometry.ClampBottom` test (C#) /
  clamp on restore (Py).*
- **R-widget-5** — When the 5-hour window has ended and the next hasn't begun,
  the footer MUST read "waiting for first message" (localized), not a countdown
  — a new session starts only with the first message. *Origin: 1.5.2.*
- **R-widget-6** — The peak-hour banner MUST show only inside Anthropic's peak
  window (weekdays 05:00–11:00 Pacific Time), converted to the OS's local zone.
  *Origin: 1.2.0. Verified by: `PeakHourWindowLocal` tests.*
- **R-widget-7** — The running version MUST be visible in the app (widget title
  row and tray menu). *Origin: 1.4.0.*

## 6. Tray icon & tooltip

- **R-tray-1** — The tray tooltip MUST be clipped to the platform limit
  (`NOTIFYICONDATAW.szTip` = 127 usable chars) so a long tooltip can never make a
  poll cycle fail. *Origin: 1.3.0. Verified by: `ClipTip` test (C#) /
  `_clip_tip` (Py).*
- **R-tray-2** — The tooltip and icon colour MUST reflect the worst-case bucket
  from the most recent poll.

## 7. Notifications

- **R-notify-1** — A threshold toast fires **once per limit per crossing**, not
  once per threshold, and MUST NOT re-fire while usage stays above the threshold.
  *Origin: 1.3.0. Verified by: `NotificationManagerTests` (C#) / notify tests (Py).*
- **R-notify-2** — A "limit has reset" toast fires **once per bucket** on a real
  reset. A slow decline in usage MUST NOT be mistaken for a reset. *Verified by:
  `NotificationManagerTests.ResetToastFiresOncePerBucket` / `SlowDeclineRearmsSilently`.*
- **R-notify-3** — Hysteresis MUST prevent oscillation around a threshold from
  producing repeat toasts. *Verified by: `HysteresisBlocksOscillation`.*
- **R-notify-4** — Desktop notifications MUST work in the packaged build (not
  only when run from source). *Origin: 1.3.0.*

## 8. Configuration

- **R-config-1** — Config is TOML at the variant's config dir (see R-parity-3).
  `%APPDATA%` MUST be resolved via the environment variable, never via the home
  directory (group-policy redirection).
- **R-config-2** — The config file is self-maintaining: on load, keys missing
  from the file MUST be written back with their defaults, so a user never has to
  add keys by hand after an update. *Origin: 1.4.0.*
- **R-config-3** — `poll_interval_seconds` MUST be floored at 10 s; anything
  lower would busy-loop against claude.ai. *Verified by: `Config` load (C#) /
  `Config.load` (Py).*
- **R-config-4** — Every variant MUST support at least: `language`,
  `poll_interval_seconds`, `update_check`, `skip_update_version`, `user_agent`,
  `autostart`, `log_level`. A lowercase `log_level` MUST NOT crash startup.
  *Origin: 1.3.0 / 1.4.0 / 1.5.0.*
- **R-config-5** — Log entries MUST stay English regardless of UI language so
  logs remain shareable for support. *Origin: 1.5.0.*

## 9. Application lifecycle

- **R-life-1** — Launching a second instance MUST NOT start a second tray icon;
  it MUST detect the running instance (named mutex) and exit with a hint. Doubling
  the instances would double every request to claude.ai. *Origin: 1.4.0.*
- **R-life-2** — The autostart (HKCU Run) entry MUST be kept in sync with the
  `autostart` config value on every start (a moved EXE re-registers itself).
  Only the packaged build registers itself. *Origin: 1.4.0.*
- **R-life-3** — The update check runs **once per app start only** (never
  periodic — explicit owner decision). If a newer GitHub release exists it offers
  Open / Skip / Cancel; "Skip version" persists to `skip_update_version` and a
  release newer than the skipped one shows the dialog again. *Origin: 1.3.0 / 1.4.0.*
- **R-life-4** — The update checker compares against the latest GitHub release
  tag; a tag higher than the running version shows every user an update dialog,
  so a tag MUST never be pushed without bumping the version first.
- **R-life-5** — Both variants MUST offer an **on-demand "Check for updates"**
  action in the tray menu, independent of the once-per-start check and of the
  `update_check` config value. A manual check MUST distinguish three outcomes:
  a newer release (show the update dialog), up-to-date, and check-failed — a
  network error MUST NOT be reported as "up to date". It MUST ignore
  `skip_update_version` so a previously-skipped release still surfaces on an
  explicit check. *Origin: this file. Verified by: `UpdateCheckTests.Evaluate*`
  (C#) / `test_update_check.py` `evaluate_release` / `check_detailed` tests (Py).*

## 10. Privacy & security

- **R-priv-1** — No telemetry, analytics, or outbound request beyond the two
  hosts in R-net-1. The README Privacy section MUST list every outbound request
  and MUST be updated whenever a new one is added.
- **R-priv-2** — Cookies are read locally and sent only to claude.ai over HTTPS;
  they MUST NOT be persisted by the app or sent anywhere else (see R-cookie-1).
- **R-priv-3** — The app is not affiliated with Anthropic and MUST say so where
  it identifies itself.

## 11. Localization

- **R-i18n-1** — All user-visible text (widget, tray menu, notifications, dialogs,
  errors) MUST be available in the nine supported languages
  (en, de, fr, es, it, pt, nl, pl, ru). *Origin: 1.5.0.*
- **R-i18n-2** — Language follows the Windows display language by default; a
  `language` config value pins it. Placeholder/key parity across catalogs MUST
  be enforced by a test. *See R-parity-4.*

## 12. Build & release

- **R-rel-1** — Each variant has a single version source (Python `__init__.py`
  `__version__`; C# csproj `<Version>`). `scripts/bump_version.ps1 X.Y.Z` sets
  both. *Origin: 1.4.0 / 2.1.0.*
- **R-rel-2** — A release requires a matching `CHANGELOG.md` section; the release
  workflow **hard-fails** without one. This guard MUST NOT be removed.
- **R-rel-3** — A version-consistency guard MUST fail the release if the tag, the
  Python version, and the C# version disagree.
- **R-rel-4** — A release MUST publish all four assets (`ClaudeUsageTracker.exe`,
  `ClaudeUsageTracker-Setup-X.Y.Z.exe`, `ClaudeUsageTracker-Portable-X.Y.Z.exe`,
  `SHA256SUMS.txt`); the workflow MUST hard-check the C# Setup EXE exists (the
  build only warns if Inno Setup is missing).
- **R-rel-5** — Local and CI builds MUST run the same quality gates
  (changelog check, byte-compile/build, full test suite) so a build can't ship
  stale or untested code. *Origin: 1.4.3.*

## 13. In-app update download & install

*variant-specific (C# installer build).* The **portable** C# EXE and the
**Python** variant MUST NOT self-update; they keep the "open GitHub" path
(self-replacing an arbitrarily-located single-file EXE is unsafe). Auto-install
is gated to the installed build (`INSTALLER_UPDATER`). The overriding goal:
**a compromised GitHub account, repository, or CI MUST NOT be able to make the
app install an attacker's build.**

- **R-update-1** — The installer build MAY offer, from the update dialog, to
  download and install a newer release. It MUST do so only after the user
  explicitly starts it (no silent/background auto-update). *Verified by: real
  install run (GUI/OS) — see CHANGELOG Unreleased; `UpdateVerifierTests`.*
- **R-update-2** — An update MUST be installed only if a detached signature over
  the exact `update.json` manifest bytes verifies against a **public key embedded
  in the app** (`UpdateKeys.json`), using an **offline** private key that never
  exists in the repo or CI. A tampered manifest or a signature from any other key
  MUST be refused. This is the anchor that a checksum file cannot provide (whoever
  can replace the installer can replace its checksum). *Verified by:
  `UpdateVerifierTests` (tamper/untrusted-key/malformed) + `UpdateTool` roundtrip.*
- **R-update-3** — The downloaded installer's bytes MUST match the SHA-256 and
  size recorded in the **signed** manifest (constant-time compare) before it is
  executed. *Verified by: `UpdateVerifierTests.DownloadedBytesMustMatchSignedDigest`.*
- **R-update-4** — **Anti-rollback:** the manifest version MUST be strictly newer
  than the anti-rollback floor; an equal or older version MUST be refused even if
  validly signed. The floor MUST be the greater of the running version and a
  **persisted highest-seen version** (`update_version_floor` in config), raised on
  every start and never lowered — so a later, legitimately-signed but *older*
  release cannot be pushed onto an install that has already run a newer version.
  *Verified by: `UpdateVerifierTests.EqualOrOlderVersionIsRejected`,
  `UpdateVerifierTests.SignedButOlderThanFloorIsRejected`,
  `UpdateVerifierTests.HigherVersionPicksTheGreater`; floor persistence in
  `AppOrchestrator.RaiseVersionFloor` + `ConfigTests`.*
- **R-update-5** — Assets MUST be downloaded only over HTTPS from
  `github.com` / `*.githubusercontent.com`; every redirect hop MUST be
  re-validated against that allow-list, downloads MUST be size-capped and
  time-limited, and the verified installer MUST land in a fresh per-user
  directory and be executed by that exact path (no TOCTOU window). *Verified by:
  `UpdateVerifierTests.OnlyGithubHttpsAssetUrlsAreAllowed`; download hardening in
  `UpdateInstaller`.*
- **R-update-6** — **Fail closed.** Any failure (no embedded key, bad signature,
  hash mismatch, disallowed host, missing asset, network error) MUST abort the
  install and leave the running app untouched; with no embedded key the feature
  is inert and no update is ever accepted. *Verified by:
  `UpdateVerifierTests.NoEmbeddedKeyFailsClosed` and the malformed-input tests.*
- **R-update-7** — **Signing can never be forgotten.** CI publishes every release
  as a **draft**; the update check follows `releases/latest`, which ignores
  drafts, so no client can see a release without a signed manifest. A release goes
  live only through local signing with the **offline** key: `scripts/release.ps1`
  (one command: bump → tag → push → wait for the draft → sign → publish) wrapping
  `scripts/publish_release.ps1`, which signs, self-verifies against the embedded
  public key, uploads `update.json(.sig)` and only then publishes. The signing key
  is never placed in CI (an owner decision: a compromised CI must not be able to
  sign). A CI **release-integrity** guard independently re-verifies each published
  release with the app's own verifier and fails if it is unsigned/invalid.
  *Verified by: `release.yml` (draft), `release.ps1`/`publish_release.ps1`
  self-verify, `.github/workflows/release-integrity.yml`.*
- **R-update-8** — Multiple embedded public keys MUST be supported so a key can be
  rotated (ship a build trusting old+new before signing with the new key).
  *Verified by: `UpdateVerifierTests.SignatureVerifiesUnderAnyEmbeddedKey`.*
