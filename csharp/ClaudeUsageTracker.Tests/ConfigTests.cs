// Config load/save/migration behaviour against real TOML files in a temp dir.

using System.IO;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class ConfigTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("cut-config-tests-").FullName;

    private string PathFor(string name) => System.IO.Path.Combine(_dir, name);

    public void Dispose()
    {
        try
        {
            Directory.Delete(_dir, recursive: true);
        }
        catch (IOException)
        {
        }
    }

    [Fact]
    public void FirstLoadWritesDefaults()
    {
        var path = PathFor("config.toml");
        var cfg = Config.Load(path);
        Assert.True(File.Exists(path));
        Assert.Equal(30, cfg.PollIntervalSeconds);
        Assert.Equal([80, 95], cfg.NotificationThresholds);
        Assert.Equal("auto", cfg.Language);
        var text = File.ReadAllText(path);
        Assert.Contains("poll_interval_seconds", text);
        Assert.Contains("notification_thresholds", text);
    }

    [Fact]
    public void RoundtripPreservesValues()
    {
        var path = PathFor("config.toml");
        var cfg = Config.Load(path);
        cfg.PollIntervalSeconds = 60;
        cfg.NotificationThresholds = [50, 75, 90];
        cfg.Language = "de";
        cfg.SkipUpdateVersion = "9.9.9";
        cfg.UpdateVersionFloor = "2.2.0";
        cfg.Save();

        var reloaded = Config.Load(path);
        Assert.Equal(60, reloaded.PollIntervalSeconds);
        Assert.Equal([50, 75, 90], reloaded.NotificationThresholds);
        Assert.Equal("de", reloaded.Language);
        Assert.Equal("9.9.9", reloaded.SkipUpdateVersion);
        Assert.Equal("2.2.0", reloaded.UpdateVersionFloor);
    }

    [Fact]
    public void PollIntervalIsFlooredAtTen()
    {
        var path = PathFor("config.toml");
        File.WriteAllText(path, "poll_interval_seconds = 0\n");
        Assert.Equal(10, Config.Load(path).PollIntervalSeconds);
    }

    [Fact]
    public void ScalarThresholdsFallBackToDefaults()
    {
        // A hand-edited scalar ("80" or bare 80) must not break startup.
        var path = PathFor("config.toml");
        File.WriteAllText(path, "notification_thresholds = \"80\"\n");
        Assert.Equal([80, 95], Config.Load(path).NotificationThresholds);
    }

    [Fact]
    public void StringThresholdEntriesAreCoerced()
    {
        var path = PathFor("config.toml");
        File.WriteAllText(path, "notification_thresholds = [\"70\", 90]\n");
        Assert.Equal([70, 90], Config.Load(path).NotificationThresholds);
    }

    [Fact]
    public void MigrationOnReadOnlyConfigDoesNotThrow()
    {
        // The migration rewrite is best-effort; a read-only config.toml must
        // load with the parsed values + defaults instead of failing startup.
        var path = PathFor("config.toml");
        File.WriteAllText(path, "poll_interval_seconds = 45\n");
        File.SetAttributes(path, FileAttributes.ReadOnly);
        try
        {
            var cfg = Config.Load(path);
            Assert.Equal(45, cfg.PollIntervalSeconds);
            Assert.Equal("auto", cfg.Language);
        }
        finally
        {
            File.SetAttributes(path, FileAttributes.Normal);
        }
    }

    [Fact]
    public void OutOfRangeThresholdEntriesFallBackToDefaults()
    {
        // The settings dialog enforces 0–100; a hand-edited file must not
        // smuggle values past that (a negative threshold would fire forever).
        var path = PathFor("config.toml");
        File.WriteAllText(path, "notification_thresholds = [80, 950]\n");
        Assert.Equal([80, 95], Config.Load(path).NotificationThresholds);

        var path2 = PathFor("config2.toml");
        File.WriteAllText(path2, "notification_thresholds = [-5, 90]\n");
        Assert.Equal([80, 95], Config.Load(path2).NotificationThresholds);
    }

    [Fact]
    public void SaveIsAtomicAndLeavesNoTempFile()
    {
        // The write goes through a sibling temp + atomic move, so a crash can
        // never leave a half-written config.toml. Prove the temp is swapped
        // away (not left behind) on both first-run and overwrite, and that a
        // stale temp from an earlier crash does not corrupt the next save.
        var path = PathFor("config.toml");
        var tmp = path + ".tmp";

        var cfg = Config.Load(path); // first-run write
        Assert.False(File.Exists(tmp));

        cfg.Language = "fr";
        cfg.Save(); // overwrite an existing file
        Assert.False(File.Exists(tmp));
        Assert.Equal("fr", Config.Load(path).Language);

        File.WriteAllText(tmp, "garbage that is not valid toml");
        cfg.Language = "it";
        cfg.Save();
        Assert.False(File.Exists(tmp));
        Assert.Equal("it", Config.Load(path).Language);
    }

    [Fact]
    public void MigrationAddsMissingKeys()
    {
        var path = PathFor("config.toml");
        File.WriteAllText(path, "poll_interval_seconds = 45\n");
        var cfg = Config.Load(path);
        Assert.Equal(45, cfg.PollIntervalSeconds);
        // The file must now contain the full key set with defaults.
        var text = File.ReadAllText(path);
        Assert.Contains("language", text);
        Assert.Contains("update_check", text);
        Assert.Contains("autostart", text);
        Assert.Contains("poll_interval_seconds = 45", text);
    }
}
