// Data models for claude.ai usage API responses.
//
// All field names mirror the actual /api/organizations/{orgId}/usage response
// (REVERSE-ENGINEERED — may break if Anthropic changes the schema).

using System.Globalization;
using System.Text.Json;

namespace ClaudeUsageTracker;

public sealed class LimitInfo
{
    // Anthropic uses internal codenames for some model-specific weekly buckets.
    // Mapping is inferred from context; "omelette" appears to be Opus-class.
    // Values are translation keys; unmapped buckets get "bucket.unknown".
    // The list order doubles as the display sort order.
    // REVERSE-ENGINEERED: update if Anthropic renames these.
    internal static readonly (string Key, string LabelKey)[] CodenameLabels =
    [
        ("five_hour", "bucket.session"),
        ("seven_day", "bucket.weekly"),
        ("seven_day_opus", "bucket.opus_weekly"),
        ("seven_day_sonnet", "bucket.sonnet_weekly"),
        ("seven_day_omelette", "bucket.opus_weekly"),   // internal codename
        ("seven_day_cowork", "bucket.teams_weekly"),    // internal codename
        ("seven_day_oauth_apps", "bucket.oauth_weekly"),
        ("iguana_necktie", "bucket.unknown"),
        ("tangelo", "bucket.unknown"),
        ("omelette_promotional", "bucket.opus_promo"),
    ];

    public required string Key { get; init; }
    public required string Label { get; init; }
    public required int Percent { get; init; }          // 0–100, already parsed by the API
    public required DateTimeOffset ResetsAt { get; init; }

    public double ResetsInSeconds =>
        Math.Max(0.0, (ResetsAt - DateTimeOffset.UtcNow).TotalSeconds);

    /// <summary>Human-readable countdown string, e.g. "3h 42m".</summary>
    public string ResetCountdown
    {
        get
        {
            var secs = (long)ResetsInSeconds;
            if (secs <= 0)
            {
                // An expired window is a caller-level state (the widget shows
                // "waiting for first message"); the countdown stays a duration.
                return I18n.Tr("countdown.minutes", ("minutes", 0));
            }
            var hours = secs / 3600;
            var minutes = secs % 3600 / 60;
            if (hours > 0)
                return I18n.Tr("countdown.hours_minutes", ("hours", hours), ("minutes", minutes));
            return I18n.Tr("countdown.minutes", ("minutes", minutes));
        }
    }

    /// <summary>Extract integer percent from the utilization field.
    /// As of 2026-05 the API returns a plain float already in 0–100 range;
    /// earlier responses used an object with parsedValue/source — that branch
    /// is kept for backwards compatibility. REVERSE-ENGINEERED.</summary>
    internal static int ParseUtilization(JsonElement raw)
    {
        switch (raw.ValueKind)
        {
            case JsonValueKind.Object:
                if (raw.TryGetProperty("parsedValue", out var parsed) &&
                    parsed.ValueKind is JsonValueKind.Number)
                    return (int)parsed.GetDouble();
                if (raw.TryGetProperty("source", out var source))
                {
                    if (source.ValueKind is JsonValueKind.Number)
                        return (int)source.GetDouble();
                    if (source.ValueKind is JsonValueKind.String &&
                        double.TryParse(source.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var d))
                        return (int)d;
                }
                return 0;
            case JsonValueKind.Number:
                return (int)raw.GetDouble();
            default:
                return 0;
        }
    }

    public static LimitInfo FromApi(string key, JsonElement data)
    {
        var labelKey = CodenameLabels.FirstOrDefault(cl => cl.Key == key).LabelKey ?? "bucket.unknown";
        // `key` is only interpolated by the "bucket.unknown" template; the
        // fixed labels have no {key} placeholder and ignore it.
        var label = I18n.Tr(labelKey, ("key", key));

        var percent = data.TryGetProperty("utilization", out var util) ? ParseUtilization(util) : 0;

        var resetsAt = DateTimeOffset.UtcNow;
        if (data.TryGetProperty("resets_at", out var resets) && resets.ValueKind is JsonValueKind.String)
        {
            // AssumeUniversal: a naive timestamp must be treated as UTC, or
            // every countdown would be off by the local UTC offset.
            if (DateTimeOffset.TryParse(
                    resets.GetString(), CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal, out var parsedAt))
                resetsAt = parsedAt;
        }

        return new LimitInfo { Key = key, Label = label, Percent = percent, ResetsAt = resetsAt };
    }
}

/// <summary>Parsed snapshot of all claude.ai usage limits.</summary>
public sealed class UsageData
{
    public List<LimitInfo> Limits { get; init; } = [];
    public DateTimeOffset FetchedAt { get; init; } = DateTimeOffset.UtcNow;
    public string SubscriptionTier { get; init; } = "unknown";

    /// <summary>Parse the raw /usage JSON into a UsageData instance.
    /// A real usage bucket is an object carrying a non-null <c>utilization</c>.
    /// Unknown *bucket* keys still get a generic "Unknown (…)" label so nothing
    /// silently disappears if Anthropic adds new buckets — but sibling metadata
    /// objects in the same response (<c>extra_usage</c>, <c>spend</c>, …) are
    /// objects too with no usable utilization, and must be skipped so they
    /// never leak into the tooltip as an "Unknown (…)" bucket.
    /// REVERSE-ENGINEERED: schema inferred from real response.</summary>
    public static UsageData FromApiResponse(JsonElement payload, string subscriptionTier = "unknown")
    {
        var limits = new List<LimitInfo>();
        foreach (var property in payload.EnumerateObject())
        {
            if (property.Value.ValueKind is not JsonValueKind.Object)
                continue;
            // Presence of a non-null utilization is what marks a genuine bucket
            // (five_hour, seven_day, future codenames) apart from metadata
            // objects like `spend` (no utilization) or `extra_usage`
            // (utilization: null).
            if (!property.Value.TryGetProperty("utilization", out var util) ||
                util.ValueKind is JsonValueKind.Null)
                continue;
            limits.Add(LimitInfo.FromApi(property.Name, property.Value));
        }

        // Stable display order: session first, then weekly buckets.
        int OrderOf(string key)
        {
            for (var i = 0; i < LimitInfo.CodenameLabels.Length; i++)
                if (LimitInfo.CodenameLabels[i].Key == key)
                    return i;
            return 999;
        }
        // Ordinal tie-break: unknown buckets all rank 999, and without a total
        // order their position would hang on response order + sort internals.
        limits.Sort((a, b) =>
        {
            var byOrder = OrderOf(a.Key).CompareTo(OrderOf(b.Key));
            return byOrder != 0 ? byOrder : string.CompareOrdinal(a.Key, b.Key);
        });

        return new UsageData { Limits = limits, SubscriptionTier = subscriptionTier };
    }

    /// <summary>The worst-case utilization across all active buckets.</summary>
    public int HighestPercent => Limits.Count == 0 ? 0 : Limits.Max(li => li.Percent);

    /// <summary>Percent for the five-hour session bucket, or null if absent.</summary>
    public int? SessionPercent => Limits.FirstOrDefault(li => li.Key == "five_hour")?.Percent;

    /// <summary>Short one-line tooltip for the tray icon.</summary>
    public string TooltipText()
    {
        if (Limits.Count == 0)
            return I18n.Tr("tooltip.no_data");
        return string.Join(" · ", Limits.Select(li => $"{li.Label} {li.Percent}%"));
    }
}
