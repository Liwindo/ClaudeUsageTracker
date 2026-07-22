// Startup check for a newer release on GitHub.
//
// Queries the public GitHub REST API once per app start and compares the
// latest release tag against the running version. Any network/API/parsing
// problem is logged and swallowed — the check must never affect normal
// operation.

using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ClaudeUsageTracker;

/// <summary>One asset attached to a GitHub release.</summary>
public sealed record ReleaseAsset(string Name, string DownloadUrl);

public sealed record UpdateInfo(string LatestVersion, string Url, IReadOnlyList<ReleaseAsset> Assets);

public enum UpdateCheckStatus { UpToDate, Available, Failed }

/// <summary>Outcome of an update check. <see cref="Info"/> is set only when
/// <see cref="Status"/> is <see cref="UpdateCheckStatus.Available"/>.</summary>
public sealed record UpdateCheckResult(UpdateCheckStatus Status, UpdateInfo? Info)
{
    public static readonly UpdateCheckResult UpToDate = new(UpdateCheckStatus.UpToDate, null);
    public static readonly UpdateCheckResult Failed = new(UpdateCheckStatus.Failed, null);
}

public static partial class UpdateCheck
{
    private const string Repo = "Liwindo/ClaudeUsageTracker";
    private static readonly string ReleasesApi = $"https://api.github.com/repos/{Repo}/releases/latest";
    public static readonly string RepoReleasesUrl = $"https://github.com/{Repo}/releases/latest";

    [GeneratedRegex(@"^v?(\d+(?:\.\d+)*)")]
    private static partial Regex VersionRegex();

    /// <summary>The running app version, e.g. "2.0.0" (from the csproj Version).</summary>
    public static string CurrentVersion
    {
        get
        {
            var info = Assembly.GetExecutingAssembly()
                .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion ?? "0.0.0";
            // Strip any "+commithash" source-link suffix.
            var plus = info.IndexOf('+');
            return plus >= 0 ? info[..plus] : info;
        }
    }

    /// <summary>'v1.2.0' / '1.2' → [1, 2, 0] / [1, 2]. Empty if unparseable —
    /// including components beyond int range, which must not throw.</summary>
    internal static int[] ParseVersion(string version)
    {
        var match = VersionRegex().Match(version.Trim());
        if (!match.Success)
            return [];
        var parts = match.Groups[1].Value.Split('.');
        var result = new int[parts.Length];
        for (var i = 0; i < parts.Length; i++)
        {
            if (!int.TryParse(parts[i], out result[i]))
                return [];
        }
        return result;
    }

    internal static bool IsNewer(string remote, string local)
    {
        var r = ParseVersion(remote);
        var l = ParseVersion(local);
        if (r.Length == 0 || l.Length == 0)
            return false;
        // Pad to equal length so '1.2' vs '1.2.0' compares equal instead of
        // shorter-is-less.
        var width = Math.Max(r.Length, l.Length);
        for (var i = 0; i < width; i++)
        {
            var rv = i < r.Length ? r[i] : 0;
            var lv = i < l.Length ? l[i] : 0;
            if (rv != lv)
                return rv > lv;
        }
        return false;
    }

    /// <summary>Return UpdateInfo if GitHub has a newer release than the
    /// running version, else null. Never throws. Thin wrapper over
    /// <see cref="CheckDetailed"/> for the once-per-start path.</summary>
    /// <param name="skipVersion">A version the user chose to skip via the
    /// update dialog. That exact release is silently ignored; anything newer
    /// than it still triggers the dialog.</param>
    public static UpdateInfo? CheckForUpdate(string skipVersion = "") =>
        CheckDetailed(skipVersion).Info;

    /// <summary>Query GitHub and report the outcome, distinguishing "up to
    /// date" from "the check failed" — the manual "check now" action needs that
    /// difference so it never claims you are current after a network error.
    /// Never throws. Pass skipVersion="" (the default) for a manual check so a
    /// previously-skipped release is still surfaced.</summary>
    public static UpdateCheckResult CheckDetailed(string skipVersion = "")
    {
        string body;
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
            using var request = new HttpRequestMessage(HttpMethod.Get, ReleasesApi);
            request.Headers.TryAddWithoutValidation("Accept", "application/vnd.github+json");
            // GitHub's API rejects requests without a User-Agent.
            request.Headers.TryAddWithoutValidation("User-Agent", "claude-usage-tracker-cs");
            using var resp = http.Send(request);
            if ((int)resp.StatusCode != 200)
            {
                Log.Info("update", $"Update check: GitHub returned {(int)resp.StatusCode}.");
                return UpdateCheckResult.Failed;
            }
            using var reader = new StreamReader(resp.Content.ReadAsStream());
            body = reader.ReadToEnd();
        }
        catch (Exception exc)
        {
            Log.Info("update", $"Update check failed: {exc.Message}");
            return UpdateCheckResult.Failed;
        }

        return Evaluate(body, skipVersion, CurrentVersion);
    }

    /// <summary>Pure decision over an already-fetched release payload — no
    /// network, so it is exhaustively unit-testable. A malformed body reads as a
    /// failed check (never "up to date"); an equal/older/skipped tag is up to
    /// date; a newer tag is available with its asset download URLs. Never throws.
    /// </summary>
    internal static UpdateCheckResult Evaluate(string body, string skipVersion, string currentVersion)
    {
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(body);
        }
        catch (JsonException)
        {
            Log.Info("update", "Update check: response was not valid JSON.");
            return UpdateCheckResult.Failed;
        }

        using (doc)
        {
            if (doc.RootElement.ValueKind is not JsonValueKind.Object)
            {
                Log.Info("update", $"Update check: unexpected response shape ({doc.RootElement.ValueKind}).");
                return UpdateCheckResult.Failed;
            }

            var tag = doc.RootElement.TryGetProperty("tag_name", out var tagEl) && tagEl.ValueKind is JsonValueKind.String
                ? tagEl.GetString()!.Trim()
                : "";
            if (string.IsNullOrEmpty(tag) || !IsNewer(tag, currentVersion))
            {
                Log.Debug("update", $"Update check: {currentVersion} is up to date (latest: {(tag.Length > 0 ? tag : "?")}).");
                return UpdateCheckResult.UpToDate;
            }

            var latest = tag.TrimStart('v', 'V');
            if (!string.IsNullOrEmpty(skipVersion) && latest == skipVersion.TrimStart('v', 'V'))
            {
                Log.Info("update", $"Update {latest} available but skipped by user preference.");
                return UpdateCheckResult.UpToDate;
            }

            var url = doc.RootElement.TryGetProperty("html_url", out var urlEl) &&
                      urlEl.ValueKind is JsonValueKind.String &&
                      !string.IsNullOrEmpty(urlEl.GetString())
                ? urlEl.GetString()!
                : RepoReleasesUrl;

            // Asset download URLs (name → browser_download_url) for the in-app
            // installer. Absent/odd shapes are simply skipped; the installer
            // fails closed if a needed asset is missing.
            var assets = new List<ReleaseAsset>();
            if (doc.RootElement.TryGetProperty("assets", out var assetsEl) &&
                assetsEl.ValueKind is JsonValueKind.Array)
            {
                foreach (var a in assetsEl.EnumerateArray())
                {
                    if (a.ValueKind is not JsonValueKind.Object)
                        continue;
                    var name = a.TryGetProperty("name", out var nEl) && nEl.ValueKind is JsonValueKind.String
                        ? nEl.GetString() : null;
                    var dl = a.TryGetProperty("browser_download_url", out var dEl) && dEl.ValueKind is JsonValueKind.String
                        ? dEl.GetString() : null;
                    if (!string.IsNullOrEmpty(name) && !string.IsNullOrEmpty(dl))
                        assets.Add(new ReleaseAsset(name, dl));
                }
            }

            Log.Info("update", $"Update available: {tag} (running {currentVersion}).");
            return new UpdateCheckResult(UpdateCheckStatus.Available, new UpdateInfo(latest, url, assets));
        }
    }
}
