# Security Policy

## Supported versions

| Version | Security updates |
|---------|-----------------|
| 1.x (latest) | ✅ Yes |
| < 1.0 | ❌ No |

Only the latest release receives security fixes. Please update before reporting.

---

## Scope

This tool reads Firefox cookies from your local SQLite database and calls internal, undocumented `claude.ai` endpoints. The following are considered **in scope** for vulnerability reports:

- Unauthorised access to or exfiltration of cookie data
- Path traversal or arbitrary file read via `firefox_profile_path` in `config.toml`
- SQL injection in the Firefox cookie database query
- Insecure HTTP behaviour (missing TLS verification, redirect following to untrusted hosts)
- Privilege escalation or code execution through the Windows tray or widget
- Sensitive data written to log files or the config directory (`%APPDATA%\claude-usage-monitor\`)

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
- Steps to reproduce (operating system, Python version, browser version if relevant)
- Affected file(s) and line numbers if known
- A proof-of-concept or example config if applicable

---

## Response timeline

| Step | Target |
|------|--------|
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
The tool opens `cookies.sqlite` read-only using a WAL-mode SQLite connection. Cookie values are held in memory only for the duration of each poll and are never written to disk.

**No credentials are stored.**
The tool does not persist cookies, tokens, or passwords. The config file (`config.toml`) stores only poll interval, log level, and an optional profile path.

**Network requests go only to `claude.ai`.**
The tool makes HTTPS requests exclusively to `https://claude.ai`. No data is sent to any other host.

**The `claude.ai` endpoints used are undocumented.**
This is a known limitation described in the README. These endpoints may change without notice and are not endorsed by Anthropic.
