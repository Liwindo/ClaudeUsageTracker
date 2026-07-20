// Level parsing/filtering and size-based rotation against a temp log file.

using System.IO;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class LogTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("cut-log-tests-").FullName;
    private string LogPath => Path.Combine(_dir, "app.log");

    public void Dispose()
    {
        // Later writes from other test classes land in the temp file (kept
        // valid on purpose — Log state is static) and are simply discarded
        // with the directory on the next run.
        try
        {
            Directory.Delete(_dir, recursive: true);
        }
        catch (IOException)
        {
        }
    }

    [Theory]
    [InlineData("DEBUG", LogLevel.Debug)]
    [InlineData("info", LogLevel.Info)]
    [InlineData(" Warning ", LogLevel.Warning)]
    [InlineData("ERROR", LogLevel.Error)]
    [InlineData("bogus", LogLevel.Warning)] // config typo → safe default
    public void LevelStringsParseWithSafeFallback(string configured, LogLevel expected)
    {
        Log.Setup(configured, LogPath);
        Assert.Equal(expected, Log.ActiveLevel);
    }

    [Fact]
    public void LinesBelowTheActiveLevelAreNotWritten()
    {
        Log.Setup("INFO", LogPath);
        Log.Debug("test", "invisible");
        Log.Info("test", "visible");
        var text = File.ReadAllText(LogPath);
        Assert.DoesNotContain("invisible", text);
        Assert.Contains("INFO test: visible", text);
    }

    [Fact]
    public void OversizedLogRotatesToBackup()
    {
        // Create the oversized file BEFORE pointing the (global) logger at it —
        // parallel test classes log through the same static Log, and touching
        // the active log file from outside races their appends.
        File.WriteAllText(LogPath, new string('x', 600_000));
        Log.Setup("INFO", LogPath);
        Log.Info("test", "after rotation");
        Assert.True(File.Exists(LogPath + ".1"));
        Assert.Equal(600_000, new FileInfo(LogPath + ".1").Length);
        Assert.Contains("after rotation", File.ReadAllText(LogPath));
    }
}
