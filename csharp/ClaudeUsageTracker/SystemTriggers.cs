// React to OS state changes that make a fresh poll worthwhile.
//
// After resume-from-standby the widget would otherwise show up to a full poll
// interval of stale data (or a stale network error); when connectivity returns
// the same applies. Both events fire an immediate refresh. In the Python
// variant this needed polling crutches — here it is a couple of native event
// subscriptions with a message pump the WPF app already runs.

using Microsoft.Win32;
using System.Net.NetworkInformation;

namespace ClaudeUsageTracker;

public sealed class SystemTriggers : IDisposable
{
    private readonly Action _onWake;
    private bool _disposed;

    public SystemTriggers(Action onWake)
    {
        _onWake = onWake;
        SystemEvents.PowerModeChanged += OnPowerModeChanged;
        NetworkChange.NetworkAvailabilityChanged += OnNetworkAvailabilityChanged;
    }

    private void OnPowerModeChanged(object sender, PowerModeChangedEventArgs e)
    {
        if (e.Mode == PowerModes.Resume)
        {
            Log.Info("triggers", "Resume from standby — refreshing.");
            SafeInvoke();
        }
    }

    private void OnNetworkAvailabilityChanged(object? sender, NetworkAvailabilityEventArgs e)
    {
        if (e.IsAvailable)
        {
            Log.Info("triggers", "Network available — refreshing.");
            SafeInvoke();
        }
    }

    private void SafeInvoke()
    {
        try
        {
            _onWake();
        }
        catch (Exception exc)
        {
            Log.Warning("triggers", $"Refresh trigger failed: {exc.Message}");
        }
    }

    public void Dispose()
    {
        if (_disposed)
            return;
        _disposed = true;
        SystemEvents.PowerModeChanged -= OnPowerModeChanged;
        NetworkChange.NetworkAvailabilityChanged -= OnNetworkAvailabilityChanged;
    }
}
