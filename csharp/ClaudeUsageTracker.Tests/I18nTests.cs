// Translation catalog behaviour: fallbacks, placeholders, unknown languages.

using Xunit;

namespace ClaudeUsageTracker.Tests;

public class I18nTests : IDisposable
{
    public void Dispose() => I18n.Init("en"); // reset for other test classes

    [Fact]
    public void AllCatalogsAreLoaded()
    {
        Assert.Superset(
            new HashSet<string> { "de", "en", "es", "fr", "it", "nl", "pl", "pt", "ru" },
            new HashSet<string>(I18n.AvailableLanguages));
    }

    [Fact]
    public void UnsupportedLanguageFallsBackToEnglish()
    {
        Assert.Equal("en", I18n.Init("xx"));
        Assert.Equal("en", I18n.ActiveLanguage);
    }

    [Fact]
    public void UnknownKeyReturnsKeyItself()
    {
        I18n.Init("en");
        Assert.Equal("no.such.key", I18n.Tr("no.such.key"));
    }

    [Fact]
    public void PlaceholdersAreFilled()
    {
        I18n.Init("en");
        Assert.Equal("3h 42m", I18n.Tr("countdown.hours_minutes", ("hours", 3), ("minutes", 42)));
    }

    [Fact]
    public void GermanCatalogTranslates()
    {
        I18n.Init("de");
        var text = I18n.Tr("tray.menu.quit");
        Assert.NotEqual("Quit", text); // German catalog must differ from English
        Assert.NotEqual("tray.menu.quit", text);
    }

    [Fact]
    public void MissingKeyInActiveCatalogFallsBackToEnglish()
    {
        I18n.Init("de");
        // Every key present in en should resolve to *something* in any language.
        foreach (var key in new[] { "tray.loading", "widget.status.connecting", "update.cancel" })
            Assert.NotEqual(key, I18n.Tr(key));
    }

    [Fact]
    public void AllCatalogsMirrorTheEnglishKeySet()
    {
        // The English catalog is authoritative; a missing key in another
        // catalog silently falls back to English at runtime, so an incomplete
        // catalog only ever shows up to users as untranslated text. Compare
        // the full key sets in both directions to catch that at test time.
        var english = I18n.Catalog("en").Keys.ToHashSet();
        foreach (var lang in I18n.AvailableLanguages)
        {
            var keys = I18n.Catalog(lang).Keys.ToHashSet();
            var missing = english.Except(keys).ToList();
            var extra = keys.Except(english).ToList();
            Assert.True(missing.Count == 0 && extra.Count == 0,
                $"{lang}: missing [{string.Join(", ", missing)}], extra [{string.Join(", ", extra)}]");
        }
    }

    [Fact]
    public void AllCatalogsKeepEnglishPlaceholders()
    {
        // A translation that drops or translates a {placeholder} would render
        // the raw brace text (or lose the value) at runtime — the key-set
        // parity test cannot see that, so pin the placeholder sets too.
        var english = I18n.Catalog("en");
        foreach (var lang in I18n.AvailableLanguages.Where(l => l != "en"))
        {
            foreach (var (key, template) in I18n.Catalog(lang))
            {
                var expected = Placeholders(english[key]);
                var actual = Placeholders(template);
                Assert.True(expected.SetEquals(actual),
                    $"{lang}/{key}: placeholders [{string.Join(", ", actual)}] != english [{string.Join(", ", expected)}]");
            }
        }

        static HashSet<string> Placeholders(string s) =>
            System.Text.RegularExpressions.Regex.Matches(s, @"\{(\w+)\}")
                .Select(m => m.Groups[1].Value).ToHashSet();
    }

    [Fact]
    public void NonEnglishCatalogsAreActuallyTranslated()
    {
        // Guard against copy-pasted English values: a handful of everyday UI
        // strings must differ from English in every other language.
        var english = I18n.Catalog("en");
        foreach (var lang in I18n.AvailableLanguages.Where(l => l != "en"))
        {
            var catalog = I18n.Catalog(lang);
            var identical = new[] { "settings.save", "settings.language", "tray.menu.quit" }
                .Where(k => catalog.TryGetValue(k, out var v) && v == english[k])
                .ToList();
            Assert.True(identical.Count == 0,
                $"{lang}: untranslated values for [{string.Join(", ", identical)}]");
        }
    }
}
