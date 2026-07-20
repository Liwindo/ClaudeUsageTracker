// Entry point.
//
// Enforces a single instance via a named Windows mutex (a different name than
// the Python variant, so both trackers can deliberately run side by side),
// then wires config, i18n, logging, autostart and the orchestrator.

using System.Windows;

namespace ClaudeUsageTracker;

public static class Program
{
    // Keep a static reference so the mutex handle lives for the whole process
    // lifetime — Windows releases it automatically on exit.
    private static Mutex? _instanceMutex;

    [STAThread]
    public static int Main()
    {
        // Detected language for the dialogs shown before the config is
        // available; re-initialised below once the configured language is known.
        I18n.Init("auto");

        if (AnotherInstanceRunning())
        {
            MessageBox.Show(
                I18n.Tr("dialog.already_running.body"),
                I18n.Tr("dialog.already_running.title"),
                MessageBoxButton.OK, MessageBoxImage.Information);
            return 0;
        }

        // Arm the logger with defaults first: Config.Load and I18n.Init log
        // migration/parse warnings, which would otherwise be dropped silently
        // (the configured level is applied right after the config is read).
        Log.Setup("WARNING");

        Config config;
        try
        {
            config = Config.Load();
        }
        catch (Exception exc)
        {
            MessageBox.Show(
                I18n.Tr("dialog.startup_error.body", ("error", exc.Message)),
                I18n.Tr("dialog.startup_error.title"),
                MessageBoxButton.OK, MessageBoxImage.Error);
            return 1;
        }

        I18n.Init(config.Language);
        Log.Setup(config.LogLevel);
        Autostart.Sync(config.Autostart);
        EfficiencyMode.Enable();

        try
        {
            // A 256 px widget needs no GPU pipeline; software rendering avoids
            // the D3D surfaces and driver allocations WPF otherwise keeps
            // resident for the process lifetime.
            System.Windows.Media.RenderOptions.ProcessRenderMode =
                System.Windows.Interop.RenderMode.SoftwareOnly;
            var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            new AppOrchestrator(config, app).Run();
            return 0;
        }
        catch (Exception exc)
        {
            Log.Exception("main", "Fatal error — application will exit", exc);
            MessageBox.Show(
                I18n.Tr("dialog.fatal.body", ("error", exc.Message), ("log_file", AppPaths.LogFilePath)),
                I18n.Tr("dialog.fatal.title"),
                MessageBoxButton.OK, MessageBoxImage.Error);
            return 1;
        }
    }

    /// <summary>Create the app's named mutex; true if another instance already
    /// owns it. Never throws — if the mutex cannot be created, startup proceeds
    /// (running twice is annoying, refusing to start is worse).</summary>
    private static bool AnotherInstanceRunning()
    {
        try
        {
            _instanceMutex = new Mutex(false, "claude-usage-tracker-cs-single-instance", out var createdNew);
            return !createdNew;
        }
        catch (Exception)
        {
            return false;
        }
    }
}
