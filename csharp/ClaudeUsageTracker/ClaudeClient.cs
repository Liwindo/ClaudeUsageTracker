// HTTP client for claude.ai internal usage endpoints.
//
// All endpoints here are REVERSE-ENGINEERED and undocumented by Anthropic.
// They may break without notice if Anthropic changes their internal API.

using System.IO;
using System.Net.Http;
using System.Text.Json;

namespace ClaudeUsageTracker;

public class ClaudeClientException : Exception
{
    public ClaudeClientException(string message) : base(message) { }
    public ClaudeClientException(string message, Exception inner) : base(message, inner) { }
}

/// <summary>Raised when Cloudflare or claude.ai rejects the session (401/403).</summary>
public class SessionExpiredException : ClaudeClientException
{
    public SessionExpiredException(string message) : base(message) { }
}

/// <summary>Raised on HTTP 429 — the poller backs off exponentially on this.</summary>
public class RateLimitedException : ClaudeClientException
{
    public RateLimitedException(string message) : base(message) { }
}

public static class ClaudeClient
{
    private const string Base = "https://claude.ai/api";

    // Subscription tier rarely changes; refetch at most once per hour to halve
    // the requests against claude.ai.
    private const int TierCacheSeconds = 3600;
    private static readonly Dictionary<string, (string Tier, long TimestampMs)> TierCache = [];

    // Must match the browser that owns the Firefox session, otherwise Cloudflare
    // may reject the request even with a valid cf_clearance cookie.
    // Users can override this without a rebuild via `user_agent` in config.toml.
    // REVERSE-ENGINEERED: update if you see systematic 403s after browser updates.
    private const string DefaultUserAgent =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) " +
        "Gecko/20100101 Firefox/138.0";

    private static readonly HttpClient Http = CreateHttpClient();

    private static HttpClient CreateHttpClient()
    {
        // WinHttpHandler (native WinHTTP), NOT SocketsHttpHandler: Cloudflare
        // fingerprints the TLS ClientHello and serves .NET's managed TLS stack
        // a "Just a moment" 403 challenge on every claude.ai request, while
        // the WinHTTP fingerprint passes. Verified 2026-07 against both.
        var handler = new WinHttpHandler
        {
            AutomaticRedirection = false,
            CookieUsePolicy = CookieUsePolicy.IgnoreCookies, // Cookie header is sent verbatim
        };
        return new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(15) };
    }

    private static HttpRequestMessage MakeRequest(string url, string cookieHeader, string? userAgent)
    {
        var request = new HttpRequestMessage(HttpMethod.Get, url);
        request.Headers.TryAddWithoutValidation("User-Agent", string.IsNullOrEmpty(userAgent) ? DefaultUserAgent : userAgent);
        request.Headers.TryAddWithoutValidation("Accept", "application/json, text/plain, */*");
        request.Headers.TryAddWithoutValidation("Accept-Language", "en-US,en;q=0.9");
        request.Headers.TryAddWithoutValidation("Referer", "https://claude.ai/");
        request.Headers.TryAddWithoutValidation("DNT", "1");
        request.Headers.TryAddWithoutValidation("Connection", "keep-alive");
        request.Headers.TryAddWithoutValidation("Sec-Fetch-Dest", "empty");
        request.Headers.TryAddWithoutValidation("Sec-Fetch-Mode", "cors");
        request.Headers.TryAddWithoutValidation("Sec-Fetch-Site", "same-origin");
        request.Headers.TryAddWithoutValidation("Cookie", cookieHeader);
        return request;
    }

    /// <summary>Throw a typed error for non-2xx responses, return parsed JSON.</summary>
    internal static JsonDocument CheckResponse(HttpResponseMessage resp, string body, string endpoint)
    {
        var status = (int)resp.StatusCode;
        if (status is 401 or 403)
        {
            throw new SessionExpiredException(
                $"{endpoint} returned {status}. " +
                "Your Firefox session may have expired or Cloudflare blocked the request. " +
                "Open claude.ai in Firefox to refresh the session.");
        }
        if (status == 429)
            throw new RateLimitedException($"{endpoint} returned 429 (rate limited). Backing off.");
        if (!resp.IsSuccessStatusCode)
        {
            throw new ClaudeClientException(
                $"{endpoint} returned unexpected status {status}: {Truncate(body, 200)}");
        }
        try
        {
            return JsonDocument.Parse(body);
        }
        catch (JsonException exc)
        {
            throw new ClaudeClientException(
                $"{endpoint} returned non-JSON response: {Truncate(body, 200)}", exc);
        }
    }

    private static string Truncate(string text, int maxLength) =>
        text.Length <= maxLength ? text : text[..maxLength];

    /// <summary>Flatten an exception chain into one diagnostic line. HttpClient
    /// reports only a generic "An error occurred while sending the request." at the
    /// top and hides the real cause — DNS, TLS/security-channel, connection
    /// refused/reset, timeout — in InnerException (a WinHttpException carrying a
    /// Win32/WINHTTP error code). Surfacing the innermost cause, with that code, is
    /// the difference between a log we can act on and one that says nothing.</summary>
    internal static string DescribeException(Exception exc)
    {
        var parts = new List<string>();
        for (Exception? e = exc; e is not null; e = e.InnerException)
        {
            var msg = e.Message;
            // WinHttpException derives from Win32Exception; the NativeErrorCode is
            // the WINHTTP_* code (12007 = name not resolved, 12175 = security
            // channel/TLS, 12029 = cannot connect, 12002 = timeout, …).
            if (e is System.ComponentModel.Win32Exception win32 && win32.NativeErrorCode != 0)
                msg = $"{msg} (Win32/WinHTTP error {win32.NativeErrorCode})";
            // Wrappers frequently repeat the inner message verbatim — collapse those.
            if (!string.IsNullOrWhiteSpace(msg) && (parts.Count == 0 || parts[^1] != msg))
                parts.Add(msg);
        }
        return parts.Count > 0 ? string.Join(" -> ", parts) : exc.GetType().Name;
    }

    private static JsonDocument GetJson(string url, string cookieHeader, string? userAgent, string endpoint)
    {
        Log.Debug("client", $"GET {url}");
        HttpResponseMessage? resp = null;
        string body;
        try
        {
            using var request = MakeRequest(url, cookieHeader, userAgent);
            // Sync-over-async is fine here: callers always sit on the
            // dedicated poller thread. WinHttpHandler has no synchronous Send.
            resp = Http.SendAsync(request).GetAwaiter().GetResult();
            body = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        }
        catch (Exception exc) when (exc is HttpRequestException or TaskCanceledException or IOException)
        {
            // resp is non-null when the body read failed mid-response.
            resp?.Dispose();
            throw new ClaudeClientException($"Network error fetching {endpoint}: {DescribeException(exc)}", exc);
        }
        using (resp)
        {
            return CheckResponse(resp!, body, endpoint);
        }
    }

    /// <summary>Fetch the user's subscription tier from the bootstrap endpoint.
    /// REVERSE-ENGINEERED: endpoint and response schema are not publicly
    /// documented. Returns a tier string like 'claude_pro', 'claude_max', ….</summary>
    public static string FetchSubscriptionTier(string orgId, string cookieHeader, string? userAgent = null)
    {
        var url = $"{Base}/bootstrap/{orgId}/app_start?statsig_hashing_algorithm=djb2";
        using var doc = GetJson(url, cookieHeader, userAgent, "bootstrap/app_start");
        return ParseSubscriptionTier(doc.RootElement, orgId);
    }

    /// <summary>Extract the tier from a bootstrap response. Separated from the
    /// HTTP call so the reverse-engineered schema stays pinned by tests.</summary>
    internal static string ParseSubscriptionTier(JsonElement root, string orgId)
    {
        if (root.TryGetProperty("account", out var account) &&
            account.ValueKind is JsonValueKind.Object &&
            account.TryGetProperty("memberships", out var memberships) &&
            memberships.ValueKind is JsonValueKind.Array)
        {
            foreach (var membership in memberships.EnumerateArray())
            {
                if (!membership.TryGetProperty("organization", out var org) ||
                    org.ValueKind is not JsonValueKind.Object)
                    continue;
                if (!org.TryGetProperty("uuid", out var uuid) || uuid.GetString() != orgId)
                    continue;

                if (org.TryGetProperty("capabilities", out var capabilities) &&
                    capabilities.ValueKind is JsonValueKind.Array)
                {
                    var caps = capabilities.EnumerateArray()
                        .Where(c => c.ValueKind is JsonValueKind.String)
                        .Select(c => c.GetString())
                        .ToHashSet();
                    foreach (var cap in new[] { "claude_max", "claude_pro", "claude_team", "claude_free" })
                        if (caps.Contains(cap))
                            return cap;
                }
                // Fallback: use rate_limit_tier if present.
                if (org.TryGetProperty("rate_limit_tier", out var tier) &&
                    tier.ValueKind is JsonValueKind.String &&
                    !string.IsNullOrEmpty(tier.GetString()))
                    return tier.GetString()!;
            }
        }

        Log.Warning("client", "Could not determine subscription tier from bootstrap response.");
        return "unknown";
    }

    /// <summary>Fetch current usage limits from the internal /usage endpoint.
    /// REVERSE-ENGINEERED: the response contains buckets like five_hour,
    /// seven_day, seven_day_omelette, … with utilization and resets_at.</summary>
    public static UsageData FetchUsage(
        string orgId, string cookieHeader, string subscriptionTier = "unknown", string? userAgent = null)
    {
        var url = $"{Base}/organizations/{orgId}/usage";
        using var doc = GetJson(url, cookieHeader, userAgent, "organizations/usage");
        return UsageData.FromApiResponse(doc.RootElement, subscriptionTier);
    }

    /// <summary>Return the cached subscription tier or refetch if stale.</summary>
    private static string CachedTier(string orgId, string cookieHeader, string? userAgent)
    {
        var now = Environment.TickCount64;
        (string Tier, long TimestampMs)? cached;
        lock (TierCache)
        {
            cached = TierCache.TryGetValue(orgId, out var entry) ? entry : null;
        }
        if (cached is not null && (now - cached.Value.TimestampMs) < TierCacheSeconds * 1000L)
            return cached.Value.Tier;

        string tier;
        try
        {
            tier = FetchSubscriptionTier(orgId, cookieHeader, userAgent);
        }
        catch (Exception exc)
        {
            // Catch everything: the tier is cosmetic, and a surprise bootstrap
            // schema must degrade to "unknown" instead of aborting the poll.
            Log.Warning("client", $"Could not fetch subscription tier: {exc.Message}");
            // On failure keep any previous value rather than dropping to "unknown".
            return cached?.Tier ?? "unknown";
        }
        lock (TierCache)
        {
            TierCache[orgId] = (tier, now);
        }
        return tier;
    }

    /// <summary>Single entry point: fetches tier + usage and returns a UsageData.</summary>
    public static UsageData FetchAll(string orgId, string cookieHeader, string? userAgent = null)
    {
        var tier = CachedTier(orgId, cookieHeader, userAgent);
        return FetchUsage(orgId, cookieHeader, tier, userAgent);
    }
}
