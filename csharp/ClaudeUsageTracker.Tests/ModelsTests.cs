// Parsing of the reverse-engineered /usage response.

using System.Text.Json;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class ModelsTests
{
    public ModelsTests() => I18n.Init("en");

    private static JsonElement Json(string json) => JsonDocument.Parse(json).RootElement;

    private static LimitInfo Li(string key = "five_hour", int percent = 50) => new()
    {
        Key = key,
        Label = key,
        Percent = percent,
        ResetsAt = DateTimeOffset.UtcNow,
    };

    [Fact]
    public void UtilizationPlainFloat()
    {
        var info = LimitInfo.FromApi("five_hour", Json("""{"utilization": 13.0, "resets_at": null}"""));
        Assert.Equal(13, info.Percent);
    }

    [Fact]
    public void UtilizationLegacyDictParsedValue()
    {
        var info = LimitInfo.FromApi("five_hour", Json("""{"utilization": {"parsedValue": 42}, "resets_at": null}"""));
        Assert.Equal(42, info.Percent);
    }

    [Fact]
    public void UtilizationLegacyDictSource()
    {
        var info = LimitInfo.FromApi("five_hour", Json("""{"utilization": {"source": "7.5"}, "resets_at": null}"""));
        Assert.Equal(7, info.Percent);
    }

    [Fact]
    public void UtilizationGarbageDefaultsToZero()
    {
        var info = LimitInfo.FromApi("five_hour", Json("""{"utilization": "n/a", "resets_at": null}"""));
        Assert.Equal(0, info.Percent);
    }

    [Fact]
    public void NaiveResetsAtIsTreatedAsUtc()
    {
        var info = LimitInfo.FromApi("five_hour", Json("""{"utilization": 50, "resets_at": "2030-01-01T00:00:00"}"""));
        Assert.Equal(TimeSpan.Zero, info.ResetsAt.Offset - info.ResetsAt.ToUniversalTime().Offset);
        Assert.Equal(new DateTimeOffset(2030, 1, 1, 0, 0, 0, TimeSpan.Zero), info.ResetsAt.ToUniversalTime());
        Assert.True(info.ResetsInSeconds > 0);
    }

    [Fact]
    public void UnknownBucketGetsGenericLabel()
    {
        var info = LimitInfo.FromApi("brand_new_bucket", Json("""{"utilization": 1, "resets_at": null}"""));
        Assert.Contains("brand_new_bucket", info.Label);
    }

    [Fact]
    public void FromApiResponseSkipsExtraUsageAndNulls()
    {
        var data = UsageData.FromApiResponse(Json("""
            {
              "five_hour": {"utilization": 12, "resets_at": "2030-01-01T00:00:00+00:00"},
              "seven_day": null,
              "extra_usage": {"foo": 1},
              "new_bucket": {"utilization": 3, "resets_at": null}
            }
            """));
        var keys = data.Limits.Select(x => x.Key).ToList();
        Assert.Contains("five_hour", keys);
        Assert.Contains("new_bucket", keys);
        Assert.DoesNotContain("extra_usage", keys);
        Assert.DoesNotContain("seven_day", keys);
    }

    [Fact]
    public void KnownBucketsSortBeforeUnknown()
    {
        var data = UsageData.FromApiResponse(Json("""
            {
              "zz_unknown": {"utilization": 1, "resets_at": null},
              "seven_day": {"utilization": 2, "resets_at": null},
              "five_hour": {"utilization": 3, "resets_at": null}
            }
            """));
        Assert.Equal(["five_hour", "seven_day", "zz_unknown"], data.Limits.Select(x => x.Key).ToArray());
    }

    [Fact]
    public void UnknownBucketsSortDeterministically()
    {
        // Unknown buckets share the same sort rank; without an ordinal
        // tie-break their order would depend on response order and sort
        // internals, letting the widget/tooltip order jitter between polls.
        var data = UsageData.FromApiResponse(Json("""
            {
              "zzz_bucket": {"utilization": 1, "resets_at": null},
              "aaa_bucket": {"utilization": 2, "resets_at": null}
            }
            """));
        Assert.Equal(["aaa_bucket", "zzz_bucket"], data.Limits.Select(x => x.Key).ToArray());
    }

    [Fact]
    public void HighestAndSessionPercent()
    {
        var data = new UsageData { Limits = [Li("five_hour", 30), Li("seven_day", 80)] };
        Assert.Equal(80, data.HighestPercent);
        Assert.Equal(30, data.SessionPercent);
        Assert.Equal(0, new UsageData().HighestPercent);
        Assert.Null(new UsageData().SessionPercent);
    }

    [Fact]
    public void ResetCountdownNeverEmpty()
    {
        Assert.False(string.IsNullOrEmpty(Li().ResetCountdown));
    }

    [Fact]
    public void ResetCountdownExpiredIsPlainZero()
    {
        // Callers decide what an expired window means; the countdown itself
        // must stay a duration and never a sentence fragment.
        var info = new LimitInfo
        {
            Key = "five_hour",
            Label = "x",
            Percent = 0,
            ResetsAt = DateTimeOffset.UtcNow.AddHours(-1),
        };
        Assert.Equal("0m", info.ResetCountdown);
    }

    [Fact]
    public void TooltipTextJoinsBuckets()
    {
        var data = new UsageData { Limits = [Li("five_hour", 30), Li("seven_day", 80)] };
        Assert.Equal("five_hour 30% · seven_day 80%", data.TooltipText());
        Assert.Equal("No data", new UsageData().TooltipText());
    }
}
