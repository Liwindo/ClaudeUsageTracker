// Session forecast (REQUIREMENTS.md R-widget-8). The cases live in
// python/tests/fixtures/forecast_cases.json (linked into this project), which
// the Python suite runs as well, so both variants forecast the same.

using System.IO;
using System.Text.Json;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class SessionForecastTests
{
    private static readonly JsonElement Cases = JsonDocument.Parse(
        File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "forecast_cases.json")))
        .RootElement.GetProperty("cases");

    public static IEnumerable<object[]> CaseNames =>
        Cases.EnumerateArray().Select(c => new object[] { c.GetProperty("name").GetString()! });

    [Theory]
    [MemberData(nameof(CaseNames))]
    public void SharedCase(string name)
    {
        var c = Cases.EnumerateArray().Single(x => x.GetProperty("name").GetString() == name);
        var fc = new SessionForecaster();
        Forecast? result = null;
        foreach (var obs in c.GetProperty("obs").EnumerateArray())
            result = fc.Observe(obs[0].GetDouble(), obs[1].GetInt32(), obs[2].GetDouble());

        var expect = c.GetProperty("expect");
        var state = expect.GetProperty("state").GetString() switch
        {
            "none" => ForecastState.None,
            "lasts" => ForecastState.Lasts,
            "runs_out" => ForecastState.RunsOut,
            var other => throw new InvalidDataException(other),
        };
        Assert.Equal(state, result!.State);
        if (state == ForecastState.RunsOut)
            Assert.Equal(expect.GetProperty("seconds").GetDouble(), result.Seconds, 6);
    }

    private static UsageData Data(DateTimeOffset at, int percent, DateTimeOffset resetsAt, string key = "five_hour") =>
        new()
        {
            FetchedAt = at,
            Limits = [new LimitInfo { Key = key, Label = "x", Percent = percent, ResetsAt = resetsAt }],
        };

    [Fact]
    public void ObserveDataUsesTheSessionBucketAndFetchTime()
    {
        var start = new DateTimeOffset(2026, 10, 19, 12, 0, 0, TimeSpan.Zero);
        var reset = start.AddHours(4);
        var fc = new SessionForecaster();
        fc.Observe(Data(start, 10, reset));
        var result = fc.Observe(Data(start.AddMinutes(10), 20, reset));
        Assert.Equal(ForecastState.RunsOut, result.State);
        Assert.Equal(4800, result.Seconds, 6); // 80 % left at 1 %/min
    }

    [Fact]
    public void WithoutSessionBucketThereIsNoForecast()
    {
        var now = new DateTimeOffset(2026, 10, 19, 12, 0, 0, TimeSpan.Zero);
        var fc = new SessionForecaster();
        Assert.Equal(ForecastState.None, fc.Observe(Data(now, 50, now.AddDays(2), "seven_day")).State);
    }

    [Fact]
    public void IdleSessionLastsAfterMeasuring()
    {
        var start = new DateTimeOffset(2026, 10, 19, 12, 0, 0, TimeSpan.Zero);
        var reset = start.AddHours(2);
        var fc = new SessionForecaster();
        var states = Enumerable.Range(0, 25)
            .Select(i => fc.Observe(Data(start.AddSeconds(30 * i), 40, reset)).State)
            .ToList();
        Assert.All(states.Take(20), s => Assert.Equal(ForecastState.None, s)); // first 10 min
        Assert.All(states.Skip(20), s => Assert.Equal(ForecastState.Lasts, s));
    }
}
