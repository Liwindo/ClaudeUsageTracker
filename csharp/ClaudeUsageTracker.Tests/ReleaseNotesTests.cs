// Release notes in the update dialog (REQUIREMENTS.md R-life-6 / R-net-8).
//
// The parser cases live in python/tests/fixtures/release_notes_cases.json (linked
// into this project), which the Python suite runs as well, so both variants turn
// a GitHub release body into the same text.

using System.IO;
using System.Text.Json;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class ReleaseNotesTests
{
    private static readonly JsonElement Cases = JsonDocument.Parse(
        File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "release_notes_cases.json"))).RootElement;

    private static IEnumerable<object[]> Section(string name) =>
        Cases.GetProperty(name).EnumerateArray().Select(c => new object[] { c.GetProperty("name").GetString()! });

    private static JsonElement Case(string section, string name) =>
        Cases.GetProperty(section).EnumerateArray().Single(c => c.GetProperty("name").GetString() == name);

    // Spans/blocks as the fixture's JSON shape, so a mismatch prints readably.
    private static string Spans(IEnumerable<NoteSpan> spans) =>
        JsonSerializer.Serialize(spans.Select(s => new object[] { s.Text, s.Bold }));

    private static string Blocks(IEnumerable<NoteBlock> blocks) =>
        "[" + string.Join(",", blocks.Select(b =>
            $"{{\"kind\":{JsonSerializer.Serialize(b.Kind)},\"level\":{b.Level},\"spans\":{Spans(b.Spans)}}}")) + "]";

    private static string Normalize(JsonElement el) =>
        JsonSerializer.Serialize(JsonSerializer.Deserialize<JsonElement>(el.GetRawText()));

    private static string ExpectedBlocks(JsonElement blocks) =>
        "[" + string.Join(",", blocks.EnumerateArray().Select(b =>
            $"{{\"kind\":{JsonSerializer.Serialize(b.GetProperty("kind").GetString())}," +
            $"\"level\":{b.GetProperty("level").GetInt32()},\"spans\":{Normalize(b.GetProperty("spans"))}}}")) + "]";

    public static IEnumerable<object[]> SanitizeCases => Section("sanitize");
    public static IEnumerable<object[]> InlineCases => Section("inline");
    public static IEnumerable<object[]> BlockCases => Section("blocks");
    public static IEnumerable<object[]> SelectCases => Section("select");

    [Theory]
    [MemberData(nameof(SanitizeCases))]
    public void SanitizeMatchesSharedCases(string name)
    {
        var c = Case("sanitize", name);
        Assert.Equal(c.GetProperty("expected").GetString(), ReleaseNotesParser.Sanitize(c.GetProperty("input").GetString()!));
    }

    [Theory]
    [MemberData(nameof(InlineCases))]
    public void InlineMatchesSharedCases(string name)
    {
        var c = Case("inline", name);
        Assert.Equal(Normalize(c.GetProperty("expected")),
            Spans(ReleaseNotesParser.ParseInline(c.GetProperty("input").GetString()!)));
    }

    [Theory]
    [MemberData(nameof(BlockCases))]
    public void BlocksMatchSharedCases(string name)
    {
        var c = Case("blocks", name);
        Assert.Equal(ExpectedBlocks(c.GetProperty("expected")),
            Blocks(ReleaseNotesParser.ParseBody(c.GetProperty("input").GetString()!)));
    }

    [Theory]
    [MemberData(nameof(SelectCases))]
    public void SelectionMatchesSharedCases(string name)
    {
        var c = Case("select", name);
        var max = c.TryGetProperty("max_releases", out var m) ? m.GetInt32() : ReleaseNotesParser.MaxReleases;
        var notes = ReleaseNotesParser.Select(c.GetProperty("releases").GetRawText(),
            c.GetProperty("current").GetString()!, c.GetProperty("latest").GetString()!, max);
        var expected = c.GetProperty("expected_versions");
        if (expected.ValueKind is JsonValueKind.Null)
        {
            Assert.Null(notes);
            return;
        }
        Assert.NotNull(notes);
        Assert.Equal(expected.EnumerateArray().Select(v => v.GetString()), notes.Versions.Select(v => v.Version));
        Assert.Equal(c.GetProperty("truncated").GetBoolean(), notes.Truncated);
        if (c.TryGetProperty("first_block", out var first))
            Assert.Equal(Normalize(first), Spans(notes.Versions[0].Blocks[0].Spans));
    }

    [Fact]
    public void RealReleasesParseExactlyLikeThePythonVariant()
    {
        // The actual GitHub release bodies (BOM in v1.3.0, CRLF and LF bodies,
        // the "Full Changelog" footer, nested bullets, quotes); the expected
        // result is the same one the Python suite asserts.
        var real = Cases.GetProperty("real");
        var notes = ReleaseNotesParser.Select(real.GetProperty("releases").GetRawText(),
            real.GetProperty("current").GetString()!, real.GetProperty("latest").GetString()!, 100);
        Assert.NotNull(notes);
        var expected = real.GetProperty("expected").EnumerateArray().ToList();
        Assert.Equal(expected.Select(v => v.GetProperty("version").GetString()), notes.Versions.Select(v => v.Version));
        for (var i = 0; i < expected.Count; i++)
            Assert.Equal(ExpectedBlocks(expected[i].GetProperty("blocks")), Blocks(notes.Versions[i].Blocks));
    }

    [Fact]
    public void LoneSurrogateIsDropped() =>
        Assert.Equal("ab", ReleaseNotesParser.Sanitize("a\uD83Db"));

    [Fact]
    public void LongBlockIsClipped()
    {
        var blocks = ReleaseNotesParser.ParseBody("- " + new string('a', ReleaseNotesParser.MaxBlockChars + 100));
        Assert.Equal(new string('a', ReleaseNotesParser.MaxBlockChars) + "…", blocks[0].Spans[0].Text);
    }

    [Fact]
    public void LongBlockClipNeverSplitsAnEmoji()
    {
        // Counted in code points like Python, so a cut can't leave half a
        // surrogate pair behind.
        var blocks = ReleaseNotesParser.ParseBody("- " + string.Concat(Enumerable.Repeat("🔒", ReleaseNotesParser.MaxBlockChars + 5)));
        var text = blocks[0].Spans[0].Text;
        Assert.Equal(string.Concat(Enumerable.Repeat("🔒", ReleaseNotesParser.MaxBlockChars)) + "…", text);
    }

    [Fact]
    public void BlockBudgetTruncatesOverAllVersions()
    {
        var body = string.Join("\n", Enumerable.Range(0, 100).Select(i => $"- item {i}"));
        var json = JsonSerializer.Serialize(new[]
        {
            new { tag_name = "v1.2.0", body },
            new { tag_name = "v1.1.0", body },
        });
        var notes = ReleaseNotesParser.Select(json, "1.0.0", "1.2.0");
        Assert.NotNull(notes);
        Assert.True(notes.Truncated);
        Assert.Equal(ReleaseNotesParser.MaxBlocks, notes.Versions.Sum(v => v.Blocks.Count));
    }

    [Fact]
    public void InvalidJsonIsUnavailableNotAnException() =>
        Assert.Null(ReleaseNotesParser.Select("<html>proxy page</html>", "1.0.0", "2.0.0"));

    [Fact]
    public void EvaluateLeavesNotesUnsetUntilFetched()
    {
        // Notes come from a second request; Evaluate alone never invents them.
        var result = UpdateCheck.Evaluate("""{"tag_name":"v9.9.9"}""", "", "1.0.0");
        Assert.Equal(UpdateCheckStatus.Available, result.Status);
        Assert.Null(result.Info!.Notes);
    }
}
