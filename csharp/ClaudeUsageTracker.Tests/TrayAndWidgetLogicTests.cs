// Pure logic shared by the tray icon and the widget (no real UI is created).

using Xunit;

namespace ClaudeUsageTracker.Tests;

public class TrayAndWidgetLogicTests
{
    public TrayAndWidgetLogicTests() => I18n.Init("en");

    [Fact]
    public void ClipTipRespectsNotifyIconLimit()
    {
        Assert.Equal("short", TrayIcon.ClipTip("short"));
        var longText = new string('x', 300);
        var clipped = TrayIcon.ClipTip(longText);
        Assert.Equal(127, clipped.Length);
        Assert.EndsWith("…", clipped);
    }

    [Fact]
    public void SessionColorBands()
    {
        Assert.Equal("grey", TrayIcon.SessionColor(null));
        Assert.Equal("green", TrayIcon.SessionColor(0));
        Assert.Equal("green", TrayIcon.SessionColor(39));
        Assert.Equal("yellow", TrayIcon.SessionColor(40));
        Assert.Equal("orange", TrayIcon.SessionColor(60));
        Assert.Equal("red", TrayIcon.SessionColor(85));
        Assert.Equal("red", TrayIcon.SessionColor(100));
    }

    private static LimitInfo Li(string key, int percent) => new()
    {
        Key = key,
        Label = key,
        Percent = percent,
        ResetsAt = DateTimeOffset.UtcNow,
    };

    [Fact]
    public void FindWeeklyPrefersWorstWeeklyBucket()
    {
        var data = new UsageData
        {
            Limits = [Li("five_hour", 99), Li("seven_day_opus", 40), Li("seven_day_sonnet", 70)],
        };
        Assert.Equal(70, WidgetWindow.FindWeekly(data));
    }

    [Fact]
    public void FindWeeklyFallsBackToNonSessionBuckets()
    {
        var data = new UsageData { Limits = [Li("five_hour", 99), Li("mystery_bucket", 12)] };
        Assert.Equal(12, WidgetWindow.FindWeekly(data));
        Assert.Null(WidgetWindow.FindWeekly(new UsageData { Limits = [Li("five_hour", 99)] }));
    }

    [Fact]
    public void DisplayPercentPrefersSessionThenWorstBucket()
    {
        var withSession = new UsageData { Limits = [Li("five_hour", 30), Li("seven_day", 80)] };
        Assert.Equal(30, TrayIcon.DisplayPercent(withSession));
        var noSession = new UsageData { Limits = [Li("seven_day", 80), Li("seven_day_opus", 12)] };
        Assert.Equal(80, TrayIcon.DisplayPercent(noSession));
        Assert.Null(TrayIcon.DisplayPercent(new UsageData()));
    }

    [Fact]
    public void PctColorBandsMatchSessionColorBands()
    {
        Assert.Equal("#FF22C55E", WidgetWindow.PctColor(0).ToString());   // green
        Assert.Equal("#FF22C55E", WidgetWindow.PctColor(39).ToString());
        Assert.Equal("#FFEAB308", WidgetWindow.PctColor(40).ToString());  // yellow
        Assert.Equal("#FFF97316", WidgetWindow.PctColor(60).ToString());  // orange
        Assert.Equal("#FFEF4444", WidgetWindow.PctColor(85).ToString());  // red
    }

    [Theory]
    // Real 401/403 texts from ClaudeClient contain "expired" → session hint
    // (rule order is part of the contract).
    [InlineData("organizations/usage returned 401. Your Firefox session may have expired or Cloudflare blocked the request.", "widget.error.session_expired")]
    [InlineData("Blocked by Cloudflare (403 challenge)", "widget.error.cloudflare")]
    [InlineData("No Firefox profile with claude.ai cookies found.", "widget.error.login")]
    [InlineData("organizations/usage returned 429 (rate limited). Backing off.", "widget.error.rate_limited")]
    [InlineData("Network error: no connection available.", "widget.error.network")]
    [InlineData("Something entirely unexpected", "widget.error.generic")]
    public void ErrorTextsClassifyToTheRightFooterHint(string message, string expectedKey)
    {
        Assert.Equal(expectedKey, WidgetWindow.ClassifyErrorKey(message));
    }

    [Fact]
    public void PeakWindowIsNullOnWeekends()
    {
        // 2026-07-18 is a Saturday; 08:00 PT would be inside the window on a weekday.
        var saturday = new DateTimeOffset(2026, 7, 18, 15, 0, 0, TimeSpan.Zero);
        Assert.Null(WidgetWindow.PeakHourWindowLocal(saturday));
    }

    [Fact]
    public void PeakWindowActiveOnWeekdayMorningsPt()
    {
        // 2026-07-17 (Friday) 15:00 UTC = 08:00 PDT → inside 05:00–11:00 PT.
        var fridayPeak = new DateTimeOffset(2026, 7, 17, 15, 0, 0, TimeSpan.Zero);
        var window = WidgetWindow.PeakHourWindowLocal(fridayPeak);
        Assert.NotNull(window);
        Assert.Matches(@"^\d{2}:\d{2}$", window.Value.Start);
        Assert.Matches(@"^\d{2}:\d{2}$", window.Value.End);

        // 2026-07-17 20:00 UTC = 13:00 PDT → outside.
        Assert.Null(WidgetWindow.PeakHourWindowLocal(new DateTimeOffset(2026, 7, 17, 20, 0, 0, TimeSpan.Zero)));
    }
}
