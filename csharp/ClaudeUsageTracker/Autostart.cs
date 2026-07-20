// Manage the Windows autostart entry (HKCU Run key).
//
// The registry entry is synced to the `autostart` config value on every app
// start, so a moved EXE re-registers itself with the fresh path automatically.
// The value name differs from the Python variant's ("ClaudeUsageTracker") so
// both variants can be autostarted independently.

using Microsoft.Win32;

namespace ClaudeUsageTracker;

public static class Autostart
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ValueName = "ClaudeUsageTrackerCS";

    /// <summary>Make the HKCU Run entry match <paramref name="enabled"/>. Never throws.</summary>
    public static void Sync(bool enabled)
    {
        var exePath = Environment.ProcessPath;
        if (enabled && string.IsNullOrEmpty(exePath))
        {
            Log.Warning("autostart", "Could not determine the executable path; autostart not registered.");
            return;
        }

        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable: true);
            if (key is null)
            {
                Log.Warning("autostart", "Could not open the HKCU Run key.");
                return;
            }
            if (enabled)
            {
                key.SetValue(ValueName, $"\"{exePath}\"", RegistryValueKind.String);
                Log.Info("autostart", $"Autostart entry set: {exePath}");
            }
            else if (key.GetValue(ValueName) is not null)
            {
                key.DeleteValue(ValueName, throwOnMissingValue: false);
                Log.Info("autostart", "Autostart entry removed.");
            }
        }
        catch (Exception exc)
        {
            Log.Warning("autostart", $"Could not update autostart registry entry: {exc.Message}");
        }
    }
}
