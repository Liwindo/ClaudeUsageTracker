// Configuration management.
//
// Config file location: %APPDATA%\claude-usage-tracker-cs\config.toml

using System.IO;
using Tomlyn;
using Tomlyn.Model;

namespace ClaudeUsageTracker;

public sealed class Config
{
    public int PollIntervalSeconds { get; set; } = 30;
    public List<int> NotificationThresholds { get; set; } = [80, 95];
    public string FirefoxProfilePath { get; set; } = "";
    public string LogLevel { get; set; } = "WARNING";
    // Override the User-Agent sent to claude.ai (empty = built-in default).
    public string UserAgent { get; set; } = "";
    // Check GitHub once per app start for a newer release.
    public bool UpdateCheck { get; set; } = true;
    // Release version the user chose to skip via the update dialog.
    public string SkipUpdateVersion { get; set; } = "";
    // Anti-rollback floor: the highest version this install has ever run. The
    // in-app updater refuses anything at or below it, so a later (legitimately
    // signed but older) release can never be pushed onto us across restarts.
    public string UpdateVersionFloor { get; set; } = "";
    // Start with Windows (HKCU Run key), synced on every app start.
    public bool Autostart { get; set; } = false;
    // UI language: "auto" (Windows display language) or a catalog code ("de", …).
    public string Language { get; set; } = "auto";

    private string _path = AppPaths.ConfigFilePath;

    public string? FirefoxProfile =>
        string.IsNullOrWhiteSpace(FirefoxProfilePath) ? null : FirefoxProfilePath.Trim();

    public static Config Load(string? path = null)
    {
        var resolved = path ?? AppPaths.ConfigFilePath;
        if (!File.Exists(resolved))
        {
            var fresh = new Config { _path = resolved };
            fresh.Save(); // write defaults on first run
            return fresh;
        }

        var model = TomlSerializer.Deserialize<TomlTable>(File.ReadAllText(resolved))!;

        var cfg = new Config
        {
            // Floor at 10 s: anything lower would busy-loop against claude.ai.
            PollIntervalSeconds = Math.Max(10, GetInt(model, "poll_interval_seconds", 30)),
            NotificationThresholds = GetIntList(model, "notification_thresholds", [80, 95]),
            FirefoxProfilePath = GetString(model, "firefox_profile_path", ""),
            LogLevel = GetString(model, "log_level", "WARNING"),
            UserAgent = GetString(model, "user_agent", ""),
            UpdateCheck = GetBool(model, "update_check", true),
            SkipUpdateVersion = GetString(model, "skip_update_version", ""),
            UpdateVersionFloor = GetString(model, "update_version_floor", ""),
            Autostart = GetBool(model, "autostart", false),
            Language = GetString(model, "language", "auto"),
            _path = resolved,
        };

        // Migrate config files from older versions: if any option is missing,
        // rewrite the file with the full key set so new options show up with
        // their defaults. Best-effort — a read-only file must not prevent startup.
        var missing = cfg.ToDict().Keys.Where(k => !model.ContainsKey(k)).ToList();
        if (missing.Count > 0)
        {
            try
            {
                cfg.Save();
                Log.Info("config", $"Config migrated: added missing option(s) {string.Join(", ", missing)} with defaults.");
            }
            catch (Exception exc) when (exc is IOException or UnauthorizedAccessException)
            {
                // UnauthorizedAccessException covers the read-only-file case.
                Log.Warning("config", $"Could not migrate config file: {exc.Message}");
            }
        }

        return cfg;
    }

    /// <summary>All persistable options. Save() writes exactly this key set, and
    /// Load() uses it to detect options missing from older config files.</summary>
    private Dictionary<string, object> ToDict() => new()
    {
        ["poll_interval_seconds"] = PollIntervalSeconds,
        ["notification_thresholds"] = NotificationThresholds,
        ["firefox_profile_path"] = FirefoxProfilePath,
        ["log_level"] = LogLevel,
        ["user_agent"] = UserAgent,
        ["update_check"] = UpdateCheck,
        ["skip_update_version"] = SkipUpdateVersion,
        ["update_version_floor"] = UpdateVersionFloor,
        ["autostart"] = Autostart,
        ["language"] = Language,
    };

    public void Save()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
        var table = new TomlTable();
        foreach (var (key, value) in ToDict())
        {
            if (value is List<int> list)
            {
                var array = new TomlArray();
                foreach (var item in list)
                    array.Add((long)item);
                table[key] = array;
            }
            else if (value is int i)
            {
                table[key] = (long)i;
            }
            else
            {
                table[key] = value;
            }
        }
        File.WriteAllText(_path, TomlSerializer.Serialize(table));
    }

    private static string GetString(TomlTable model, string key, string fallback) =>
        model.TryGetValue(key, out var value) && value is not null ? value.ToString() ?? fallback : fallback;

    private static bool GetBool(TomlTable model, string key, bool fallback) =>
        model.TryGetValue(key, out var value) && value is bool b ? b : fallback;

    private static int GetInt(TomlTable model, string key, int fallback)
    {
        if (!model.TryGetValue(key, out var value))
            return fallback;
        return value switch
        {
            long l => (int)l,
            int i => i,
            double d => (int)d,
            string s when int.TryParse(s, out var parsed) => parsed,
            _ => fallback,
        };
    }

    private static List<int> GetIntList(TomlTable model, string key, List<int> fallback)
    {
        if (!model.TryGetValue(key, out var value))
            return [.. fallback];
        // A hand-edited scalar must not slip through: "80" or a bare 80 would
        // otherwise misbehave at poll time — fall back to defaults instead.
        if (value is not TomlArray array)
        {
            Log.Warning("config", $"{key} must be a TOML array like [80, 95], got '{value}' — using defaults.");
            return [.. fallback];
        }
        var result = new List<int>();
        foreach (var item in array)
        {
            int entry;
            switch (item)
            {
                case long l:
                    entry = (int)l;
                    break;
                case double d:
                    entry = (int)d;
                    break;
                case string s when int.TryParse(s, out var parsed):
                    entry = parsed;
                    break;
                default:
                    Log.Warning("config", $"{key} contains a non-integer entry '{item}' — using defaults.");
                    return [.. fallback];
            }
            // Same 0–100 range the settings dialog enforces; a hand-edited
            // negative threshold would otherwise fire on every poll forever.
            if (entry is < 0 or > 100)
            {
                Log.Warning("config", $"{key} entry {entry} is outside 0–100 — using defaults.");
                return [.. fallback];
            }
            result.Add(entry);
        }
        return result;
    }
}
