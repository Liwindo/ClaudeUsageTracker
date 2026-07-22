// The signed update manifest.
//
// A release carries a small JSON manifest (update.json) plus a detached
// signature (update.json.sig). The manifest lists, per downloadable asset, the
// exact SHA-256 and byte size. The signature — an offline key the developer
// holds and that never touches CI — is what makes the manifest trustworthy;
// see UpdateVerifier. This file only PARSES the manifest, strictly, without
// trusting any field. It is deliberately dependency-free (System.Text.Json
// only) so it can be shared verbatim with the offline signing tool.

using System.Text.Json;

namespace ClaudeUsageTracker;

/// <summary>One downloadable release asset's integrity data.</summary>
public sealed record UpdateAsset(string Sha256Hex, long Size);

/// <summary>A parsed, not-yet-trusted update manifest. Trust comes only from a
/// valid signature over the exact bytes it was parsed from (UpdateVerifier).</summary>
public sealed record UpdateManifest(int Schema, string Version, IReadOnlyDictionary<string, UpdateAsset> Assets)
{
    public const int CurrentSchema = 1;

    /// <summary>The largest manifest we will parse. A signed manifest is a few
    /// hundred bytes; the cap bounds abuse from a hostile response before any
    /// signature check runs.</summary>
    public const int MaxBytes = 16 * 1024;

    /// <summary>Parse <paramref name="bytes"/> strictly. Returns null (never
    /// throws) on anything malformed — an oversize blob, wrong schema, a missing
    /// or ill-typed field, a non-hex/short digest, a non-positive size. A caller
    /// that gets null must treat it as "no valid update".</summary>
    public static UpdateManifest? TryParse(ReadOnlySpan<byte> bytes)
    {
        if (bytes.Length == 0 || bytes.Length > MaxBytes)
            return null;

        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(bytes.ToArray());
        }
        catch (JsonException)
        {
            return null;
        }

        using (doc)
        {
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                return null;

            if (!root.TryGetProperty("schema", out var schemaEl) ||
                schemaEl.ValueKind != JsonValueKind.Number ||
                !schemaEl.TryGetInt32(out var schema) ||
                schema != CurrentSchema)
                return null;

            if (!root.TryGetProperty("version", out var versionEl) ||
                versionEl.ValueKind != JsonValueKind.String)
                return null;
            var version = versionEl.GetString()!.Trim();
            if (version.Length == 0 || version.Length > 64)
                return null;

            if (!root.TryGetProperty("assets", out var assetsEl) ||
                assetsEl.ValueKind != JsonValueKind.Object)
                return null;

            var assets = new Dictionary<string, UpdateAsset>(StringComparer.Ordinal);
            foreach (var prop in assetsEl.EnumerateObject())
            {
                if (prop.Name.Length == 0 || prop.Name.Length > 200)
                    return null;
                if (prop.Value.ValueKind != JsonValueKind.Object)
                    return null;

                if (!prop.Value.TryGetProperty("sha256", out var shaEl) ||
                    shaEl.ValueKind != JsonValueKind.String)
                    return null;
                var sha = shaEl.GetString()!.Trim().ToLowerInvariant();
                if (!IsSha256Hex(sha))
                    return null;

                if (!prop.Value.TryGetProperty("size", out var sizeEl) ||
                    sizeEl.ValueKind != JsonValueKind.Number ||
                    !sizeEl.TryGetInt64(out var size) ||
                    size <= 0)
                    return null;

                assets[prop.Name] = new UpdateAsset(sha, size);
            }

            if (assets.Count == 0)
                return null;

            return new UpdateManifest(schema, version, assets);
        }
    }

    private static bool IsSha256Hex(string s)
    {
        if (s.Length != 64)
            return false;
        foreach (var c in s)
        {
            var isHex = c is >= '0' and <= '9' or >= 'a' and <= 'f';
            if (!isHex)
                return false;
        }
        return true;
    }
}
