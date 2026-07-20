// Threshold / reset notification logic (no real toasts — the notify delegate
// is captured in a list).

using Xunit;

namespace ClaudeUsageTracker.Tests;

public class NotificationManagerTests
{
    private readonly List<(string Title, string Message)> _toasts = [];

    public NotificationManagerTests() => I18n.Init("en");

    private NotificationManager Manager(params int[] thresholds) =>
        new(thresholds, (title, message) => _toasts.Add((title, message)));

    private static UsageData Usage(int percent, string key = "five_hour") => new()
    {
        Limits =
        [
            new LimitInfo { Key = key, Label = key, Percent = percent, ResetsAt = DateTimeOffset.UtcNow },
        ],
    };

    [Fact]
    public void EachThresholdFiresOnce()
    {
        var nm = Manager(80, 95);
        nm.Process(Usage(96));
        Assert.Equal(2, _toasts.Count); // 80 and 95 crossed
        nm.Process(Usage(97));
        Assert.Equal(2, _toasts.Count); // no repeat while above
    }

    [Fact]
    public void ResetToastFiresOncePerBucket()
    {
        var nm = Manager(80, 95);
        nm.Process(Usage(96));
        _toasts.Clear();
        nm.Process(Usage(0)); // re-arms BOTH thresholds — but only one toast
        Assert.Single(_toasts);
        Assert.Contains("reset", _toasts[0].Title.ToLowerInvariant());
    }

    [Fact]
    public void SlowDeclineRearmsSilently()
    {
        var nm = Manager(80);
        nm.Process(Usage(85));
        _toasts.Clear();
        foreach (var pct in new[] { 78, 74, 69 }) // rolling window declining slowly
            nm.Process(Usage(pct));
        Assert.Empty(_toasts);
        nm.Process(Usage(82)); // re-crossing fires again after silent re-arm
        Assert.Single(_toasts);
    }

    [Fact]
    public void HysteresisBlocksOscillation()
    {
        var nm = Manager(95);
        nm.Process(Usage(95));
        _toasts.Clear();
        foreach (var pct in new[] { 94, 95, 94, 95 }) // oscillation around threshold
            nm.Process(Usage(pct));
        Assert.Empty(_toasts);
    }

    [Fact]
    public void UpdateThresholdsAppliesLive()
    {
        var nm = Manager(95);
        nm.Process(Usage(90)); // below 95, nothing
        Assert.Empty(_toasts);
        nm.UpdateThresholds([80]);
        nm.Process(Usage(85)); // now above the new 80 threshold
        Assert.Single(_toasts);
    }

    [Fact]
    public void UpdateThresholdsKeepsFiredStateForSurvivingThresholds()
    {
        var nm = Manager(80, 95);
        nm.Process(Usage(96)); // fires 80 and 95
        _toasts.Clear();
        nm.UpdateThresholds([80, 95]); // same set — must not re-fire
        nm.Process(Usage(97));
        Assert.Empty(_toasts);
    }

    [Fact]
    public void LooksLikeResetBoundaries()
    {
        Assert.True(NotificationManager.LooksLikeReset(96, 0));   // sharp drop
        Assert.True(NotificationManager.LooksLikeReset(null, 3)); // near zero, no history
        Assert.True(NotificationManager.LooksLikeReset(40, 10));  // drop of >= 25 points
        Assert.False(NotificationManager.LooksLikeReset(78, 69)); // slow decline
        Assert.False(NotificationManager.LooksLikeReset(null, 69)); // no history, not near zero
    }
}
