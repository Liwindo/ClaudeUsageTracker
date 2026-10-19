// Release notes for the update dialog, taken from the GitHub release bodies.
//
// The source is always the live GitHub releases API — nothing is bundled — so an
// edited release text on GitHub is what users see. The release workflow fills
// each body from that version's CHANGELOG.md section, i.e. a small Markdown
// subset: ### headings, - bullets (one nesting level), **bold**, *emphasis*,
// `code` and [links](…).
//
// A release body is UNTRUSTED under the compromised-GitHub model (REQUIREMENTS.md
// §13, R-net-8). It is therefore only ever turned into plain text plus a bold
// flag: no markup, no clickable links (a link keeps just its text), invisible
// format characters such as a BOM or bidi overrides are dropped, and the amount
// shown is capped. Mirrors python/src/claude_usage_monitor/release_notes.py;
// both suites run the cases in python/tests/fixtures/release_notes_cases.json.

using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ClaudeUsageTracker;

public sealed record NoteSpan(string Text, bool Bold);

/// <summary>Kind is "heading", "bullet" or "text"; Level is the bullet nesting (0 or 1).</summary>
public sealed record NoteBlock(string Kind, IReadOnlyList<NoteSpan> Spans, int Level = 0);

/// <summary>Version without a leading "v", e.g. "2.2.5".</summary>
public sealed record VersionNotes(string Version, IReadOnlyList<NoteBlock> Blocks);

/// <summary>Versions newest first, never empty; Truncated when more changes
/// exist than are shown.</summary>
public sealed record ReleaseNotes(IReadOnlyList<VersionNotes> Versions, bool Truncated);

public static partial class ReleaseNotesParser
{
    // At most this many versions are listed; older ones are summed up by a
    // "see GitHub" line.
    public const int MaxReleases = 10;
    // Hard caps against an oversized (hostile or accidental) body.
    public const int MaxBlocks = 150;        // blocks over all versions
    public const int MaxBlockChars = 1500;   // code points per block, longer text ends in "…"

    private const char Zwj = '‍'; // keeps emoji sequences like 👨‍👩‍👧 together

    [GeneratedRegex(@"^#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")]
    private static partial Regex HeadingRegex();

    [GeneratedRegex(@"^[-*+][ \t]+(.*)$")]
    private static partial Regex BulletRegex();

    [GeneratedRegex(@"^\d{1,9}[.)][ \t]+")]
    private static partial Regex OrderedRegex();

    [GeneratedRegex(@"^(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$")]
    private static partial Regex RuleRegex();

    // The workflow appends "**Full Changelog**: <compare URL>" — a link the
    // dialog cannot open anyway, so the line is dropped.
    [GeneratedRegex(@"^\**full changelog\**\s*:", RegexOptions.IgnoreCase)]
    private static partial Regex FullChangelogRegex();

    [GeneratedRegex(@"\G!?\[([^\[\]]*)\]\([^()\s]*(?:[ \t]+""[^""]*"")?\)")]
    private static partial Regex LinkRegex();

    [GeneratedRegex(@"\G<(https?://[^<>\s]+)>")]
    private static partial Regex AutolinkRegex();

    [GeneratedRegex(@"^v?([0-9]{1,9}(?:\.[0-9]{1,9})*)$")]
    private static partial Regex VersionRegex();

    private const string AsciiPunct = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~";

    // ── Sanitising ────────────────────────────────────────────────────────────

    private static bool IsDropped(UnicodeCategory category) => category is
        UnicodeCategory.Control or UnicodeCategory.Format or UnicodeCategory.Surrogate or
        UnicodeCategory.LineSeparator or UnicodeCategory.ParagraphSeparator;

    /// <summary>Normalise line endings and drop characters that must never
    /// reach the UI: control characters (a tab becomes a space), format
    /// characters such as a BOM or bidi overrides (except the emoji joiner
    /// ZWJ), and lone surrogates.</summary>
    public static string Sanitize(string text)
    {
        text = text.Replace("\r\n", "\n").Replace('\r', '\n');
        var sb = new StringBuilder(text.Length);
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            if (char.IsHighSurrogate(c))
            {
                if (i + 1 < text.Length && char.IsLowSurrogate(text[i + 1]))
                {
                    if (!IsDropped(CharUnicodeInfo.GetUnicodeCategory(text, i)))
                        sb.Append(c).Append(text[i + 1]);
                    i++;
                }
                continue;
            }
            if (char.IsLowSurrogate(c))
                continue;
            if (c is '\n' or Zwj)
                sb.Append(c);
            else if (c == '\t')
                sb.Append(' ');
            else if (!IsDropped(CharUnicodeInfo.GetUnicodeCategory(c)))
                sb.Append(c);
        }
        return sb.ToString();
    }

    // ── Inline Markdown ───────────────────────────────────────────────────────

    /// <summary>One code point plus whether it is literal (escaped, or inside a
    /// code span) and can therefore never act as an emphasis marker.</summary>
    private readonly record struct Atom(string Ch, bool Literal);

    private static void AddLiteral(List<Atom> atoms, string text)
    {
        foreach (var rune in text.EnumerateRunes())
            atoms.Add(new Atom(rune.ToString(), true));
    }

    /// <summary>Split inline text into atoms. Links keep only their text,
    /// autolinks only their URL text.</summary>
    private static List<Atom> Atoms(string text)
    {
        var atoms = new List<Atom>();
        var i = 0;
        var n = text.Length;
        while (i < n)
        {
            var ch = text[i];
            if (ch == '\\' && i + 1 < n && AsciiPunct.Contains(text[i + 1]))
            {
                atoms.Add(new Atom(text[i + 1].ToString(), true));
                i += 2;
                continue;
            }
            if (ch == '`')
            {
                var run = 1;
                while (i + run < n && text[i + run] == '`')
                    run++;
                var close = FindBacktickRun(text, i + run, run);
                if (close < 0)
                {
                    AddLiteral(atoms, text.Substring(i, run));
                    i += run;
                    continue;
                }
                var content = text[(i + run)..close];
                if (content.Length >= 2 && content[0] == ' ' && content[^1] == ' ' &&
                    content.Trim().Length > 0)
                    content = content[1..^1];
                AddLiteral(atoms, content);
                i = close + run;
                continue;
            }
            if (ch is '[' or '!')
            {
                var m = LinkRegex().Match(text, i);
                if (m.Success)
                {
                    atoms.AddRange(Atoms(m.Groups[1].Value));
                    i += m.Length;
                    continue;
                }
            }
            if (ch == '<')
            {
                var m = AutolinkRegex().Match(text, i);
                if (m.Success)
                {
                    AddLiteral(atoms, m.Groups[1].Value);
                    i += m.Length;
                    continue;
                }
            }
            var len = char.IsSurrogatePair(text, i) ? 2 : 1;
            atoms.Add(new Atom(text.Substring(i, len), false));
            i += len;
        }
        return atoms;
    }

    /// <summary>Index of the next backtick run of exactly <paramref name="run"/>
    /// length, or -1.</summary>
    private static int FindBacktickRun(string text, int start, int run)
    {
        var i = start;
        while (i < text.Length)
        {
            if (text[i] != '`')
            {
                i++;
                continue;
            }
            var j = i;
            while (j < text.Length && text[j] == '`')
                j++;
            if (j - i == run)
                return i;
            i = j;
        }
        return -1;
    }

    private static bool IsWord(string? ch) =>
        ch is not null && Rune.GetRuneAt(ch, 0) is var r && (Rune.IsLetter(r) || Rune.IsDigit(r));

    private static bool IsSpace(string? ch) =>
        ch is null || Rune.IsWhiteSpace(Rune.GetRuneAt(ch, 0));

    private readonly record struct Marker(int Start, int Size, string Kind, bool CanOpen, bool CanClose);

    /// <summary><c>**bold**</c>/<c>__bold__</c> → bold spans; <c>*em*</c>/<c>_em_</c>
    /// lose their markers (no italics in the dialog); unmatched markers stay literal.</summary>
    public static IReadOnlyList<NoteSpan> ParseInline(string text)
    {
        var atoms = Atoms(text);
        var n = atoms.Count;
        var markers = new List<Marker>();
        var i = 0;
        while (i < n)
        {
            var (ch, literal) = (atoms[i].Ch, atoms[i].Literal);
            if (literal || ch is not ("*" or "_"))
            {
                i++;
                continue;
            }
            var j = i;
            while (j < n && atoms[j] == new Atom(ch, false))
                j++;
            var length = j - i;
            if (length <= 3)
            {
                var prev = i > 0 ? atoms[i - 1].Ch : null;
                var next = j < n ? atoms[j].Ch : null;
                // A run of three is strong + emphasis ("***x***").
                (int Start, int Size)[] pieces = length switch
                {
                    1 => [(i, 1)],
                    2 => [(i, 2)],
                    _ => [(i, 2), (i + 2, 1)],
                };
                foreach (var (start, size) in pieces)
                {
                    var canOpen = !IsSpace(next);
                    var canClose = !IsSpace(prev);
                    if (size == 1 || ch == "_")
                    {
                        // Emphasis and underscores never apply inside a word
                        // (snake_case, 5*3*2).
                        canOpen = canOpen && !IsWord(prev);
                        canClose = canClose && !IsWord(next);
                    }
                    var kind = (size == 2 ? "strong" : "em") + ch;
                    markers.Add(new Marker(start, size, kind, canOpen, canClose));
                }
            }
            i = j;
        }

        // Pair openers with the next closer of the same kind; the rest stay literal.
        var pending = new Dictionary<string, int>();
        var paired = new Dictionary<int, bool>(); // atom index → toggles bold (else dropped)
        foreach (var m in markers)
        {
            if (pending.TryGetValue(m.Kind, out var opener) && m.CanClose)
            {
                pending.Remove(m.Kind);
                var bold = m.Kind.StartsWith("strong", StringComparison.Ordinal);
                paired[opener] = bold;
                paired[m.Start] = bold;
            }
            else if (m.CanOpen)
            {
                pending[m.Kind] = m.Start;
            }
        }

        var lengths = new Dictionary<int, int>();
        foreach (var m in markers)
            lengths[m.Start] = m.Size;
        var spans = new List<NoteSpan>();
        var buf = new StringBuilder();
        var isBold = false;
        i = 0;
        while (i < n)
        {
            if (paired.TryGetValue(i, out var togglesBold))
            {
                if (togglesBold)
                {
                    if (buf.Length > 0)
                    {
                        spans.Add(new NoteSpan(buf.ToString(), isBold));
                        buf.Clear();
                    }
                    isBold = !isBold;
                }
                i += lengths[i];
                continue;
            }
            buf.Append(atoms[i].Ch);
            i++;
        }
        if (buf.Length > 0)
            spans.Add(new NoteSpan(buf.ToString(), isBold));
        return Merge(spans);
    }

    /// <summary>Join neighbours with the same weight and drop empty spans.</summary>
    private static List<NoteSpan> Merge(IEnumerable<NoteSpan> spans)
    {
        var output = new List<NoteSpan>();
        foreach (var span in spans)
        {
            if (span.Text.Length == 0)
                continue;
            if (output.Count > 0 && output[^1].Bold == span.Bold)
                output[^1] = new NoteSpan(output[^1].Text + span.Text, span.Bold);
            else
                output.Add(span);
        }
        return output;
    }

    private static int CountRunes(string text)
    {
        var count = 0;
        foreach (var _ in text.EnumerateRunes())
            count++;
        return count;
    }

    private static string TakeRunes(string text, int count)
    {
        var sb = new StringBuilder();
        foreach (var rune in text.EnumerateRunes())
        {
            if (count-- <= 0)
                break;
            sb.Append(rune.ToString());
        }
        return sb.ToString();
    }

    /// <summary>Trim the outer whitespace of a block and cap its length.</summary>
    private static List<NoteSpan> Clip(IReadOnlyList<NoteSpan> spans)
    {
        var output = new List<NoteSpan>();
        var budget = MaxBlockChars;
        foreach (var span in spans)
        {
            if (budget <= 0)
                break;
            var text = span.Text;
            var length = CountRunes(text);
            if (length > budget)
            {
                text = TakeRunes(text, budget).TrimEnd() + "…";
                budget = 0;
            }
            else
            {
                budget -= length;
            }
            output.Add(new NoteSpan(text, span.Bold));
        }
        if (output.Count > 0)
        {
            output[0] = output[0] with { Text = output[0].Text.TrimStart() };
            output[^1] = output[^1] with { Text = output[^1].Text.TrimEnd() };
        }
        return Merge(output);
    }

    // ── Blocks ────────────────────────────────────────────────────────────────

    /// <summary>Turn one release body into display blocks.</summary>
    public static IReadOnlyList<NoteBlock> ParseBody(string body)
    {
        var blocks = new List<NoteBlock>();
        string? kind = null;
        var level = 0;
        var parts = new List<string>();

        void Flush()
        {
            if (kind is not null)
            {
                var spans = Clip(ParseInline(string.Join(" ", parts)));
                if (spans.Count > 0)
                    blocks.Add(new NoteBlock(kind, spans, level));
            }
            kind = null;
            parts = [];
        }

        var inQuote = false;
        foreach (var raw in Sanitize(body).Split('\n'))
        {
            var line = raw.TrimEnd();
            var stripped = line.TrimStart(' ');
            var indent = line.Length - stripped.Length;
            // A "> " quote is shown as an ordinary paragraph of its own.
            var quote = stripped.StartsWith('>');
            if (quote)
            {
                stripped = stripped[1..].TrimStart(' ');
                indent = 0;
            }
            if (quote != inQuote)
            {
                Flush();
                inQuote = quote;
            }
            if (stripped.Length == 0)
            {
                Flush();
                continue;
            }
            if (stripped.StartsWith("```", StringComparison.Ordinal) ||
                stripped.StartsWith("~~~", StringComparison.Ordinal))
            {
                Flush(); // fence lines themselves carry nothing to show
                continue;
            }
            if (FullChangelogRegex().IsMatch(stripped) || RuleRegex().IsMatch(stripped))
            {
                Flush();
                continue;
            }
            var m = HeadingRegex().Match(stripped);
            if (m.Success)
            {
                Flush();
                (kind, level, parts) = ("heading", 0, [m.Groups[1].Value]);
                Flush();
                continue;
            }
            m = BulletRegex().Match(stripped);
            if (m.Success)
            {
                Flush();
                (kind, level, parts) = ("bullet", indent >= 2 ? 1 : 0, [m.Groups[1].Value]);
                continue;
            }
            if (OrderedRegex().IsMatch(stripped))
            {
                Flush(); // a numbered item starts its own line, number kept
                (kind, level, parts) = ("text", 0, [stripped]);
                continue;
            }
            if (kind is null)
                (kind, level) = ("text", 0);
            parts.Add(stripped);
        }
        Flush();
        return blocks;
    }

    // ── Choosing the releases ─────────────────────────────────────────────────

    private static int[]? VersionKey(string tag)
    {
        var m = VersionRegex().Match(tag.Trim());
        if (!m.Success)
            return null;
        var parts = m.Groups[1].Value.Split('.').Select(int.Parse).ToList();
        while (parts.Count > 1 && parts[^1] == 0)
            parts.RemoveAt(parts.Count - 1); // "1.2.0" and "1.2" are the same version
        return [.. parts];
    }

    private static int CompareKeys(int[] a, int[] b)
    {
        for (var i = 0; i < Math.Min(a.Length, b.Length); i++)
        {
            if (a[i] != b[i])
                return a[i].CompareTo(b[i]);
        }
        return a.Length.CompareTo(b.Length);
    }

    /// <summary>From a <c>GET /releases</c> payload, the notes of every
    /// published release newer than the running version and not newer than the
    /// latest one, newest first. Null when nothing usable is there (including
    /// invalid JSON), so the dialog can say the notes are unavailable instead of
    /// showing an empty box. Never throws.</summary>
    public static ReleaseNotes? Select(string json, string currentVersion, string latestVersion,
        int maxReleases = MaxReleases)
    {
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(json);
        }
        catch (JsonException)
        {
            return null;
        }
        using (doc)
            return Select(doc.RootElement, currentVersion, latestVersion, maxReleases);
    }

    private static ReleaseNotes? Select(JsonElement payload, string currentVersion, string latestVersion,
        int maxReleases)
    {
        if (payload.ValueKind is not JsonValueKind.Array)
            return null;
        var current = VersionKey(currentVersion);
        var latest = VersionKey(latestVersion);
        if (current is null || latest is null)
            return null;

        var found = new List<(int[] Key, string Version, IReadOnlyList<NoteBlock> Blocks)>();
        foreach (var item in payload.EnumerateArray())
        {
            if (item.ValueKind is not JsonValueKind.Object)
                continue;
            if (item.TryGetProperty("draft", out var draft) && draft.ValueKind is JsonValueKind.True)
                continue;
            if (item.TryGetProperty("prerelease", out var pre) && pre.ValueKind is JsonValueKind.True)
                continue;
            if (!item.TryGetProperty("tag_name", out var tagEl) || tagEl.ValueKind is not JsonValueKind.String ||
                !item.TryGetProperty("body", out var bodyEl) || bodyEl.ValueKind is not JsonValueKind.String)
                continue;
            var tag = tagEl.GetString()!;
            var key = VersionKey(tag);
            if (key is null || found.Any(f => CompareKeys(f.Key, key) == 0) ||
                CompareKeys(current, key) >= 0 || CompareKeys(key, latest) > 0)
                continue;
            var blocks = ParseBody(bodyEl.GetString()!);
            if (blocks.Count > 0)
                found.Add((key, tag.Trim().TrimStart('v', 'V'), blocks));
        }

        found.Sort((a, b) => CompareKeys(b.Key, a.Key));
        var truncated = found.Count > maxReleases;
        var versions = new List<VersionNotes>();
        var budget = MaxBlocks;
        foreach (var (_, version, all) in found.Take(maxReleases))
        {
            if (budget <= 0)
            {
                truncated = true;
                break;
            }
            var blocks = all;
            if (blocks.Count > budget)
            {
                blocks = [.. blocks.Take(budget)];
                truncated = true;
            }
            budget -= blocks.Count;
            versions.Add(new VersionNotes(version, blocks));
        }
        return versions.Count == 0 ? null : new ReleaseNotes(versions, truncated);
    }
}
