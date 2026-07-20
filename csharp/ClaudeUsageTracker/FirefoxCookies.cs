// Read claude.ai session cookies directly from Firefox's cookie store.
//
// Firefox stores cookies unencrypted in an SQLite database at:
//   %APPDATA%\Mozilla\Firefox\Profiles\<profile>\cookies.sqlite
//
// The database is opened read-only. Firefox's WAL journal mode allows
// concurrent reads without needing a file copy.

using System.IO;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;

namespace ClaudeUsageTracker;

/// <summary>Raised when cookies cannot be read from Firefox's profile.</summary>
public class FirefoxCookieException : Exception
{
    public FirefoxCookieException(string message) : base(message) { }
    public FirefoxCookieException(string message, Exception inner) : base(message, inner) { }
}

/// <summary>Browser-agnostic cookie error used for org-ID failures.</summary>
public class CookieException : Exception
{
    public CookieException(string message) : base(message) { }
}

public static partial class FirefoxCookies
{
    private const string ClaudeHost = "claude.ai";

    [GeneratedRegex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
    private static partial Regex UuidRegex();

    private static string FirefoxAppData
    {
        get
        {
            // Respect %APPDATA% — profiles redirected via group policy don't
            // live under the user-profile folder.
            var appdata = Environment.GetEnvironmentVariable("APPDATA");
            var baseDir = !string.IsNullOrEmpty(appdata)
                ? appdata
                : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AppData", "Roaming");
            return Path.Combine(baseDir, "Mozilla", "Firefox");
        }
    }

    /// <summary>Locate the default Firefox profile directory on Windows.
    /// Prefers the profile named in an [Install…] section, then the first
    /// [Profile*] section with Default=1, then any existing profile.</summary>
    internal static string FindDefaultProfile(string? firefoxAppData = null)
    {
        var appData = firefoxAppData ?? FirefoxAppData;
        var profilesIni = Path.Combine(appData, "profiles.ini");
        if (!File.Exists(profilesIni))
        {
            throw new FirefoxCookieException(
                $"Firefox profiles.ini not found at {profilesIni}. Is Firefox installed?");
        }

        var sections = ParseIni(profilesIni);

        foreach (var (name, values) in sections)
        {
            if (!name.StartsWith("Install", StringComparison.Ordinal))
                continue;
            if (!values.TryGetValue("Default", out var installDefault) || string.IsNullOrEmpty(installDefault))
                continue;
            var candidate = Path.Combine(appData, installDefault);
            if (Directory.Exists(candidate))
                return candidate;
        }

        // Fallback: scan [Profile*] sections, honouring the Default=1 flag.
        string? fallback = null;
        foreach (var (name, values) in sections)
        {
            if (!name.StartsWith("Profile", StringComparison.Ordinal))
                continue;
            var relative = values.GetValueOrDefault("IsRelative", "1") == "1";
            var pathStr = values.GetValueOrDefault("Path", "");
            var profilePath = relative ? Path.Combine(appData, pathStr) : pathStr;
            if (!Directory.Exists(profilePath))
                continue;
            if (values.GetValueOrDefault("Default") == "1")
                return profilePath;
            fallback ??= profilePath;
        }

        if (fallback is not null)
            return fallback;

        throw new FirefoxCookieException("No usable Firefox profile directory found.");
    }

    /// <summary>Minimal INI parser. Values are literal (no interpolation) —
    /// profiles.ini paths may contain '%' characters.</summary>
    private static List<(string Section, Dictionary<string, string> Values)> ParseIni(string path)
    {
        var sections = new List<(string, Dictionary<string, string>)>();
        Dictionary<string, string>? current = null;
        foreach (var rawLine in File.ReadAllLines(path))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith(';') || line.StartsWith('#'))
                continue;
            if (line.StartsWith('[') && line.EndsWith(']'))
            {
                current = [];
                sections.Add((line[1..^1], current));
                continue;
            }
            var eq = line.IndexOf('=');
            if (eq > 0 && current is not null)
                current[line[..eq].Trim()] = line[(eq + 1)..].Trim();
        }
        return sections;
    }

    /// <summary>Read all non-expired cookies for <paramref name="host"/>
    /// directly, without copying the database.
    /// Matches the exact host and any subdomain (host-only `claude.ai` and
    /// domain cookies stored as `.claude.ai` / `.sub.claude.ai`).</summary>
    internal static Dictionary<string, string> QueryCookies(string dbPath, string host)
    {
        var nowSeconds = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        try
        {
            using var conn = new SqliteConnection(new SqliteConnectionStringBuilder
            {
                DataSource = dbPath,
                Mode = SqliteOpenMode.ReadOnly,
                Pooling = false, // don't hold a handle on Firefox's DB after the poll
            }.ToString());
            conn.Open();

            List<(string Name, string Value, string OriginAttributes)> rows;
            try
            {
                rows = RunQuery(conn, host, nowSeconds, withOriginAttributes: true);
                // Firefox containers store separate rows per container (column
                // originAttributes). Sort so default-container rows ('') come
                // last and win the dict merge — otherwise a container session
                // could shadow the regular login.
                rows = [.. rows.OrderBy(r => r.OriginAttributes == "" ? 1 : 0)];
            }
            catch (SqliteException)
            {
                // Very old schema without originAttributes.
                rows = RunQuery(conn, host, nowSeconds, withOriginAttributes: false);
            }

            var cookies = new Dictionary<string, string>();
            foreach (var row in rows)
                cookies[row.Name] = row.Value;
            return cookies;
        }
        catch (SqliteException exc)
        {
            throw new FirefoxCookieException($"Could not read Firefox cookie database: {exc.Message}", exc);
        }
    }

    private static List<(string, string, string)> RunQuery(
        SqliteConnection conn, string host, long nowSeconds, bool withOriginAttributes)
    {
        var columns = withOriginAttributes ? "name, value, originAttributes" : "name, value";
        using var cmd = conn.CreateCommand();
        cmd.CommandText = $"""
            SELECT {columns}
            FROM   moz_cookies
            WHERE  (host = $host OR host = $dotHost OR host LIKE $subHost)
              AND  expiry > $now
            """;
        cmd.Parameters.AddWithValue("$host", host);
        cmd.Parameters.AddWithValue("$dotHost", $".{host}");
        cmd.Parameters.AddWithValue("$subHost", $"%.{host}");
        cmd.Parameters.AddWithValue("$now", nowSeconds);

        var rows = new List<(string, string, string)>();
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            rows.Add((
                reader.GetString(0),
                reader.GetString(1),
                withOriginAttributes && !reader.IsDBNull(2) ? reader.GetString(2) : ""));
        }
        return rows;
    }

    /// <summary>Return current claude.ai cookies from Firefox.</summary>
    /// <exception cref="FirefoxCookieException">Profile or cookie DB missing/unreadable.</exception>
    public static Dictionary<string, string> GetClaudeCookies(string? profileDir = null)
    {
        var resolved = profileDir ?? FindDefaultProfile();
        var dbPath = Path.Combine(resolved, "cookies.sqlite");
        if (!File.Exists(dbPath))
        {
            throw new FirefoxCookieException(
                $"cookies.sqlite not found in Firefox profile: {resolved}\n" +
                "Make sure Firefox has been launched at least once.");
        }

        var cookies = QueryCookies(dbPath, ClaudeHost);
        if (cookies.Count == 0)
        {
            throw new FirefoxCookieException(
                "No claude.ai cookies found in Firefox. " +
                "Please log in to claude.ai in Firefox first.");
        }
        return cookies;
    }

    /// <summary>Pull the organisation UUID from the lastActiveOrg cookie.
    /// The value is validated as a canonical UUID before being returned so it
    /// cannot smuggle extra path segments into the API URL.</summary>
    public static string ExtractOrgId(IReadOnlyDictionary<string, string> cookies)
    {
        var orgId = (cookies.GetValueOrDefault("lastActiveOrg") ?? "").Trim('"').ToLowerInvariant();
        if (string.IsNullOrEmpty(orgId))
        {
            throw new CookieException(
                "lastActiveOrg cookie not found. " +
                "Visit claude.ai in your browser to set an active organisation.");
        }
        if (!UuidRegex().IsMatch(orgId))
        {
            throw new CookieException(
                "lastActiveOrg cookie is not a valid UUID. " +
                "Open claude.ai in Firefox to refresh the session.");
        }
        return orgId;
    }

    /// <summary>Serialise the cookie dict to an HTTP Cookie header string.</summary>
    public static string BuildCookieHeader(IReadOnlyDictionary<string, string> cookies) =>
        string.Join("; ", cookies.Select(kv => $"{kv.Key}={kv.Value}"));
}
