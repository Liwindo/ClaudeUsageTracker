// Cookie extraction against a real temp SQLite database plus the pure helpers.

using System.IO;
using Microsoft.Data.Sqlite;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class FirefoxCookiesTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("cut-cookie-tests-").FullName;

    public void Dispose()
    {
        SqliteConnection.ClearAllPools();
        try
        {
            Directory.Delete(_dir, recursive: true);
        }
        catch (IOException)
        {
        }
    }

    private string CreateCookieDb(params (string Host, string Name, string Value, long Expiry, string Origin)[] rows)
    {
        var path = Path.Combine(_dir, "cookies.sqlite");
        using var conn = new SqliteConnection($"Data Source={path}");
        conn.Open();
        using (var cmd = conn.CreateCommand())
        {
            cmd.CommandText = """
                CREATE TABLE moz_cookies (
                    id INTEGER PRIMARY KEY,
                    name TEXT, value TEXT, host TEXT,
                    expiry INTEGER, originAttributes TEXT NOT NULL DEFAULT ''
                )
                """;
            cmd.ExecuteNonQuery();
        }
        foreach (var row in rows)
        {
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                INSERT INTO moz_cookies (name, value, host, expiry, originAttributes)
                VALUES ($name, $value, $host, $expiry, $origin)
                """;
            cmd.Parameters.AddWithValue("$name", row.Name);
            cmd.Parameters.AddWithValue("$value", row.Value);
            cmd.Parameters.AddWithValue("$host", row.Host);
            cmd.Parameters.AddWithValue("$expiry", row.Expiry);
            cmd.Parameters.AddWithValue("$origin", row.Origin);
            cmd.ExecuteNonQuery();
        }
        return path;
    }

    private static long Future => DateTimeOffset.UtcNow.ToUnixTimeSeconds() + 3600;
    private static long Past => DateTimeOffset.UtcNow.ToUnixTimeSeconds() - 3600;

    [Fact]
    public void MatchesHostAndSubdomainsOnly()
    {
        var db = CreateCookieDb(
            ("claude.ai", "a", "1", Future, ""),
            (".claude.ai", "b", "2", Future, ""),
            (".api.claude.ai", "c", "3", Future, ""),
            ("notclaude.ai", "evil", "x", Future, ""),
            ("evil-claude.ai.example.com", "evil2", "x", Future, ""));
        var cookies = FirefoxCookies.QueryCookies(db, "claude.ai");
        Assert.Equal(new HashSet<string> { "a", "b", "c" }, [.. cookies.Keys]);
    }

    [Fact]
    public void ExpiredCookiesAreSkipped()
    {
        var db = CreateCookieDb(
            ("claude.ai", "fresh", "1", Future, ""),
            ("claude.ai", "stale", "2", Past, ""));
        var cookies = FirefoxCookies.QueryCookies(db, "claude.ai");
        Assert.True(cookies.ContainsKey("fresh"));
        Assert.False(cookies.ContainsKey("stale"));
    }

    [Fact]
    public void DefaultContainerWinsOverContainerCookies()
    {
        // Firefox containers store separate rows; the default container ('')
        // must win the merge so a container session cannot shadow the login.
        var db = CreateCookieDb(
            ("claude.ai", "sessionKey", "container-value", Future, "^userContextId=1"),
            ("claude.ai", "sessionKey", "default-value", Future, ""));
        var cookies = FirefoxCookies.QueryCookies(db, "claude.ai");
        Assert.Equal("default-value", cookies["sessionKey"]);
    }

    [Fact]
    public void ExtractOrgIdValidatesUuid()
    {
        var valid = new Dictionary<string, string>
        {
            ["lastActiveOrg"] = "\"12345678-ABCD-abcd-1234-1234567890ab\"",
        };
        Assert.Equal("12345678-abcd-abcd-1234-1234567890ab", FirefoxCookies.ExtractOrgId(valid));

        Assert.Throws<CookieException>(() =>
            FirefoxCookies.ExtractOrgId(new Dictionary<string, string>()));
        Assert.Throws<CookieException>(() =>
            FirefoxCookies.ExtractOrgId(new Dictionary<string, string>
            {
                ["lastActiveOrg"] = "not-a-uuid/../../evil",
            }));
    }

    [Fact]
    public void BuildCookieHeaderJoinsPairs()
    {
        var header = FirefoxCookies.BuildCookieHeader(new Dictionary<string, string>
        {
            ["a"] = "1",
            ["b"] = "2",
        });
        Assert.Equal("a=1; b=2", header);
    }

    [Fact]
    public void MissingProfilesIniThrowsHelpfulError()
    {
        var exc = Assert.Throws<FirefoxCookieException>(() =>
            FirefoxCookies.FindDefaultProfile(Path.Combine(_dir, "no-such-firefox")));
        Assert.Contains("profiles.ini", exc.Message);
    }

    [Fact]
    public void InstallSectionWinsOverDefaultFlag()
    {
        var firefoxDir = Path.Combine(_dir, "firefox");
        Directory.CreateDirectory(Path.Combine(firefoxDir, "Profiles", "install.default"));
        Directory.CreateDirectory(Path.Combine(firefoxDir, "Profiles", "other.default"));
        File.WriteAllText(Path.Combine(firefoxDir, "profiles.ini"), """
            [Install4F96D1932A9F858E]
            Default=Profiles/install.default

            [Profile0]
            Name=other
            IsRelative=1
            Path=Profiles/other.default
            Default=1
            """);
        var profile = FirefoxCookies.FindDefaultProfile(firefoxDir);
        Assert.EndsWith("install.default", profile);
    }
}
