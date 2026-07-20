// Windows-facing pieces that can be exercised safely from the test host:
// autostart registry sync (with save/restore) and the process-level P/Invokes.

using Microsoft.Win32;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class SystemIntegrationTests
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ValueName = "ClaudeUsageTrackerCS";

    [Fact]
    public void AutostartSyncCreatesAndRemovesTheRunEntry()
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable: true);
        Assert.NotNull(key);
        var original = key!.GetValue(ValueName);
        try
        {
            Autostart.Sync(true);
            Assert.Equal($"\"{Environment.ProcessPath}\"", key.GetValue(ValueName) as string);
            Autostart.Sync(false);
            Assert.Null(key.GetValue(ValueName));
        }
        finally
        {
            if (original is not null)
                key.SetValue(ValueName, original);
            else
                key.DeleteValue(ValueName, throwOnMissingValue: false);
        }
    }

    [Fact]
    public void EfficiencyModeAndTrimmerNeverThrow()
    {
        // Both are opportunistic P/Invokes that must degrade to no-ops; their
        // actual effect (EcoQoS flag, working-set drop) is only observable on
        // the real app process and was measured there.
        EfficiencyMode.Enable();
        WorkingSetTrimmer.Trim();
    }
}
