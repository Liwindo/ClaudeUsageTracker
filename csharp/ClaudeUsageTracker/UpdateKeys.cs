// The update-signing public key(s) baked into the shipped app.
//
// This is the trust anchor: the app will only install an update whose manifest
// is signed by the matching OFFLINE private key (UpdateVerifier). Keys live in
// the embedded UpdateKeys.json ({"keys": ["<base64 SubjectPublicKeyInfo>", …]})
// — the SAME file the offline signing tool and the CI integrity guard read, so
// there is exactly one source of truth for what counts as a valid signer.
//
// The list supports rotation: publish a release signed by BOTH the old and a
// new key (add the new public key here first, ship it, then start signing with
// the new key), and only later drop the old key.

using System.Reflection;
using System.Text.Json;

namespace ClaudeUsageTracker;

public static class UpdateKeys
{
    /// <summary>Embedded public keys as SubjectPublicKeyInfo DER blobs. Empty if
    /// none are configured — UpdateVerifier then refuses every update
    /// (fail-closed), so a build can never silently accept unsigned updates.</summary>
    public static IReadOnlyList<byte[]> PublicKeys { get; } = Load();

    private static IReadOnlyList<byte[]> Load()
    {
        try
        {
            var assembly = Assembly.GetExecutingAssembly();
            var name = Array.Find(assembly.GetManifestResourceNames(),
                n => n.EndsWith("UpdateKeys.json", StringComparison.Ordinal));
            if (name is null)
                return [];
            using var stream = assembly.GetManifestResourceStream(name)!;
            using var doc = JsonDocument.Parse(stream);
            if (!doc.RootElement.TryGetProperty("keys", out var keysEl) ||
                keysEl.ValueKind != JsonValueKind.Array)
                return [];
            var keys = new List<byte[]>();
            foreach (var el in keysEl.EnumerateArray())
            {
                var b64 = el.GetString();
                if (string.IsNullOrWhiteSpace(b64))
                    continue;
                try
                {
                    keys.Add(Convert.FromBase64String(b64.Trim()));
                }
                catch (FormatException)
                {
                    // A malformed key entry is ignored; a real one still counts.
                }
            }
            return keys;
        }
        catch (Exception exc)
        {
            Log.Warning("update", $"Could not load update public keys: {exc.Message}");
            return [];
        }
    }
}
