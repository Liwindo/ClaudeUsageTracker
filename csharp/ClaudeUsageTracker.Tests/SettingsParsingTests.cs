// Threshold text parsing used by the settings dialog.

using Xunit;

namespace ClaudeUsageTracker.Tests;

public class SettingsParsingTests
{
    [Theory]
    [InlineData("80, 95", new[] { 80, 95 })]
    [InlineData("95;80", new[] { 80, 95 })]      // any separator, re-sorted
    [InlineData("80 90 100", new[] { 80, 90, 100 })]
    [InlineData("80, 80, 95", new[] { 80, 95 })] // de-duplicated
    [InlineData("0", new[] { 0 })]
    public void ValidThresholdsParse(string text, int[] expected)
    {
        Assert.True(SettingsWindow.TryParseThresholds(text, out var result));
        Assert.Equal(expected, result);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("80, abc")]
    [InlineData("-5, 80")]
    [InlineData("80, 101")]
    public void InvalidThresholdsRejected(string text)
    {
        Assert.False(SettingsWindow.TryParseThresholds(text, out _));
    }
}
