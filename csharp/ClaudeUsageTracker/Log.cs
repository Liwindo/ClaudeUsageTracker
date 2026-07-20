// Minimal thread-safe file logger with size-based rotation (500 KB, 1 backup),
// mirroring the Python variant's RotatingFileHandler setup.

using System.IO;
using System.Text;

namespace ClaudeUsageTracker;

public enum LogLevel
{
    Debug = 10,
    Info = 20,
    Warning = 30,
    Error = 40,
}

public static class Log
{
    private const long MaxBytes = 500_000;
    private static readonly object Lock = new();
    private static LogLevel _level = LogLevel.Warning;
    private static string? _filePath;

    internal static LogLevel ActiveLevel => _level;

    /// <summary>Configure level and target file. <paramref name="filePath"/>
    /// defaults to the app-data log; tests pass a temp path.</summary>
    public static void Setup(string configuredLevel, string? filePath = null)
    {
        _level = configuredLevel.Trim().ToUpperInvariant() switch
        {
            "DEBUG" => LogLevel.Debug,
            "INFO" => LogLevel.Info,
            "WARNING" => LogLevel.Warning,
            "ERROR" => LogLevel.Error,
            _ => LogLevel.Warning,
        };
        var path = filePath ?? AppPaths.LogFilePath;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        _filePath = path;
    }

    public static void Debug(string source, string message) => WriteLine(LogLevel.Debug, source, message);
    public static void Info(string source, string message) => WriteLine(LogLevel.Info, source, message);
    public static void Warning(string source, string message) => WriteLine(LogLevel.Warning, source, message);
    public static void Error(string source, string message) => WriteLine(LogLevel.Error, source, message);

    public static void Exception(string source, string message, Exception exc) =>
        WriteLine(LogLevel.Error, source, $"{message}: {exc}");

    private static void WriteLine(LogLevel level, string source, string message)
    {
        if (level < _level || _filePath is null)
            return;
        var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {level.ToString().ToUpperInvariant()} {source}: {message}{Environment.NewLine}";
        lock (Lock)
        {
            try
            {
                RotateIfNeeded();
                File.AppendAllText(_filePath, line, Encoding.UTF8);
            }
            catch
            {
                // Logging must never crash the app (read-only dir, disk full, …).
            }
        }
    }

    private static void RotateIfNeeded()
    {
        var info = new FileInfo(_filePath!);
        if (!info.Exists || info.Length < MaxBytes)
            return;
        var backup = _filePath + ".1";
        File.Delete(backup);
        File.Move(_filePath!, backup);
    }
}
