// Runtime translation of user-visible strings.
//
// One JSON catalog per language is embedded from Locales/*.json (exported from
// the Python variant so both trackers share identical wording). Log messages
// and exception texts deliberately stay English — logs must remain readable
// for support, and the widget's error classifier matches on the English
// exception wording.

using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace ClaudeUsageTracker;

public static class I18n
{
    public const string DefaultLanguage = "en";

    private static readonly Dictionary<string, Dictionary<string, string>> Catalogs = LoadCatalogs();
    private static string _activeLanguage = DefaultLanguage;

    // Primary-language part of a Windows LANGID (low 10 bits) → catalog code.
    // Constants from winnt.h (LANG_GERMAN = 0x07, …); stable since Windows 2000.
    private static readonly Dictionary<int, string> LangIdPrimary = new()
    {
        [0x07] = "de",
        [0x09] = "en",
        [0x0A] = "es",
        [0x0C] = "fr",
        [0x10] = "it",
        [0x13] = "nl",
        [0x15] = "pl",
        [0x16] = "pt",
        [0x19] = "ru",
    };

    [DllImport("kernel32.dll")]
    private static extern ushort GetUserDefaultUILanguage();

    private static Dictionary<string, Dictionary<string, string>> LoadCatalogs()
    {
        var catalogs = new Dictionary<string, Dictionary<string, string>>();
        var assembly = Assembly.GetExecutingAssembly();
        foreach (var name in assembly.GetManifestResourceNames())
        {
            // Names look like "ClaudeUsageTracker.Locales.de.json".
            var marker = ".Locales.";
            var idx = name.IndexOf(marker, StringComparison.Ordinal);
            if (idx < 0 || !name.EndsWith(".json", StringComparison.Ordinal))
                continue;
            var code = name[(idx + marker.Length)..^".json".Length];
            using var stream = assembly.GetManifestResourceStream(name)!;
            var strings = JsonSerializer.Deserialize<Dictionary<string, string>>(stream);
            if (strings is not null)
                catalogs[code] = strings;
        }
        return catalogs;
    }

    public static IReadOnlyCollection<string> AvailableLanguages => Catalogs.Keys;

    internal static IReadOnlyDictionary<string, string> Catalog(string language) => Catalogs[language];

    public static string ActiveLanguage => _activeLanguage;

    public static string DetectSystemLanguage()
    {
        try
        {
            var langId = GetUserDefaultUILanguage();
            if (LangIdPrimary.TryGetValue(langId & 0x3FF, out var code))
                return code;
        }
        catch
        {
            // fall through to env-var detection
        }
        foreach (var envVar in new[] { "LC_ALL", "LC_MESSAGES", "LANG" })
        {
            var value = Environment.GetEnvironmentVariable(envVar) ?? "";
            var code = value.Replace('-', '_').Split('_')[0].ToLowerInvariant();
            if (Catalogs.ContainsKey(code))
                return code;
        }
        return DefaultLanguage;
    }

    /// <summary>
    /// Set the active language and return the resolved code. "auto" or ""
    /// triggers system detection; unsupported values fall back to English —
    /// a config typo must never break startup.
    /// </summary>
    public static string Init(string language)
    {
        var code = string.IsNullOrWhiteSpace(language) ? "auto" : language.Trim().ToLowerInvariant();
        if (code is "auto" or "")
            code = DetectSystemLanguage();
        if (!Catalogs.ContainsKey(code))
        {
            Log.Warning("i18n", $"Unsupported language '{language}' — falling back to English.");
            code = DefaultLanguage;
        }
        _activeLanguage = code;
        return code;
    }

    /// <summary>
    /// Translate <paramref name="key"/> into the active language and fill
    /// {placeholder} slots. Never throws: a key missing from the active catalog
    /// falls back to the English catalog; an unknown key returns the key itself.
    /// </summary>
    public static string Tr(string key, params (string Name, object? Value)[] args)
    {
        if (!Catalogs[_activeLanguage].TryGetValue(key, out var template))
        {
            if (!Catalogs[DefaultLanguage].TryGetValue(key, out template))
            {
                Log.Warning("i18n", $"Missing translation key: {key}");
                return key;
            }
        }
        return FillPlaceholders(template, args);
    }

    private static string FillPlaceholders(string template, (string Name, object? Value)[] args)
    {
        var result = template;
        foreach (var (name, value) in args)
            result = result.Replace("{" + name + "}", value?.ToString() ?? "");
        return result;
    }
}
