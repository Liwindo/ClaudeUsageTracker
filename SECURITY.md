# Security Policy

## Supported versions

| Version | Security updates |
| --- | --- |
| 2.x (latest) | ✅ Yes |
| < 2.0 | ❌ No |

Only the latest release receives security fixes. Both variants (the Python EXE and the C# installer/portable version) are released together under one version number. Please update before reporting.

---

## Scope

This tool reads Firefox cookies from your local SQLite database and calls internal, undocumented `claude.ai` endpoints. The following are considered **in scope** for vulnerability reports:

- Unauthorised access to or exfiltration of cookie data
- Path traversal or arbitrary file read via `firefox_profile_path` in `config.toml`
- SQL injection in the Firefox cookie database query
- Insecure HTTP behaviour (missing TLS verification, redirect following to untrusted hosts)
- Privilege escalation or code execution through the Windows tray or widget
- Getting the C# in-app updater to download from a non-GitHub host, or to install a file whose signed manifest or digest does not verify
- Sensitive data written to log files or the config directories (`%APPDATA%\claude-usage-monitor\` for the Python variant, `%APPDATA%\claude-usage-tracker-cs\` for the C# variant)

The following are **out of scope**:

- Security issues in `claude.ai` itself or Anthropic's infrastructure
- Issues that require physical access to the machine
- Bugs in third-party dependencies without a demonstrated impact on this project
- The use of undocumented Anthropic API endpoints (acknowledged in the README — this is a known design constraint, not a vulnerability)

---

## Reporting a vulnerability

**Please do not open a public GitHub Issue for security vulnerabilities.**

Use GitHub's private vulnerability reporting instead:

1. Go to **[Security → Advisories](https://github.com/Liwindo/ClaudeUsageTracker/security/advisories/new)**
2. Click **"Report a vulnerability"**
3. Fill in the form with as much detail as possible

Alternatively, you can reach out directly via the GitHub profile of the maintainer: [@Liwindo](https://github.com/Liwindo).

### What to include

A useful report contains:

- A clear description of the vulnerability and its potential impact
- Steps to reproduce: which variant and version (Python EXE, C# installer or C# portable), Windows version, and browser version if relevant
- Affected file(s) and line numbers if known
- A proof-of-concept or example config if applicable

---

## Response timeline

| Step | Target |
| --- | --- |
| Acknowledgement | Within 72 hours |
| Initial assessment | Within 7 days |
| Fix or mitigation | Within 30 days for high/critical issues |
| Public disclosure | After a fix is released, coordinated with the reporter |

---

## Disclosure policy

This project follows **coordinated disclosure**. Please allow reasonable time for a fix before publishing details publicly. Credit will be given to reporters in the release notes unless anonymity is requested.

---

## Security-relevant design decisions

A few aspects of this project are intentional but worth understanding from a security perspective:

**Firefox cookies are read in-process, without copying the file.**
Both variants open `cookies.sqlite` read-only (SQLite `mode=ro` / `SqliteOpenMode.ReadOnly`); Firefox's WAL journal lets this coexist with a running browser. Cookie values are held in memory only for the duration of each poll and are never written to disk.

**No credentials are stored.**
The tool does not persist cookies, tokens, or passwords. The config files hold settings only: poll interval, notification thresholds, log level, an optional Firefox profile path and User-Agent, update preferences, autostart and language. More verbose log levels record the organisation UUID in request URLs (Python variant from `INFO`, C# variant from `DEBUG`), and the Python variant's `DEBUG` level also logs the full usage response, so the default is `WARNING`.

**Cookies and usage data go only to `claude.ai`.**
Usage data is fetched over HTTPS from `https://claude.ai` only. Besides that, each app start makes one anonymous request to `api.github.com` for the latest release version, and only when a newer version exists, a second one to the same host for the release notes shown in the update dialog. Neither carries cookies or usage data, and `update_check = false` turns both off. Choosing "Check for updates" or "Release notes" in the tray menu makes the same requests on demand. The Python variant and the C# portable version only open the GitHub release page in your browser when you choose to update.

**In-app updates are signed with an offline key (C# installer version).**
The installed C# version can download and install an update itself. It downloads only from `github.com` / `*.githubusercontent.com`, and runs the installer only after verifying an ECDSA P-256 signature over the release manifest plus the installer's SHA-256 digest. The signing key is kept offline and never reaches CI, so a compromised build pipeline or GitHub account cannot produce an update the app accepts. The installer starts as a normal, visible setup wizard. A CI job additionally re-verifies every published release's signature.

**Release notes are shown as plain text only.**
The update dialog shows the GitHub release texts of the versions you would get, and "Release notes" in the tray menu shows those of every version. Like everything else from GitHub, they are treated as untrusted. They are reduced to plain text with bold at most: no HTML is rendered, links are shown as text and cannot be clicked, invisible control and format characters (such as bidi overrides) are removed, and the amount shown is capped. The only way out of the dialog stays the checked "Open GitHub" button.

**The `claude.ai` endpoints used are undocumented.**
This is a known limitation described in the README. These endpoints may change without notice and are not endorsed by Anthropic.
