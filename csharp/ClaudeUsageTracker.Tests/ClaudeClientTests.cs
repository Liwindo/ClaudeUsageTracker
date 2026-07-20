// HTTP response handling and bootstrap-schema parsing (no network involved).

using System.Net;
using System.Net.Http;
using System.Text.Json;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class ClaudeClientTests
{
    private static JsonDocument Check(HttpStatusCode status, string body)
    {
        using var resp = new HttpResponseMessage(status);
        return ClaudeClient.CheckResponse(resp, body, "test/endpoint");
    }

    [Theory]
    [InlineData(HttpStatusCode.Unauthorized)]
    [InlineData(HttpStatusCode.Forbidden)]
    public void AuthFailuresRaiseSessionExpired(HttpStatusCode status)
    {
        var exc = Assert.Throws<SessionExpiredException>(() => Check(status, ""));
        Assert.Contains(((int)status).ToString(), exc.Message);
    }

    [Fact]
    public void TooManyRequestsRaisesRateLimited()
    {
        Assert.Throws<RateLimitedException>(() => Check(HttpStatusCode.TooManyRequests, ""));
    }

    [Fact]
    public void UnexpectedStatusRaisesGenericErrorWithTruncatedBody()
    {
        var body = new string('x', 500);
        var exc = Assert.Throws<ClaudeClientException>(() => Check(HttpStatusCode.InternalServerError, body));
        Assert.Contains("500", exc.Message);
        Assert.DoesNotContain(new string('x', 201), exc.Message);
    }

    [Fact]
    public void NonJsonSuccessBodyRaisesClientError()
    {
        // Cloudflare interstitials return 200 + HTML — must not crash the poll.
        Assert.Throws<ClaudeClientException>(() => Check(HttpStatusCode.OK, "<html>Just a moment</html>"));
    }

    [Fact]
    public void ValidJsonPassesThrough()
    {
        using var doc = Check(HttpStatusCode.OK, "{\"ok\": true}");
        Assert.True(doc.RootElement.GetProperty("ok").GetBoolean());
    }

    // ── bootstrap tier parsing (reverse-engineered schema, pinned here) ──────

    private const string OrgId = "11111111-2222-3333-4444-555555555555";

    private static string Tier(string json)
    {
        using var doc = JsonDocument.Parse(json);
        return ClaudeClient.ParseSubscriptionTier(doc.RootElement, OrgId);
    }

    private static string Bootstrap(string orgJson) =>
        $"{{\"account\": {{\"memberships\": [{{\"organization\": {orgJson}}}]}}}}";

    [Fact]
    public void HighestCapabilityWins()
    {
        var json = Bootstrap($"{{\"uuid\": \"{OrgId}\", \"capabilities\": [\"claude_pro\", \"claude_max\"]}}");
        Assert.Equal("claude_max", Tier(json));
    }

    [Fact]
    public void OnlyTheMatchingOrganizationCounts()
    {
        var other = $"{{\"organization\": {{\"uuid\": \"other\", \"capabilities\": [\"claude_max\"]}}}}";
        var mine = $"{{\"organization\": {{\"uuid\": \"{OrgId}\", \"capabilities\": [\"claude_pro\"]}}}}";
        var json = $"{{\"account\": {{\"memberships\": [{other}, {mine}]}}}}";
        Assert.Equal("claude_pro", Tier(json));
    }

    [Fact]
    public void RateLimitTierIsTheFallback()
    {
        var json = Bootstrap($"{{\"uuid\": \"{OrgId}\", \"capabilities\": [\"chat\"], \"rate_limit_tier\": \"default_claude_ai\"}}");
        Assert.Equal("default_claude_ai", Tier(json));
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("{\"account\": {}}")]
    [InlineData("{\"account\": {\"memberships\": []}}")]
    public void UnrecognisedShapesDegradeToUnknown(string json)
    {
        Assert.Equal("unknown", Tier(json));
    }

    [Fact]
    public void BackoffDoublesAndCapsAtSixteen()
    {
        Assert.Equal(2, Poller.NextBackoffFactor(1));
        Assert.Equal(4, Poller.NextBackoffFactor(2));
        Assert.Equal(16, Poller.NextBackoffFactor(8));
        Assert.Equal(16, Poller.NextBackoffFactor(16));
    }
}
