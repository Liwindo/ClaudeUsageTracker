// Update trust gate (UpdateVerifier) — the security-critical decision code.
//
// Every test signs with a throwaway ECDSA P-256 key generated in-process, so
// no key material is committed. The suite pins the fail-closed behaviour that
// stops a compromised GitHub/CI from shipping an infected version: a tampered
// manifest, a wrong signer, a mismatched download, a rollback, a foreign host,
// or a missing embedded key must all be REFUSED. Requirement ids: see
// REQUIREMENTS.md R-update-*.

using System.Security.Cryptography;
using System.Text;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class UpdateVerifierTests
{
    private const string Asset = "ClaudeUsageTracker-Setup-9.9.9.exe";

    private static ECDsa NewKey() => ECDsa.Create(ECCurve.NamedCurves.nistP256);

    private static byte[] Spki(ECDsa key) => key.ExportSubjectPublicKeyInfo();

    private static byte[] Sign(ECDsa key, byte[] data) =>
        key.SignData(data, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation);

    private static byte[] Manifest(string version, string assetName, string sha256Hex, long size) =>
        Encoding.UTF8.GetBytes(
            $"{{\"schema\":1,\"version\":\"{version}\",\"assets\":{{\"{assetName}\":{{\"sha256\":\"{sha256Hex}\",\"size\":{size}}}}}}}");

    // R-update-1: a genuinely signed, newer manifest with a matching asset entry
    // is accepted and yields the trusted digest.
    [Fact]
    public void ValidSignedNewerManifestIsAccepted()
    {
        using var key = NewKey();
        var installer = new byte[12345];
        RandomNumberGenerator.Fill(installer);
        var bytes = Manifest("9.9.9", Asset, UpdateVerifier.Sha256Hex(installer), installer.Length);

        var result = UpdateVerifier.Verify(bytes, Sign(key, bytes), Asset, "2.1.1", [Spki(key)]);

        Assert.True(result.Ok, result.Error);
        Assert.NotNull(result.Asset);
        Assert.True(UpdateVerifier.AssetContentMatches(result.Asset!, installer));
    }

    // R-update-2: any change to the manifest bytes after signing invalidates it.
    [Fact]
    public void TamperedManifestIsRejected()
    {
        using var key = NewKey();
        var bytes = Manifest("9.9.9", Asset, new string('a', 64), 100);
        var sig = Sign(key, bytes);

        var tampered = Manifest("9.9.8", Asset, new string('a', 64), 100); // downgraded version
        var result = UpdateVerifier.Verify(tampered, sig, Asset, "2.1.1", [Spki(key)]);

        Assert.False(result.Ok);
        Assert.Contains("signature", result.Error);
    }

    // R-update-2: a signature from a key the app does not embed is refused.
    [Fact]
    public void SignatureFromUntrustedKeyIsRejected()
    {
        using var signer = NewKey();
        using var trusted = NewKey();
        var bytes = Manifest("9.9.9", Asset, new string('b', 64), 100);

        var result = UpdateVerifier.Verify(bytes, Sign(signer, bytes), Asset, "2.1.1", [Spki(trusted)]);

        Assert.False(result.Ok);
    }

    // R-update-1 (rotation): verification passes if ANY embedded key matches.
    [Fact]
    public void SignatureVerifiesUnderAnyEmbeddedKey()
    {
        using var oldKey = NewKey();
        using var newKey = NewKey();
        var bytes = Manifest("9.9.9", Asset, new string('c', 64), 100);
        var sig = Sign(newKey, bytes);

        Assert.True(UpdateVerifier.SignatureIsValid(bytes, sig, [Spki(oldKey), Spki(newKey)]));
    }

    // R-update-3: a downloaded file that does not match the signed digest/size
    // is refused even when the manifest itself is valid.
    [Fact]
    public void DownloadedBytesMustMatchSignedDigest()
    {
        var real = new byte[5000];
        RandomNumberGenerator.Fill(real);
        var asset = new UpdateAsset(UpdateVerifier.Sha256Hex(real), real.Length);

        Assert.True(UpdateVerifier.AssetContentMatches(asset, real));

        var evil = (byte[])real.Clone();
        evil[0] ^= 0xFF;
        Assert.False(UpdateVerifier.AssetContentMatches(asset, evil));           // same size, different bytes
        Assert.False(UpdateVerifier.AssetContentMatches(asset, real[..4999]));   // wrong size
    }

    // R-update-4: never "update" to an equal or older version (anti-rollback),
    // even if that version is validly signed.
    [Theory]
    [InlineData("9.9.9", "9.9.9")] // equal
    [InlineData("2.1.0", "2.1.1")] // older
    [InlineData("2.1", "2.1.0")]   // equal after zero-padding
    public void EqualOrOlderVersionIsRejected(string manifestVersion, string current)
    {
        using var key = NewKey();
        var bytes = Manifest(manifestVersion, Asset, new string('d', 64), 100);

        var result = UpdateVerifier.Verify(bytes, Sign(key, bytes), Asset, current, [Spki(key)]);

        Assert.False(result.Ok);
        Assert.Contains("anti-rollback", result.Error);
    }

    // R-update-4 (floor): HigherVersion picks the greater of running vs. persisted
    // highest-seen, tolerating blank/unparseable input, so the floor only rises.
    [Theory]
    [InlineData("2.2.0", "", "2.2.0")]        // no persisted floor yet → running
    [InlineData("2.0.0", "2.2.0", "2.2.0")]   // persisted floor higher → floor wins
    [InlineData("2.3.0", "2.2.0", "2.3.0")]   // running higher → running wins
    [InlineData("2.2.0", "2.2.0", "2.2.0")]   // equal → same value
    [InlineData("2.2.0", "garbage", "2.2.0")] // unparseable floor → running
    [InlineData("", "2.2.0", "2.2.0")]        // blank running → floor
    public void HigherVersionPicksTheGreater(string running, string floor, string expected)
    {
        Assert.Equal(expected, UpdateVerifier.HigherVersion(running, floor));
    }

    // R-update-4 (floor): the concrete attack the persisted floor closes — a
    // GENUINELY signed but OLDER release (newer than the running build, so it
    // would otherwise install) is refused once the app has ever run something
    // higher. The floor is passed to Verify as the effective current version.
    [Fact]
    public void SignedButOlderThanFloorIsRejected()
    {
        using var key = NewKey();
        // Attacker replays a real, signed 2.1.0 while we run 2.0.0 but have a
        // persisted floor of 2.2.0 (we ran 2.2.0 before). max(2.0.0, 2.2.0)=2.2.0.
        var floor = UpdateVerifier.HigherVersion("2.0.0", "2.2.0");
        var bytes = Manifest("2.1.0", Asset, new string('a', 64), 100);

        var result = UpdateVerifier.Verify(bytes, Sign(key, bytes), Asset, floor, [Spki(key)]);

        Assert.False(result.Ok);
        Assert.Contains("anti-rollback", result.Error);
    }

    // R-update-5: only https github.com / *.githubusercontent.com may serve an asset.
    [Theory]
    [InlineData("https://github.com/Liwindo/ClaudeUsageTracker/releases/download/v9.9.9/x.exe", true)]
    [InlineData("https://objects.githubusercontent.com/abc/x.exe", true)]
    [InlineData("https://release-assets.githubusercontent.com/abc/x.exe", true)]
    [InlineData("http://github.com/x.exe", false)]              // not https
    [InlineData("https://evil.com/x.exe", false)]               // foreign host
    [InlineData("https://github.com.evil.com/x.exe", false)]    // suffix trick
    [InlineData("https://notgithubusercontent.com/x.exe", false)]
    [InlineData("", false)]
    [InlineData("not a url", false)]
    public void OnlyGithubHttpsAssetUrlsAreAllowed(string url, bool allowed)
    {
        Assert.Equal(allowed, UpdateVerifier.IsAllowedAssetUrl(url));
    }

    // R-update-6: fail closed when no public key is embedded — a build can never
    // silently accept an unsigned update.
    [Fact]
    public void NoEmbeddedKeyFailsClosed()
    {
        var bytes = Manifest("9.9.9", Asset, new string('e', 64), 100);
        var result = UpdateVerifier.Verify(bytes, new byte[64], Asset, "2.1.1", []);

        Assert.False(result.Ok);
        Assert.Contains("no update public key", result.Error);
    }

    // R-update-2: garbage/empty/oversize signatures are rejected, never crash.
    [Fact]
    public void MalformedSignaturesAreRejectedNotThrown()
    {
        using var key = NewKey();
        var bytes = Manifest("9.9.9", Asset, new string('f', 64), 100);
        var keys = new[] { Spki(key) };

        Assert.False(UpdateVerifier.SignatureIsValid(bytes, [], keys));                    // empty
        Assert.False(UpdateVerifier.SignatureIsValid(bytes, new byte[1000], keys));        // oversize
        Assert.False(UpdateVerifier.SignatureIsValid(bytes, new byte[64], keys));          // wrong bytes
    }

    // R-update-2: a valid signature over bytes that are not a well-formed manifest
    // is still refused (signature authenticates, parsing then rejects).
    [Fact]
    public void ValidlySignedButMalformedManifestIsRejected()
    {
        using var key = NewKey();
        var junk = Encoding.UTF8.GetBytes("this is not json");
        var result = UpdateVerifier.Verify(junk, Sign(key, junk), Asset, "2.1.1", [Spki(key)]);

        Assert.False(result.Ok);
        Assert.Contains("malformed", result.Error);
    }

    // R-update-1: the manifest must actually carry the asset we intend to install.
    [Fact]
    public void ManifestWithoutTheRequestedAssetIsRejected()
    {
        using var key = NewKey();
        var bytes = Manifest("9.9.9", "some-other-file.exe", new string('a', 64), 100);
        var result = UpdateVerifier.Verify(bytes, Sign(key, bytes), Asset, "2.1.1", [Spki(key)]);

        Assert.False(result.Ok);
        Assert.Contains("no entry for asset", result.Error);
    }

    // R-update-6: whatever keys ARE embedded in the shipped app must be valid
    // SPKI blobs — a placeholder/garbage key can never ship unnoticed.
    [Fact]
    public void EmbeddedAppKeysAreValidOrEmpty()
    {
        foreach (var spki in UpdateKeys.PublicKeys)
        {
            using var ecdsa = ECDsa.Create();
            var ex = Record.Exception(() => ecdsa.ImportSubjectPublicKeyInfo(spki, out _));
            Assert.Null(ex);
        }
    }
}
