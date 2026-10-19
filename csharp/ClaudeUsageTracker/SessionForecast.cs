// Session forecast: does the 5-hour limit last until it resets? (R-widget-8)
//
// Extrapolates the pace of the last WindowS seconds of polls. Uses only the
// data every poll already fetches — no extra request. Same rules as the Python
// variant's forecast.py; both run python/tests/fixtures/forecast_cases.json.
//
// Utilization arrives in whole percent, so a pace is only trusted once the
// samples span MinSpanS. A moved resets_at means a new 5-hour window: the
// samples of the old one must not feed the new pace.

namespace ClaudeUsageTracker;

internal enum ForecastState
{
    None,     // nothing to show (measuring, at 100 %, window over)
    Lasts,    // the limit is not reached before the reset
    RunsOut,  // the limit is reached in Seconds at this pace
}

internal sealed record Forecast(ForecastState State, double Seconds = 0)
{
    public static readonly Forecast NoForecast = new(ForecastState.None);
}

/// <summary>Keeps the samples of the current 5-hour window. One caller thread.</summary>
internal sealed class SessionForecaster
{
    internal const double WindowS = 1800;    // trailing window the pace is measured over
    internal const double MinSpanS = 600;    // shorter spans give no forecast
    internal const double NewWindowS = 600;  // resets_at moving further = new window

    private readonly List<(double T, int Percent)> _samples = [];
    private double? _resetsAt;

    /// <summary>Times are seconds on any common clock (the app uses Unix time).</summary>
    public Forecast Observe(double t, int percent, double resetsAt)
    {
        var newWindow = _resetsAt is not double prev
            || Math.Abs(resetsAt - prev) > NewWindowS
            || (_samples.Count > 0 && t < _samples[^1].T); // clock went back
        if (newWindow)
            _samples.Clear();
        _resetsAt = resetsAt;
        _samples.Add((t, percent));
        while (_samples[0].T < t - WindowS)
            _samples.RemoveAt(0);
        return Estimate(_samples, resetsAt);
    }

    public Forecast Observe(UsageData data)
    {
        var li = data.Limits.FirstOrDefault(l => l.Key == "five_hour");
        if (li is null)
            return Forecast.NoForecast;
        return Observe(data.FetchedAt.ToUnixTimeMilliseconds() / 1000.0,
            li.Percent, li.ResetsAt.ToUnixTimeMilliseconds() / 1000.0);
    }

    internal static Forecast Estimate(IReadOnlyList<(double T, int Percent)> samples, double resetsAt)
    {
        if (samples.Count == 0)
            return Forecast.NoForecast;
        var (t, p) = samples[^1];
        if (p >= 100 || t >= resetsAt)
            return Forecast.NoForecast;
        var (t0, p0) = samples[0];
        var span = t - t0;
        if (span < MinSpanS)
            return Forecast.NoForecast;
        var rise = p - p0;
        if (rise <= 0)
            return new Forecast(ForecastState.Lasts);
        var seconds = (100 - p) * span / rise;
        if (t + seconds >= resetsAt)
            return new Forecast(ForecastState.Lasts);
        return new Forecast(ForecastState.RunsOut, seconds);
    }
}
