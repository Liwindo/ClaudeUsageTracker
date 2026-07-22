// Application orchestrator.
//
// Threading model:
//   - UI thread:     WPF dispatcher (widget + tray icon + toasts)
//   - Poller thread: background thread, fetches data every N seconds
//   - Update check:  one-shot background task per app start (never periodic —
//                    explicit owner decision from the Python variant)

using Application = System.Windows.Application;

namespace ClaudeUsageTracker;

public sealed class AppOrchestrator
{
    private readonly Config _config;
    private readonly Application _app;
    private readonly WidgetWindow _widget;
    private readonly TrayIcon _tray;
    private readonly NotificationManager _notifier;
    private readonly Poller _poller;
    private SystemTriggers? _triggers;
    private Timer? _trimTimer;
    private bool _quitting;

    public AppOrchestrator(Config config, Application app)
    {
        _config = config;
        _app = app;

        _widget = new WidgetWindow(OnRefreshRequested, ShowSettings, Quit);
        _tray = new TrayIcon(
            onClickOpen: _widget.Toggle,
            onClickRefresh: OnRefreshRequested,
            onSettings: ShowSettings,
            onCheckUpdates: CheckForUpdatesNow,
            onQuit: Quit);
        _notifier = new NotificationManager(config.NotificationThresholds, _tray.ShowToast);
        _poller = new Poller(config, OnData, OnError);
    }

    /// <summary>Start everything. Blocks until the user quits.</summary>
    public void Run()
    {
        RaiseVersionFloor();
        // Remove any installer staged by a previous update: after an update the
        // freshly-installed version relaunches and this start sweeps it away.
        UpdateInstaller.CleanUpStagedInstallers();
        _poller.Start();
        _tray.Show();
        if (_config.UpdateCheck)
        {
            Task.Run(() =>
            {
                // Delayed a few seconds so the GitHub request never competes
                // with the UI startup and the dialog appears after the widget
                // is on screen.
                Thread.Sleep(3000);
                var info = UpdateCheck.CheckForUpdate(_config.SkipUpdateVersion);
                if (info is not null)
                    _widget.NotifyUpdate(info, EffectiveVersionFloor(), () => SkipUpdate(info.LatestVersion));
            });
        }
        if (!_widget.StartMinimized)
            _widget.Show();
        // Keep the idle footprint small: first trim once startup settled,
        // then every 5 minutes (cold pages fault back in when needed).
        _trimTimer = new Timer(_ => WorkingSetTrimmer.Trim(), null,
            TimeSpan.FromSeconds(15), TimeSpan.FromMinutes(5));
        // Refresh immediately when the machine wakes or the network returns.
        _triggers = new SystemTriggers(OnRefreshRequested);
        _app.Run(); // blocks; ShutdownMode is OnExplicitShutdown
    }

    private void OnData(UsageData data)
    {
        // Called on the poller thread — marshal everything to the UI thread.
        _widget.Post(() =>
        {
            _tray.Update(data);
            _notifier.Process(data);
        });
        _widget.UpdateData(data);
    }

    private void OnError(string message)
    {
        _widget.Post(() => _tray.SetError(message));
        _widget.SetError(message);
    }

    private void OnRefreshRequested() => _poller.RefreshNow();

    private SettingsWindow? _settingsWindow;

    private void ShowSettings() => _widget.Post(() =>
    {
        if (_settingsWindow is not null)
        {
            _settingsWindow.Activate();
            return;
        }
        _settingsWindow = new SettingsWindow(_config, OnSettingsApplied, CheckForUpdatesNow);
        _settingsWindow.Closed += (_, _) => _settingsWindow = null;
        _settingsWindow.Show();
        _settingsWindow.Activate();
    });

    /// <summary>Manual "check for updates now" from the settings dialog. Runs off
    /// the UI thread and reports all three outcomes distinctly — a newer release
    /// opens the update dialog, otherwise a short message says up-to-date or that
    /// the check failed (so a network error never masquerades as "up to date").
    /// Ignores the skip-version preference: a manual check always surfaces.</summary>
    private void CheckForUpdatesNow() => Task.Run(() =>
    {
        var result = UpdateCheck.CheckDetailed("");
        _widget.Post(() =>
        {
            switch (result.Status)
            {
                case UpdateCheckStatus.Available:
                    _widget.NotifyUpdate(result.Info!, EffectiveVersionFloor(), () => SkipUpdate(result.Info!.LatestVersion));
                    break;
                case UpdateCheckStatus.UpToDate:
                    System.Windows.MessageBox.Show(
                        I18n.Tr("update.up_to_date", ("version", UpdateCheck.CurrentVersion)),
                        I18n.Tr("update.window_title"),
                        System.Windows.MessageBoxButton.OK, System.Windows.MessageBoxImage.Information);
                    break;
                default:
                    System.Windows.MessageBox.Show(
                        I18n.Tr("update.check_failed"),
                        I18n.Tr("update.window_title"),
                        System.Windows.MessageBoxButton.OK, System.Windows.MessageBoxImage.Warning);
                    break;
            }
        });
    });

    private void OnSettingsApplied(Config config)
    {
        // Config is the same instance the poller reads, so the new poll interval
        // is picked up on the next cycle; apply the rest that can change live.
        Log.Setup(config.LogLevel);
        _notifier.UpdateThresholds(config.NotificationThresholds);
        Autostart.Sync(config.Autostart);
        Log.Info("app", "Settings applied.");
        _poller.RefreshNow(); // reflect the new interval / thresholds promptly
    }

    /// <summary>The anti-rollback floor to gate an install against: whichever is
    /// greater, the running version or the persisted highest-seen version.</summary>
    private string EffectiveVersionFloor() =>
        UpdateVerifier.HigherVersion(UpdateCheck.CurrentVersion, _config.UpdateVersionFloor);

    /// <summary>Record the highest version this install has ever run, so a later
    /// (legitimately signed but older) release can never be pushed onto us. The
    /// floor only ever rises; a downgrade/manual roll-back keeps the old floor.
    /// Best-effort persistence — a read-only config must not prevent startup.</summary>
    private void RaiseVersionFloor()
    {
        var floor = EffectiveVersionFloor();
        if (floor == _config.UpdateVersionFloor)
            return;
        _config.UpdateVersionFloor = floor;
        try
        {
            _config.Save();
            Log.Info("app", $"Update version floor raised to {floor}.");
        }
        catch (Exception exc)
        {
            Log.Warning("app", $"Could not persist version floor: {exc.Message}");
        }
    }

    private void SkipUpdate(string version)
    {
        Log.Info("app", $"User skipped update {version}.");
        _config.SkipUpdateVersion = version;
        try
        {
            _config.Save();
        }
        catch (Exception exc)
        {
            Log.Warning("app", $"Could not persist skipped version: {exc.Message}");
        }
    }

    private void Quit()
    {
        if (_quitting)
            return;
        _quitting = true;
        Log.Info("app", "Quitting.");
        _triggers?.Dispose();
        _trimTimer?.Dispose();
        _poller.Stop();
        _widget.Shutdown();
        _tray.Dispose();
        _app.Shutdown();
    }
}
