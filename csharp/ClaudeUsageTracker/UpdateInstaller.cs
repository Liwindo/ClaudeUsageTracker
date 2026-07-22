// In-app updater: download → verify → install, fail-closed at every step.
//
// This is the I/O around the pure trust gate (UpdateVerifier). It downloads the
// signed manifest, its detached signature and the Setup installer from the
// GitHub release, refuses anything that does not verify against the embedded
// offline public key, and only then launches the installer.
//
// It is deliberately conservative about the network: every hop must stay on an
// allow-listed HTTPS GitHub host (no open redirects to an attacker's server),
// every download is size-capped and time-limited, and the installer bytes are
// re-hashed against the SIGNED manifest before a single byte is executed.
//
// HOW IT INSTALLS — and why it looks completely ordinary to security software.
// Antivirus behaviour engines (e.g. Bitdefender ATC) score a process on what it
// DOES, and the classic dropper fingerprint is: a program spawns a hidden script
// interpreter that SILENTLY runs a freshly-downloaded EXE out of %TEMP%. We do
// none of that — a false positive there would damage the project's reputation
// far more than it would help. Instead the updater:
//   * stages the verified installer under %LOCALAPPDATA% (this app's own folder),
//     never %TEMP%;
//   * launches it exactly the way a person double-clicking it would — a normal,
//     VISIBLE Inno Setup wizard via ShellExecute, with NO command-line switches,
//     NO silent/unattended flags, and NO intermediate powershell/cmd;
//   * lets the installer itself relaunch the app on its Finish page ([Run]
//     postinstall), so there is no second process-spawn to explain either.
// The app then quits so the running EXE is unlocked for replacement. See
// REQUIREMENTS.md R-update-9.
//
// Feature-gated: only the installer build (INSTALLER_UPDATER) ever calls Run —
// the portable single-EXE cannot safely replace itself, so it keeps the
// "open GitHub" path.

using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;

namespace ClaudeUsageTracker;

public enum UpdateStage { Downloading, Verifying, Installing }

/// <summary>Result of an install attempt. <see cref="Started"/> true means the
/// installer was launched and the app MUST now quit so its files can be
/// replaced; the new version relaunches automatically.</summary>
public sealed record UpdateOutcome(bool Started, string? Error)
{
    public static UpdateOutcome Ok() => new(true, null);
    public static UpdateOutcome Fail(string error) => new(false, error);
}

public static class UpdateInstaller
{
    private const string ManifestName = "update.json";
    private const string SignatureName = "update.json.sig";
    private const int MaxRedirects = 6;
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(60);

    /// <summary>Download, verify and launch the update for <paramref name="info"/>.
    /// Reports coarse progress through <paramref name="onStage"/>. Never throws —
    /// any failure returns <see cref="UpdateOutcome.Fail"/> with a log-worthy
    /// message and leaves the running app untouched (fail-closed).</summary>
    public static UpdateOutcome Run(UpdateInfo info, string currentVersion, Action<UpdateStage> onStage)
    {
        try
        {
            var setupName = $"ClaudeUsageTracker-Setup-{info.LatestVersion}.exe";
            var manifestUrl = FindAssetUrl(info, ManifestName);
            var signatureUrl = FindAssetUrl(info, SignatureName);
            var setupUrl = FindAssetUrl(info, setupName);
            if (manifestUrl is null || signatureUrl is null || setupUrl is null)
                return UpdateOutcome.Fail(
                    "release is missing a signed manifest or the Setup installer — refusing to install");

            // Belt-and-suspenders: the URLs came from GitHub's API, but re-check
            // that each is an allow-listed HTTPS host before touching it.
            foreach (var url in new[] { manifestUrl, signatureUrl, setupUrl })
                if (!UpdateVerifier.IsAllowedAssetUrl(url))
                    return UpdateOutcome.Fail($"refusing non-GitHub asset URL: {url}");

            onStage(UpdateStage.Downloading);
            var manifestBytes = Download(manifestUrl, UpdateManifest.MaxBytes);
            var signature = ParseSignature(Download(signatureUrl, UpdateVerifier.MaxSignatureBytes * 4));

            onStage(UpdateStage.Verifying);
            var verification = UpdateVerifier.Verify(
                manifestBytes, signature, setupName, currentVersion, UpdateKeys.PublicKeys);
            if (!verification.Ok)
            {
                Log.Warning("update", $"Update rejected: {verification.Error}");
                return UpdateOutcome.Fail(verification.Error!);
            }

            onStage(UpdateStage.Downloading);
            var setupBytes = Download(setupUrl, UpdateVerifier.MaxInstallerBytes);
            if (!UpdateVerifier.AssetContentMatches(verification.Asset!, setupBytes))
            {
                Log.Warning("update", "Downloaded installer does not match the signed digest — discarding.");
                return UpdateOutcome.Fail("downloaded installer failed the signed integrity check");
            }

            // Stage under %LOCALAPPDATA% (never %TEMP%), in a fresh per-user
            // subdirectory, and run THAT exact file — no window for another
            // writer to swap it (TOCTOU-safe). Sweep any leftovers from a prior
            // update first so installers never pile up.
            CleanUpStagedInstallers();
            var dir = Path.Combine(AppPaths.UpdatesDir, Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            var setupPath = Path.Combine(dir, setupName);
            File.WriteAllBytes(setupPath, setupBytes);

            onStage(UpdateStage.Installing);
            LaunchInstaller(setupPath);
            Log.Info("update", $"Verified installer {info.LatestVersion} launched (visible); quitting for replacement.");
            return UpdateOutcome.Ok();
        }
        catch (Exception exc)
        {
            Log.Warning("update", $"Update install failed: {exc.Message}");
            return UpdateOutcome.Fail(exc.Message);
        }
    }

    private static string? FindAssetUrl(UpdateInfo info, string name) =>
        info.Assets.FirstOrDefault(a => string.Equals(a.Name, name, StringComparison.Ordinal))?.DownloadUrl;

    private static byte[] ParseSignature(byte[] raw)
    {
        // The .sig asset is base64 text (optionally with a trailing newline).
        var text = System.Text.Encoding.ASCII.GetString(raw).Trim();
        return Convert.FromBase64String(text);
    }

    /// <summary>HTTPS GET with a hard size cap and manual redirect handling that
    /// re-validates the host on every hop — a redirect can never send the
    /// download to a non-GitHub server.</summary>
    private static byte[] Download(string url, long cap)
    {
        using var handler = new HttpClientHandler { AllowAutoRedirect = false };
        using var http = new HttpClient(handler) { Timeout = Timeout };

        var current = url;
        for (var hop = 0; hop < MaxRedirects; hop++)
        {
            if (!UpdateVerifier.IsAllowedAssetUrl(current))
                throw new InvalidOperationException($"refusing non-GitHub host: {current}");

            using var request = new HttpRequestMessage(HttpMethod.Get, current);
            request.Headers.TryAddWithoutValidation("User-Agent", "claude-usage-tracker-cs");
            using var response = http.Send(request, HttpCompletionOption.ResponseHeadersRead);

            if ((int)response.StatusCode is >= 300 and < 400)
            {
                var location = response.Headers.Location
                    ?? throw new InvalidOperationException("redirect without a Location header");
                current = location.IsAbsoluteUri
                    ? location.ToString()
                    : new Uri(new Uri(current), location).ToString();
                continue;
            }
            if (response.StatusCode != HttpStatusCode.OK)
                throw new InvalidOperationException($"HTTP {(int)response.StatusCode} for {current}");
            if (response.Content.Headers.ContentLength is long len && len > cap)
                throw new InvalidOperationException($"response exceeds {cap} bytes");

            using var stream = response.Content.ReadAsStream();
            return ReadCapped(stream, cap);
        }
        throw new InvalidOperationException("too many redirects");
    }

    private static byte[] ReadCapped(Stream stream, long cap)
    {
        using var buffer = new MemoryStream();
        var chunk = new byte[81920];
        int read;
        while ((read = stream.Read(chunk, 0, chunk.Length)) > 0)
        {
            if (buffer.Length + read > cap)
                throw new InvalidOperationException($"download exceeds {cap} bytes");
            buffer.Write(chunk, 0, read);
        }
        return buffer.ToArray();
    }

    /// <summary>Launch the verified installer the way a person double-clicking it
    /// would: a normal, VISIBLE Inno Setup wizard via ShellExecute, with NO
    /// command-line switches (no silent/unattended flags) and NO intermediate
    /// shell. The installer is per-user, so it never elevates; it closes the
    /// running app via its Restart Manager and relaunches it from its Finish page
    /// ([Run] postinstall). Nothing here resembles a dropper — see the file
    /// header and REQUIREMENTS.md R-update-9. The caller quits the app afterwards
    /// so the in-use EXE is unlocked for replacement.</summary>
    private static void LaunchInstaller(string setupPath)
    {
        // UseShellExecute = true → ShellExecute, i.e. the exact "open this file"
        // action Explorer performs on a double-click. No hidden window, no args.
        Process.Start(new ProcessStartInfo(setupPath) { UseShellExecute = true });
    }

    /// <summary>Best-effort removal of installers staged by earlier updates, so
    /// %LOCALAPPDATA%\...\updates never accumulates. Called at app startup (so the
    /// installer used for THIS update is gone once the freshly-installed version
    /// relaunches) and again before staging a new download. A file still locked by
    /// an in-flight installer is simply skipped and cleaned up on the next start.
    /// </summary>
    public static void CleanUpStagedInstallers()
    {
        try
        {
            if (Directory.Exists(AppPaths.UpdatesDir))
                Directory.Delete(AppPaths.UpdatesDir, recursive: true);
        }
        catch (Exception exc)
        {
            Log.Info("update", $"Could not remove staged update installer(s): {exc.Message}");
        }
    }
}
