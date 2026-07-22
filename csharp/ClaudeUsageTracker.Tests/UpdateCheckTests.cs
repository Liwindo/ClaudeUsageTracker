// GitHub update check: version comparison. (The HTTP branches are exercised
// manually — the check swallows every error by design.)

using Xunit;

namespace ClaudeUsageTracker.Tests;

public class UpdateCheckTests
{
    [Fact]
    public void ParseVersion()
    {
        Assert.Equal([1, 2, 0], UpdateCheck.ParseVersion("v1.2.0"));
        Assert.Equal([1, 2], UpdateCheck.ParseVersion("1.2"));
        Assert.Equal([2, 0, 1], UpdateCheck.ParseVersion("  v2.0.1  "));
        Assert.Empty(UpdateCheck.ParseVersion("garbage"));
    }

    [Fact]
    public void IsNewer()
    {
        Assert.True(UpdateCheck.IsNewer("v1.3.0", "1.2.0"));
        Assert.True(UpdateCheck.IsNewer("2.0", "1.9.9"));
        Assert.False(UpdateCheck.IsNewer("v1.2.0", "1.2.0"));
        Assert.False(UpdateCheck.IsNewer("1.2", "1.2.0")); // equal after zero-padding
        Assert.False(UpdateCheck.IsNewer("v1.1.9", "1.2.0"));
        Assert.False(UpdateCheck.IsNewer("not-a-version", "1.2.0"));
    }

    [Fact]
    public void OversizedVersionComponentIsUnparseableNotAnException()
    {
        // CheckForUpdate promises "never throws"; a tag component beyond int
        // range must read as unparseable instead of an OverflowException.
        Assert.Empty(UpdateCheck.ParseVersion("v99999999999999999999"));
        Assert.False(UpdateCheck.IsNewer("v99999999999999999999", "2.0.0"));
    }

    [Fact]
    public void CurrentVersionIsParseable()
    {
        Assert.NotEmpty(UpdateCheck.ParseVersion(UpdateCheck.CurrentVersion));
    }

    // ── Evaluate: the pure, network-free decision the manual check relies on ──

    private const string Body =
        """{"tag_name":"v9.9.9","html_url":"https://github.com/x/releases/tag/v9.9.9","assets":[{"name":"ClaudeUsageTracker-Setup-9.9.9.exe","browser_download_url":"https://github.com/x/y.exe"}]}""";

    [Fact]
    public void EvaluateReportsAvailableWithAssetsForNewerTag()
    {
        var result = UpdateCheck.Evaluate(Body, skipVersion: "", currentVersion: "2.1.1");
        Assert.Equal(UpdateCheckStatus.Available, result.Status);
        Assert.NotNull(result.Info);
        Assert.Equal("9.9.9", result.Info!.LatestVersion);
        Assert.Contains(result.Info.Assets, a => a.Name == "ClaudeUsageTracker-Setup-9.9.9.exe");
    }

    [Fact]
    public void EvaluateReportsUpToDateForEqualOrOlderTag()
    {
        Assert.Equal(UpdateCheckStatus.UpToDate,
            UpdateCheck.Evaluate(Body, "", "9.9.9").Status);
        Assert.Equal(UpdateCheckStatus.UpToDate,
            UpdateCheck.Evaluate(Body, "", "10.0.0").Status);
    }

    [Fact]
    public void EvaluateReportsUpToDateWhenSkipped()
    {
        // Manual checks pass skipVersion="" so a skipped release still surfaces;
        // the once-per-start path passes the skipped version and stays quiet.
        Assert.Equal(UpdateCheckStatus.UpToDate,
            UpdateCheck.Evaluate(Body, skipVersion: "9.9.9", currentVersion: "2.1.1").Status);
        Assert.Equal(UpdateCheckStatus.Available,
            UpdateCheck.Evaluate(Body, skipVersion: "", currentVersion: "2.1.1").Status);
    }

    [Theory]
    [InlineData("not json at all")]
    [InlineData("[1,2,3]")]                 // array, not an object
    [InlineData("{\"message\":\"rate limited\"}")] // no tag_name
    public void EvaluateReportsFailedOrUpToDateForBadBodies(string body)
    {
        // A malformed/array body is a FAILED check (never a false "up to date");
        // a valid object without a usable tag is up to date.
        var status = UpdateCheck.Evaluate(body, "", "2.1.1").Status;
        Assert.NotEqual(UpdateCheckStatus.Available, status);
    }

    [Fact]
    public void EvaluateTreatsMalformedJsonAsFailedNotUpToDate()
    {
        Assert.Equal(UpdateCheckStatus.Failed, UpdateCheck.Evaluate("<html>502</html>", "", "2.1.1").Status);
        Assert.Equal(UpdateCheckStatus.Failed, UpdateCheck.Evaluate("[1,2,3]", "", "2.1.1").Status);
    }
}
