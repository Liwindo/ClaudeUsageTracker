// The trust gate for in-app updates.
//
// SECURITY MODEL — why this exists and what it guarantees.
// The only defence against a *compromised release* (an attacker who can alter
// what GitHub serves, or who compromises the CI that builds it) is a signature
// made with a key that does NOT live where the artifacts live. This project
// signs the update manifest with an ECDSA P-256 key the developer keeps
// OFFLINE; the matching public key is baked into the shipped app (UpdateKeys).
// A checksum file alone is worthless here: whoever can replace the installer
// can replace its checksum too. The signature cannot be forged without the
// offline private key, so a hostile GitHub or CI cannot mint an update this
// code will accept.
//
// Every method here is a pure decision over in-memory bytes — no network, no
// disk, no app types — so it is exhaustively unit-testable AND can be linked
// verbatim into the offline signing/verification tool, guaranteeing the CI
// integrity guard checks byte-for-byte what the app checks. FAIL CLOSED: any
// doubt returns a rejection; the caller must run nothing unless Ok is true.

using System.Security.Cryptography;

namespace ClaudeUsageTracker;

/// <summary>Outcome of verifying an update. On success, <see cref="Asset"/> is
/// the trusted integrity data the downloaded installer must then match.</summary>
public sealed record UpdateVerification(bool Ok, string? Error, UpdateAsset? Asset)
{
    public static UpdateVerification Fail(string error) => new(false, error, null);
    public static UpdateVerification Pass(UpdateAsset asset) => new(true, null, asset);
}

public static class UpdateVerifier
{
    /// <summary>Largest signature blob accepted (a P-256 IEEE-P1363 signature is
    /// 64 bytes; the cap bounds abuse before the verify runs).</summary>
    public const int MaxSignatureBytes = 256;

    /// <summary>Largest installer we will download/verify. The C# Setup asset is
    /// ~5 MB; the cap bounds a hostile server padding the response.</summary>
    public const long MaxInstallerBytes = 50L * 1024 * 1024;

    /// <summary>Only these hosts may serve an update asset, and only over HTTPS.
    /// GitHub release downloads live on github.com and redirect to
    /// *.githubusercontent.com (objects/release-assets). Anything else is refused
    /// — a manifest cannot point the download at an attacker's host.</summary>
    public static bool IsAllowedAssetUrl(string? url)
    {
        if (string.IsNullOrWhiteSpace(url) ||
            !Uri.TryCreate(url, UriKind.Absolute, out var uri))
            return false;
        if (uri.Scheme != Uri.UriSchemeHttps)
            return false;
        var host = uri.Host;
        return host.Equals("github.com", StringComparison.OrdinalIgnoreCase) ||
               host.EndsWith(".githubusercontent.com", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>Lowercase hex SHA-256 of <paramref name="data"/>.</summary>
    public static string Sha256Hex(ReadOnlySpan<byte> data) =>
        Convert.ToHexStringLower(SHA256.HashData(data));

    /// <summary>True iff the manifest signature verifies under ANY embedded
    /// public key (supports key rotation: a new key can be added before the old
    /// one is retired). Signature is ECDSA P-256 over SHA-256 of the exact
    /// manifest bytes, IEEE-P1363 encoded. Never throws.</summary>
    public static bool SignatureIsValid(ReadOnlySpan<byte> manifestBytes, byte[] signature,
        IEnumerable<byte[]> spkiPublicKeys)
    {
        if (signature.Length == 0 || signature.Length > MaxSignatureBytes)
            return false;
        var data = manifestBytes.ToArray();
        foreach (var spki in spkiPublicKeys)
        {
            try
            {
                using var ecdsa = ECDsa.Create();
                ecdsa.ImportSubjectPublicKeyInfo(spki, out _);
                if (ecdsa.VerifyData(data, signature, HashAlgorithmName.SHA256,
                        DSASignatureFormat.IeeeP1363FixedFieldConcatenation))
                    return true;
            }
            catch (CryptographicException)
            {
                // A malformed key or signature is a rejection, not a crash — try
                // the next key.
            }
        }
        return false;
    }

    /// <summary>Constant-time check that a downloaded file's bytes match the
    /// signed asset's size and digest. Call this on the actual installer bytes
    /// AFTER <see cref="Verify"/> has accepted the manifest.</summary>
    public static bool AssetContentMatches(UpdateAsset asset, ReadOnlySpan<byte> fileBytes)
    {
        if (fileBytes.Length != asset.Size)
            return false;
        var actual = SHA256.HashData(fileBytes);
        byte[] expected;
        try
        {
            expected = Convert.FromHexString(asset.Sha256Hex);
        }
        catch (FormatException)
        {
            return false;
        }
        return CryptographicOperations.FixedTimeEquals(actual, expected);
    }

    /// <summary>The full manifest-level decision, fail-closed. Accepts only when
    /// ALL hold: the signature is valid under an embedded key; the manifest
    /// declares a version strictly newer than <paramref name="currentVersion"/>
    /// (anti-rollback — never "update" to an equal or older, possibly-vulnerable
    /// build); and the manifest carries an entry for <paramref name="assetName"/>.
    /// Returns that entry so the caller can hash-check the download against it.
    /// </summary>
    public static UpdateVerification Verify(byte[] manifestBytes, byte[] signature,
        string assetName, string currentVersion, IReadOnlyList<byte[]> spkiPublicKeys)
    {
        if (manifestBytes.Length == 0 || manifestBytes.Length > UpdateManifest.MaxBytes)
            return UpdateVerification.Fail("manifest missing or too large");
        if (spkiPublicKeys.Count == 0)
            return UpdateVerification.Fail("no update public key embedded");

        // Signature first: never interpret manifest fields we have not
        // authenticated. (Parsing is memory-safe, but decisions come after.)
        if (!SignatureIsValid(manifestBytes, signature, spkiPublicKeys))
            return UpdateVerification.Fail("signature does not verify against any embedded key");

        var manifest = UpdateManifest.TryParse(manifestBytes);
        if (manifest is null)
            return UpdateVerification.Fail("manifest is malformed");

        if (!IsStrictlyNewer(manifest.Version, currentVersion))
            return UpdateVerification.Fail(
                $"manifest version {manifest.Version} is not newer than running {currentVersion} (anti-rollback)");

        if (!manifest.Assets.TryGetValue(assetName, out var asset))
            return UpdateVerification.Fail($"manifest has no entry for asset '{assetName}'");

        return UpdateVerification.Pass(asset);
    }

    /// <summary>The greater of two versions, used to pick the anti-rollback floor
    /// = max(running version, persisted highest-seen). A blank/unparseable side
    /// yields the other; if both are unusable, <paramref name="a"/> is returned
    /// verbatim. Never throws.</summary>
    public static string HigherVersion(string a, string b)
    {
        if (string.IsNullOrWhiteSpace(b))
            return a;
        if (string.IsNullOrWhiteSpace(a))
            return b;
        return IsStrictlyNewer(b, a) ? b : a;
    }

    /// <summary>Dotted numeric compare with zero-padding: "2.2" &gt; "2.1.9",
    /// "2.1" == "2.1.0". Unparseable input on either side → false (fail closed).
    /// Components beyond int range read as unparseable, never throw.</summary>
    internal static bool IsStrictlyNewer(string candidate, string current)
    {
        var c = ParseVersion(candidate);
        var b = ParseVersion(current);
        if (c.Length == 0 || b.Length == 0)
            return false;
        var width = Math.Max(c.Length, b.Length);
        for (var i = 0; i < width; i++)
        {
            var cv = i < c.Length ? c[i] : 0;
            var bv = i < b.Length ? b[i] : 0;
            if (cv != bv)
                return cv > bv;
        }
        return false;
    }

    internal static int[] ParseVersion(string version)
    {
        var trimmed = version.Trim().TrimStart('v', 'V');
        var end = 0;
        while (end < trimmed.Length && (char.IsDigit(trimmed[end]) || trimmed[end] == '.'))
            end++;
        trimmed = trimmed[..end];
        if (trimmed.Length == 0)
            return [];
        var parts = trimmed.Split('.', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0)
            return [];
        var result = new int[parts.Length];
        for (var i = 0; i < parts.Length; i++)
        {
            if (!int.TryParse(parts[i], out result[i]))
                return [];
        }
        return result;
    }
}
