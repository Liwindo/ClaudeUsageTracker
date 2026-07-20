// Central path definitions.
//
// The C# variant deliberately uses its own config directory
// (%APPDATA%\claude-usage-tracker-cs) so it can run side by side with the
// Python variant (%APPDATA%\claude-usage-monitor) without the two fighting
// over config.toml / widget_pos.json / app.log.

using System.IO;

namespace ClaudeUsageTracker;

public static class AppPaths
{
    public static string ConfigDir
    {
        get
        {
            // Respect %APPDATA% — profiles redirected via group policy don't
            // live under the user-profile folder.
            var appdata = Environment.GetEnvironmentVariable("APPDATA");
            var baseDir = !string.IsNullOrEmpty(appdata)
                ? appdata
                : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AppData", "Roaming");
            return Path.Combine(baseDir, "claude-usage-tracker-cs");
        }
    }

    public static string ConfigFilePath => Path.Combine(ConfigDir, "config.toml");
    public static string LogFilePath => Path.Combine(ConfigDir, "app.log");
    public static string WidgetPosFilePath => Path.Combine(ConfigDir, "widget_pos.json");
}
