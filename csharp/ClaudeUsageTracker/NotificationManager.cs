// Desktop notification logic.
//
// Fires a system notification when a threshold is crossed (upward) or when a
// limit resets (drops significantly below a previously fired threshold).
// The actual toast delivery is injected so the logic stays testable.

namespace ClaudeUsageTracker;

public sealed class NotificationManager
{
    // Hysteresis band (percent) below the threshold required to re-arm a fired
    // notification. Without this, a value oscillating around the threshold
    // (e.g. 94 ⇄ 95 with threshold=95) would spam notifications every poll.
    private const int Hysteresis = 10;

    private List<int> _thresholds;
    private readonly Action<string, string> _notify;
    // Set of (bucket key, threshold) pairs that have already fired.
    private readonly HashSet<(string Key, int Threshold)> _fired = [];
    // Last seen percent per bucket — used to tell a real reset (sharp drop
    // between two polls) from a rolling window slowly declining.
    private readonly Dictionary<string, int> _lastPercent = [];

    public NotificationManager(IEnumerable<int> thresholds, Action<string, string> notify)
    {
        _thresholds = [.. thresholds.OrderBy(t => t)];
        _notify = notify;
    }

    /// <summary>Swap the thresholds at runtime (settings dialog). Already-fired
    /// state for thresholds that still exist is preserved so a save doesn't
    /// re-toast a limit that is currently over the line.</summary>
    public void UpdateThresholds(IEnumerable<int> thresholds)
    {
        var next = thresholds.OrderBy(t => t).ToList();
        // Drop fired markers for thresholds that no longer exist.
        _fired.RemoveWhere(pair => !next.Contains(pair.Threshold));
        _thresholds = next;
    }

    /// <summary>Check data against thresholds and fire notifications as needed.</summary>
    public void Process(UsageData data)
    {
        foreach (var li in data.Limits)
        {
            int? prev = _lastPercent.TryGetValue(li.Key, out var p) ? p : null;
            _lastPercent[li.Key] = li.Percent;
            var rearmed = false;
            foreach (var threshold in _thresholds)
            {
                var key = (li.Key, threshold);
                if (li.Percent >= threshold)
                {
                    if (_fired.Add(key))
                        FireThreshold(li.Label, li.Percent, threshold);
                }
                else if (_fired.Contains(key) && li.Percent < threshold - Hysteresis)
                {
                    // Meaningful drop below the hysteresis band: re-arm.
                    _fired.Remove(key);
                    rearmed = true;
                }
            }
            // Announce at most once per bucket — a reset to 0% re-arms ALL
            // fired thresholds in the same pass and would otherwise toast once
            // per threshold. A slow decline re-arms silently.
            if (rearmed && LooksLikeReset(prev, li.Percent))
                FireReset(li.Label, li.Percent);
        }
    }

    /// <summary>True if the drop looks like an actual limit reset. A real reset
    /// collapses to ~0 within one poll interval; a rolling window declines a
    /// few points per poll at most.</summary>
    internal static bool LooksLikeReset(int? prev, int current)
    {
        if (current <= 5)
            return true;
        return prev is not null && prev - current >= 25;
    }

    private void FireThreshold(string label, int percent, int threshold)
    {
        Log.Info("notify", $"Notification: {label} reached {percent}% (threshold {threshold}%)");
        SafeNotify(
            I18n.Tr("notify.threshold.title", ("label", label), ("percent", percent)),
            I18n.Tr("notify.threshold.body", ("label", label), ("threshold", threshold)));
    }

    private void FireReset(string label, int percent)
    {
        Log.Info("notify", $"Notification: {label} reset (now {percent}%)");
        SafeNotify(
            I18n.Tr("notify.reset.title", ("label", label)),
            I18n.Tr("notify.reset.body", ("label", label), ("percent", percent)));
    }

    private void SafeNotify(string title, string message)
    {
        try
        {
            _notify(title, message);
        }
        catch (Exception exc)
        {
            // Notifications failing must never crash the app.
            Log.Warning("notify", $"Desktop notification failed: {exc.Message}");
        }
    }
}
