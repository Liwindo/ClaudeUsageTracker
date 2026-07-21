// Regression tests for the bottom-anchored widget geometry.
//
// The widget's height changes at runtime (peak-hour banner, wrapped footer text).
// The bottom edge — the corner the user positions — must stay put while the top
// moves; WPF's SizeToContent=Height does the opposite and made the widget jump on
// every peak/non-peak transition. This class pins that invariant so the bug the
// Python variant already fixed in 1.4.1 cannot silently come back to the C# port.

using Xunit;

namespace ClaudeUsageTracker.Tests;

public class WidgetGeometryTests
{
    // Realistic heights measured from the live widget: collapsed vs. peak banner.
    private const double CollapsedH = 164.0;
    private const double PeakH = 186.7;
    private const double Anchor = 180.0;

    [Fact]
    public void BottomStaysFixedWhenBannerGrowsHeight()
    {
        var topCollapsed = WidgetGeometry.TopForBottom(Anchor, CollapsedH);
        var topPeak = WidgetGeometry.TopForBottom(Anchor, PeakH);

        // Bottom edge is identical in both states…
        Assert.Equal(Anchor, WidgetGeometry.BottomOf(topCollapsed, CollapsedH), 6);
        Assert.Equal(Anchor, WidgetGeometry.BottomOf(topPeak, PeakH), 6);
        // …and the extra height is absorbed by moving the top UP, never the bottom.
        Assert.True(topPeak < topCollapsed);
        Assert.Equal(CollapsedH - PeakH, topPeak - topCollapsed, 6);
    }

    [Fact]
    public void RepeatedPeakCyclesDoNotDriftTheTop()
    {
        var baseTop = WidgetGeometry.TopForBottom(Anchor, CollapsedH);
        var top = baseTop;
        for (var i = 0; i < 50; i++)
        {
            top = WidgetGeometry.TopForBottom(Anchor, PeakH);      // enter peak
            top = WidgetGeometry.TopForBottom(Anchor, CollapsedH); // leave peak
        }
        // After many transitions the resting top is exactly where it started —
        // this is the "creeps downward on each peak/non-peak transition" bug.
        Assert.Equal(baseTop, top, 6);
    }

    [Fact]
    public void SavedAnchorSurvivesRestartWhilePeakBannerShowing()
    {
        // User rests the widget; anchor captured from the collapsed layout.
        var top = WidgetGeometry.TopForBottom(Anchor, CollapsedH);
        var anchorAtRest = WidgetGeometry.BottomOf(top, CollapsedH);

        // Peak arrives → top shifts up, bottom (the persisted value) is unchanged.
        var topDuringPeak = WidgetGeometry.TopForBottom(anchorAtRest, PeakH);
        var persistedDuringPeak = anchorAtRest; // SavePosition writes the anchor…

        // App restarts during NON-peak: top is derived from the saved anchor.
        var restoredTop = WidgetGeometry.TopForBottom(persistedDuringPeak, CollapsedH);
        // Re-saving after restart yields the SAME anchor — no accumulation. The old
        // code persisted the live top, so saving during peak then restoring during
        // non-peak drifted the widget up by the banner height every cycle.
        var resaved = WidgetGeometry.BottomOf(restoredTop, CollapsedH);

        Assert.Equal(anchorAtRest, resaved, 6);
        Assert.Equal(WidgetGeometry.TopForBottom(Anchor, CollapsedH), restoredTop, 6);
        Assert.True(topDuringPeak < restoredTop); // peak really did move the top up
    }

    [Fact]
    public void LegacyTopMigratesToBottomAnchorAtFirstLayout()
    {
        // Old files stored the top ("y"). On first layout the anchor is the bottom
        // edge that top+height implies, so the position is preserved on upgrade.
        const double legacyTop = 300.0;
        var anchor = WidgetGeometry.BottomOf(legacyTop, CollapsedH);
        Assert.Equal(legacyTop, WidgetGeometry.TopForBottom(anchor, CollapsedH), 6);
    }

    [Theory]
    [InlineData(5000, 0, 1080, 1080)]   // bottom far below the desktop → clamped to its edge
    [InlineData(-200, 0, 1080, 40)]     // bottom above the desktop → clamped to a reachable strip
    [InlineData(600, 0, 1080, 600)]     // already on-screen → unchanged
    public void ClampBottomKeepsAnchorReachable(double bottom, double vy, double vh, double expected)
    {
        Assert.Equal(expected, WidgetGeometry.ClampBottom(bottom, vy, vh), 6);
    }
}
