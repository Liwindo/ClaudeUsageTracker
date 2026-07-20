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
}
