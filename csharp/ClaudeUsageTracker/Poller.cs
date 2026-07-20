// Background polling thread.
//
// Runs ClaudeClient.FetchAll() on a configurable interval and invokes the
// registered callbacks with fresh UsageData or an error string.

namespace ClaudeUsageTracker;

public sealed class Poller
{
    private readonly Config _config;
    private readonly Action<UsageData> _onData;
    private readonly Action<string> _onError;
    private readonly ManualResetEventSlim _stopEvent = new(false);
    private readonly AutoResetEvent _forceEvent = new(false);
    private readonly Thread _thread;
    // Doubles after each consecutive 429, resets to 1 on success.
    // A manual "Refresh now" still bypasses the wait via _forceEvent.
    private int _backoffFactor = 1;

    public Poller(Config config, Action<UsageData> onData, Action<string> onError)
    {
        _config = config;
        _onData = onData;
        _onError = onError;
        _thread = new Thread(Loop) { IsBackground = true, Name = "poller" };
    }

    public void Start()
    {
        Log.Info("poller", $"Poller starting (interval={_config.PollIntervalSeconds}s)");
        _thread.Start();
    }

    public void Stop()
    {
        Log.Info("poller", "Poller stopping.");
        _stopEvent.Set();
        _forceEvent.Set();
        // Stop() can run on the UI thread (quit button): keep the join short —
        // an in-flight HTTP request may take up to 15 s, and the background
        // thread dies with the process anyway.
        _thread.Join(TimeSpan.FromSeconds(1));
    }

    /// <summary>Trigger an immediate poll outside the normal schedule.</summary>
    public void RefreshNow() => _forceEvent.Set();

    /// <summary>Doubles on each consecutive 429, capped at 16× the interval.</summary>
    internal static int NextBackoffFactor(int factor) => Math.Min(factor * 2, 16);

    private void Loop()
    {
        while (!_stopEvent.IsSet)
        {
            Poll();
            var timeout = TimeSpan.FromSeconds(_config.PollIntervalSeconds * _backoffFactor);
            _forceEvent.WaitOne(timeout);
        }
    }

    private void Poll()
    {
        Log.Debug("poller", "Poll cycle starting.");
        if (!System.Net.NetworkInformation.NetworkInterface.GetIsNetworkAvailable())
        {
            // No point hitting Cloudflare with no route — skip quietly and let
            // the widget show a network hint. The network-return trigger fires
            // an immediate poll once connectivity is back.
            Log.Debug("poller", "No network available — skipping poll.");
            _onError("Network error: no connection available.");
            return;
        }
        try
        {
            var cookies = FirefoxCookies.GetClaudeCookies(_config.FirefoxProfile);
            var orgId = FirefoxCookies.ExtractOrgId(cookies);
            var cookieHeader = FirefoxCookies.BuildCookieHeader(cookies);
            var data = ClaudeClient.FetchAll(
                orgId, cookieHeader,
                string.IsNullOrEmpty(_config.UserAgent) ? null : _config.UserAgent);
            Log.Info("poller", $"Poll OK: highest={data.HighestPercent}% tier={data.SubscriptionTier}");
            _backoffFactor = 1;
            _onData(data);
        }
        catch (RateLimitedException exc)
        {
            _backoffFactor = NextBackoffFactor(_backoffFactor);
            Log.Warning("poller",
                $"Rate limited: {exc.Message} (next poll in {_config.PollIntervalSeconds * _backoffFactor}s)");
            _onError(exc.Message);
        }
        catch (SessionExpiredException exc)
        {
            Log.Warning("poller", $"Session expired: {exc.Message}");
            _onError(exc.Message);
        }
        catch (Exception exc) when (exc is FirefoxCookieException or CookieException)
        {
            Log.Warning("poller", $"Browser cookie error: {exc.Message}");
            _onError(exc.Message);
        }
        catch (ClaudeClientException exc)
        {
            Log.Warning("poller", $"API error: {exc.Message}");
            _onError(exc.Message);
        }
        catch (Exception exc)
        {
            Log.Exception("poller", "Unhandled exception in poll cycle", exc);
            _onError($"Unexpected error: {exc.Message}");
        }
    }
}
