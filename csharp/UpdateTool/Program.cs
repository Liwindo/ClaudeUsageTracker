// Offline release-signing / verification tool. See UpdateTool.csproj header.
//
// Commands:
//   keygen  --out <priv.pem>
//       Create an ECDSA P-256 keypair. Writes the private key AES-256-encrypted
//       (passphrase from env CUT_UPDATE_KEY_PASS) to <priv.pem> and prints the
//       base64 SubjectPublicKeyInfo public key to paste into UpdateKeys.json.
//
//   sign    --key <priv.pem> --version <X.Y.Z> --out-dir <dir> --keys <UpdateKeys.json>
//           --asset <file> [--asset <file> …]
//       Build <dir>\update.json (schema/version/per-asset sha256+size), sign its
//       exact bytes → <dir>\update.json.sig (base64), then self-verify against
//       --keys and abort non-zero if the app would NOT accept it.
//
//   verify  --keys <UpdateKeys.json> --manifest <update.json> --sig <update.json.sig>
//           --current <X.Y.Z> [--asset name=<file> …]
//       Run the app's exact verification. Exit 0 only if it would install; else 1.
//
// The offline private key never leaves the developer's machine — this tool is
// the only thing that touches it, and it runs locally, never in CI.

using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ClaudeUsageTracker;

static string? Opt(string[] a, string name)
{
    for (var i = 0; i < a.Length - 1; i++)
        if (a[i] == name)
            return a[i + 1];
    return null;
}

static List<string> OptAll(string[] a, string name)
{
    var list = new List<string>();
    for (var i = 0; i < a.Length - 1; i++)
        if (a[i] == name)
            list.Add(a[i + 1]);
    return list;
}

static int Die(string message)
{
    Console.Error.WriteLine($"error: {message}");
    return 1;
}

static string RequirePass()
{
    var pass = Environment.GetEnvironmentVariable("CUT_UPDATE_KEY_PASS");
    if (string.IsNullOrEmpty(pass))
        throw new InvalidOperationException(
            "set CUT_UPDATE_KEY_PASS to the private-key passphrase");
    return pass;
}

// Deterministic manifest bytes: schema, version, then assets sorted by name.
// The SAME bytes are written to disk and signed, so the app verifies byte-for-byte.
static byte[] BuildManifestBytes(string version, IReadOnlyList<string> assetFiles)
{
    var buffer = new System.IO.MemoryStream();
    using (var w = new Utf8JsonWriter(buffer, new JsonWriterOptions { Indented = true }))
    {
        w.WriteStartObject();
        w.WriteNumber("schema", UpdateManifest.CurrentSchema);
        w.WriteString("version", version);
        w.WriteStartObject("assets");
        foreach (var file in assetFiles.OrderBy(System.IO.Path.GetFileName, StringComparer.Ordinal))
        {
            var bytes = System.IO.File.ReadAllBytes(file);
            w.WriteStartObject(System.IO.Path.GetFileName(file));
            w.WriteString("sha256", UpdateVerifier.Sha256Hex(bytes));
            w.WriteNumber("size", bytes.LongLength);
            w.WriteEndObject();
        }
        w.WriteEndObject();
        w.WriteEndObject();
    }
    return buffer.ToArray();
}

static IReadOnlyList<byte[]> LoadKeys(string keysJsonPath)
{
    using var doc = JsonDocument.Parse(System.IO.File.ReadAllText(keysJsonPath));
    var keys = new List<byte[]>();
    if (doc.RootElement.TryGetProperty("keys", out var arr) && arr.ValueKind == JsonValueKind.Array)
        foreach (var el in arr.EnumerateArray())
        {
            var b64 = el.GetString();
            if (!string.IsNullOrWhiteSpace(b64))
                keys.Add(Convert.FromBase64String(b64.Trim()));
        }
    return keys;
}

try
{
    if (args.Length == 0)
        return Die("usage: keygen | sign | verify (see Program.cs header)");

    switch (args[0])
    {
        case "keygen":
        {
            var outPath = Opt(args, "--out") ?? throw new InvalidOperationException("--out required");
            var pass = RequirePass();
            using var ec = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var pbe = new PbeParameters(PbeEncryptionAlgorithm.Aes256Cbc, HashAlgorithmName.SHA256, 600_000);
            var encrypted = ec.ExportEncryptedPkcs8PrivateKey(pass, pbe);
            var pem = PemEncoding.WriteString("ENCRYPTED PRIVATE KEY", encrypted);
            System.IO.File.WriteAllText(outPath, pem);
            var spki = ec.ExportSubjectPublicKeyInfo();
            Console.WriteLine("Private key (AES-256 encrypted) written to: " + outPath);
            Console.WriteLine("KEEP IT OFFLINE. Never commit it. Public key (base64 SPKI) for UpdateKeys.json:");
            Console.WriteLine(Convert.ToBase64String(spki));
            return 0;
        }

        case "sign":
        {
            var keyPath = Opt(args, "--key") ?? throw new InvalidOperationException("--key required");
            var version = Opt(args, "--version") ?? throw new InvalidOperationException("--version required");
            var outDir = Opt(args, "--out-dir") ?? throw new InvalidOperationException("--out-dir required");
            var keysJson = Opt(args, "--keys") ?? throw new InvalidOperationException("--keys required");
            var assets = OptAll(args, "--asset");
            if (assets.Count == 0)
                return Die("at least one --asset required");
            foreach (var f in assets)
                if (!System.IO.File.Exists(f))
                    return Die($"asset not found: {f}");

            var pass = RequirePass();
            using var ec = ECDsa.Create();
            ec.ImportFromEncryptedPem(System.IO.File.ReadAllText(keyPath), pass);

            var manifestBytes = BuildManifestBytes(version, assets);
            var signature = ec.SignData(manifestBytes, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation);

            System.IO.Directory.CreateDirectory(outDir);
            var manifestPath = System.IO.Path.Combine(outDir, "update.json");
            var sigPath = System.IO.Path.Combine(outDir, "update.json.sig");
            System.IO.File.WriteAllBytes(manifestPath, manifestBytes);
            System.IO.File.WriteAllText(sigPath, Convert.ToBase64String(signature) + "\n");

            // Self-verify with the SHIPPED public keys: refuse to hand off a
            // manifest the app would reject. This is the "can never be forgotten"
            // guarantee at the source — a release signed by a key the app does
            // not trust aborts HERE instead of being published. (Anti-rollback is
            // install-time and situational, so it is not part of this check; the
            // signature-against-embedded-keys gate is what must hold at signing.)
            var keys = LoadKeys(keysJson);
            if (keys.Count == 0)
                return Die("self-verify failed: --keys lists no public keys. "
                    + "Run 'keygen' and paste the public key into UpdateKeys.json first.");
            if (!UpdateVerifier.SignatureIsValid(manifestBytes, signature, keys))
                return Die("self-verify failed: signature does not match any embedded public key. "
                    + "Is UpdateKeys.json updated with THIS key's public half?");

            Console.WriteLine($"Signed {assets.Count} asset(s) for v{version}:");
            Console.WriteLine("  " + manifestPath);
            Console.WriteLine("  " + sigPath);
            return 0;
        }

        case "verify":
        {
            var keysJson = Opt(args, "--keys") ?? throw new InvalidOperationException("--keys required");
            var manifestPath = Opt(args, "--manifest") ?? throw new InvalidOperationException("--manifest required");
            var sigPath = Opt(args, "--sig") ?? throw new InvalidOperationException("--sig required");
            var current = Opt(args, "--current") ?? "0.0.0";
            var keys = LoadKeys(keysJson);

            var manifestBytes = System.IO.File.ReadAllBytes(manifestPath);
            var signature = Convert.FromBase64String(System.IO.File.ReadAllText(sigPath).Trim());

            // Verify each named asset the caller pins (name=path). At least one.
            var assetArgs = OptAll(args, "--asset");
            if (assetArgs.Count == 0)
                return Die("at least one --asset name=path required");

            foreach (var pair in assetArgs)
            {
                var eq = pair.IndexOf('=');
                if (eq <= 0)
                    return Die($"bad --asset '{pair}', expected name=path");
                var name = pair[..eq];
                var path = pair[(eq + 1)..];
                var result = UpdateVerifier.Verify(manifestBytes, signature, name, current, keys);
                if (!result.Ok)
                    return Die($"{name}: {result.Error}");
                var fileBytes = System.IO.File.ReadAllBytes(path);
                if (!UpdateVerifier.AssetContentMatches(result.Asset!, fileBytes))
                    return Die($"{name}: downloaded bytes do not match the signed sha256/size");
                Console.WriteLine($"OK  {name}: signature + digest verified (manifest v{UpdateManifest.TryParse(manifestBytes)!.Version})");
            }
            Console.WriteLine("VERIFIED: the app would accept this update.");
            return 0;
        }

        default:
            return Die($"unknown command '{args[0]}'");
    }
}
catch (Exception exc)
{
    return Die(exc.Message);
}
