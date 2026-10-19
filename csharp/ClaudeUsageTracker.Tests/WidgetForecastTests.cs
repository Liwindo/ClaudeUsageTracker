// Session forecast in the widget (REQUIREMENTS.md R-widget-8): after the
// session label, in full or not at all. Mirrors python/tests/test_widget_forecast.py.
// Whether the text fits is real font measurement, so the widget is shown
// (fully transparent, nothing ever saved) on an STA thread.

using System.Runtime.ExceptionServices;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class WidgetForecastTests
{
    // The longest countdown a runs-out forecast can show inside a 5 h window.
    private static readonly Forecast Longest = new(ForecastState.RunsOut, 4 * 3600 + 59 * 60);
    private static readonly Forecast Lasts = new(ForecastState.Lasts);

    private static void OnSta(string language, Action<WidgetWindow> test)
    {
        ExceptionDispatchInfo? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                I18n.Init(language);
                var widget = new WidgetWindow(() => { }, () => { }, () => { })
                {
                    Opacity = 0,
                    ShowActivated = false,
                };
                try
                {
                    widget.Show();
                    widget.Width = 256;
                    widget.UpdateLayout();
                    test(widget);
                }
                finally
                {
                    widget.Close();
                }
            }
            catch (Exception exc)
            {
                failure = ExceptionDispatchInfo.Capture(exc);
            }
            finally
            {
                I18n.Init("en");
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        thread.Join();
        failure?.Throw();
    }

    private static UsageData Data(int percent)
    {
        var now = DateTimeOffset.UtcNow;
        return new UsageData
        {
            Limits =
            [
                new LimitInfo { Key = "five_hour", Label = "s", Percent = percent, ResetsAt = now.AddMinutes(299) },
                new LimitInfo { Key = "seven_day", Label = "w", Percent = 100, ResetsAt = now.AddDays(3) },
            ],
        };
    }

    private static void Apply(WidgetWindow w, int percent, Forecast forecast)
    {
        w.ApplyData(Data(percent), forecast);
        w.UpdateLayout();
    }

    public static IEnumerable<object[]> LanguagesAndForecasts =>
        I18n.AvailableLanguages.Order().SelectMany(lang =>
            new[] { new object[] { lang, "runs_out" }, new object[] { lang, "lasts" } });

    [Theory]
    [MemberData(nameof(LanguagesAndForecasts))]
    public void LongestForecastFitsTheDefaultWidth(string language, string kind) => OnSta(language, w =>
    {
        var forecast = kind == "runs_out" ? Longest : Lasts;
        Apply(w, 99, forecast);
        Assert.False(string.IsNullOrEmpty(w.ShownForecast),
            $"{language}: '{WidgetWindow.ForecastText(forecast).Text}' does not fit");
    });

    [Fact]
    public void RunsOutTextAndColour() => OnSta("en", w =>
    {
        Apply(w, 50, new Forecast(ForecastState.RunsOut, 4800));
        Assert.Equal(" · limit in 1h 20m", w.ShownForecast);
        Assert.Equal(WidgetWindow.WarnColor, w.ShownForecastColor);
    });

    [Fact]
    public void LastsTextAndColour() => OnSta("de", w =>
    {
        Apply(w, 50, Lasts);
        Assert.Equal(" · reicht bis Reset", w.ShownForecast);
        Assert.Equal(WidgetWindow.Dim, w.ShownForecastColor);
    });

    [Fact]
    public void NoForecastShowsNothing() => OnSta("en", w =>
    {
        Apply(w, 50, Forecast.NoForecast);
        Assert.Equal("", w.ShownForecast);
    });

    [Fact]
    public void TooNarrowHidesInsteadOfClippingAndComesBack() => OnSta("en", w =>
    {
        Apply(w, 50, Longest);
        Assert.NotEqual("", w.ShownForecast);
        w.Width = 150;
        w.UpdateLayout();
        Assert.Equal("", w.ShownForecast);
        w.Width = 256;
        w.UpdateLayout();
        Assert.NotEqual("", w.ShownForecast);
    });

    [Fact]
    public void ErrorClearsTheForecast() => OnSta("en", w =>
    {
        Apply(w, 50, Lasts);
        w.ApplyError("Network error fetching usage: timeout");
        w.UpdateLayout();
        Assert.Equal("", w.ShownForecast);
    });
}
