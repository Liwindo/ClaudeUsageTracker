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

public sealed record UpdateInfo(string LatestVersion, string Url);

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
    /// running version, else null. Never throws.</summary>
    /// <param name="skipVersion">A version the user chose to skip via the
    /// update dialog. That exact release is silently ignored; anything newer
    /// than it still triggers the dialog.</param>
    public static UpdateInfo? CheckForUpdate(string skipVersion = "")
    {
        JsonDocument doc;
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
                return null;
            }
            using var reader = new StreamReader(resp.Content.ReadAsStream());
            doc = JsonDocument.Parse(reader.ReadToEnd());
        }
        catch (Exception exc)
        {
            Log.Info("update", $"Update check failed: {exc.Message}");
            return null;
        }

        using (doc)
        {
            if (doc.RootElement.ValueKind is not JsonValueKind.Object)
            {
                Log.Info("update", $"Update check: unexpected response shape ({doc.RootElement.ValueKind}).");
                return null;
            }

            var tag = doc.RootElement.TryGetProperty("tag_name", out var tagEl) && tagEl.ValueKind is JsonValueKind.String
                ? tagEl.GetString()!.Trim()
                : "";
            if (string.IsNullOrEmpty(tag) || !IsNewer(tag, CurrentVersion))
            {
                Log.Debug("update", $"Update check: {CurrentVersion} is up to date (latest: {(tag.Length > 0 ? tag : "?")}).");
                return null;
            }

            var latest = tag.TrimStart('v', 'V');
            if (!string.IsNullOrEmpty(skipVersion) && latest == skipVersion.TrimStart('v', 'V'))
            {
                Log.Info("update", $"Update {latest} available but skipped by user preference.");
                return null;
            }

            var url = doc.RootElement.TryGetProperty("html_url", out var urlEl) &&
                      urlEl.ValueKind is JsonValueKind.String &&
                      !string.IsNullOrEmpty(urlEl.GetString())
                ? urlEl.GetString()!
                : RepoReleasesUrl;
            Log.Info("update", $"Update available: {tag} (running {CurrentVersion}).");
            return new UpdateInfo(latest, url);
        }
    }
}
