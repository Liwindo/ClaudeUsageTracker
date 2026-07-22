// System tray icon with colour-coded circle based on session usage.
//
// Uses a WinForms NotifyIcon hosted on the WPF UI thread (the WPF dispatcher
// pumps Windows messages, which is all NotifyIcon needs). All public members
// must be called on the UI thread.

using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ClaudeUsageTracker;

public sealed class TrayIcon : IDisposable
{
    private const int IconSize = 32;

    // NOTIFYICONDATAW.szTip is a fixed WCHAR[128] buffer (incl. NUL) — clip
    // to 127 chars so a long tooltip can never make a poll cycle fail.
    private const int MaxTip = 127;

    private static readonly Dictionary<string, Color> Colors = new()
    {
        ["green"] = ColorTranslator.FromHtml("#22c55e"),
        ["yellow"] = ColorTranslator.FromHtml("#eab308"),
        ["orange"] = ColorTranslator.FromHtml("#f97316"),
        ["red"] = ColorTranslator.FromHtml("#ef4444"),
        ["grey"] = ColorTranslator.FromHtml("#6b7280"),
    };

    private readonly NotifyIcon _icon;
    private readonly Dictionary<string, Icon> _iconCache = [];

    [DllImport("user32.dll")]
    private static extern bool DestroyIcon(IntPtr handle);

    public TrayIcon(Action onClickOpen, Action onClickRefresh, Action onSettings,
        Action onCheckUpdates, Action onQuit)
    {
        var menu = new ContextMenuStrip();
        // Disabled header line — shows which version is running.
        menu.Items.Add(new ToolStripMenuItem($"Claude Usage Tracker v{UpdateCheck.CurrentVersion}") { Enabled = false });
        menu.Items.Add(new ToolStripSeparator());
        var showHide = new ToolStripMenuItem(I18n.Tr("tray.menu.show_hide"));
        showHide.Click += (_, _) => onClickOpen();
        showHide.Font = new Font(showHide.Font, System.Drawing.FontStyle.Bold); // default item
        menu.Items.Add(showHide);
        var refresh = new ToolStripMenuItem(I18n.Tr("tray.menu.refresh"));
        refresh.Click += (_, _) => onClickRefresh();
        menu.Items.Add(refresh);
        var settings = new ToolStripMenuItem(I18n.Tr("tray.menu.settings"));
        settings.Click += (_, _) => onSettings();
        menu.Items.Add(settings);
        var checkUpdates = new ToolStripMenuItem(I18n.Tr("tray.menu.check_updates"));
        checkUpdates.Click += (_, _) => onCheckUpdates();
        menu.Items.Add(checkUpdates);
        menu.Items.Add(new ToolStripSeparator());
        var viewLog = new ToolStripMenuItem(I18n.Tr("tray.menu.view_log"));
        viewLog.Click += (_, _) => ViewLog();
        menu.Items.Add(viewLog);
        var openAppData = new ToolStripMenuItem(I18n.Tr("tray.menu.open_appdata"));
        openAppData.Click += (_, _) => OpenAppData();
        menu.Items.Add(openAppData);
        menu.Items.Add(new ToolStripSeparator());
        var quit = new ToolStripMenuItem(I18n.Tr("tray.menu.quit"));
        quit.Click += (_, _) => onQuit();
        menu.Items.Add(quit);

        _icon = new NotifyIcon
        {
            Icon = GetCircleIcon("grey"),
            Text = ClipTip(I18n.Tr("tray.loading")),
            ContextMenuStrip = menu,
            Visible = false,
        };
        _icon.MouseClick += (_, e) =>
        {
            if (e.Button == MouseButtons.Left)
                onClickOpen();
        };
        // A usage notification is always about claude.ai — clicking it opens the
        // site so "limit almost full" is one click from "let me check". Balloon
        // tips surface in the Action Center on Windows 10+, so the notification
        // is not lost if it is missed live.
        _icon.BalloonTipClicked += (_, _) => OpenClaude();
    }

    private static void OpenClaude()
    {
        try
        {
            Process.Start(new ProcessStartInfo("https://claude.ai/") { UseShellExecute = true });
        }
        catch (Exception exc)
        {
            Log.Warning("tray", $"Could not open claude.ai: {exc.Message}");
        }
    }

    internal static string ClipTip(string text) =>
        text.Length <= MaxTip ? text : text[..(MaxTip - 1)] + "…";

    internal static string SessionColor(int? percent)
    {
        if (percent is null)
            return "grey";
        if (percent >= 85)
            return "red";
        if (percent >= 60)
            return "orange";
        if (percent >= 40)
            return "yellow";
        return "green";
    }

    /// <summary>Plain filled circle, cached per colour. Deliberately no percent
    /// glyph on it — text is unreadable at 16 px tray size (owner decision);
    /// the exact numbers live in the tooltip and the widget.</summary>
    private Icon GetCircleIcon(string colorName)
    {
        var key = colorName;
        if (_iconCache.TryGetValue(key, out var cached))
            return cached;

        using var bitmap = new Bitmap(IconSize, IconSize);
        using (var g = Graphics.FromImage(bitmap))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.Clear(Color.Transparent);
            var fill = Colors.GetValueOrDefault(colorName, Colors["grey"]);
            using var brush = new SolidBrush(fill);
            const int margin = 1;
            g.FillEllipse(brush, margin, margin, IconSize - 2 * margin, IconSize - 2 * margin);
        }
        // Icon.FromHandle borrows the GDI handle; clone to own the resource,
        // then release the temporary handle to avoid a leak per colour change.
        var handle = bitmap.GetHicon();
        try
        {
            using var borrowed = Icon.FromHandle(handle);
            var icon = (Icon)borrowed.Clone();
            _iconCache[key] = icon;
            return icon;
        }
        finally
        {
            DestroyIcon(handle);
        }
    }

    public void Show() => _icon.Visible = true;

    /// <summary>Percent driving the icon colour: the session bucket if present,
    /// otherwise the worst bucket instead of a meaningless grey dot.</summary>
    internal static int? DisplayPercent(UsageData data)
    {
        var percent = data.SessionPercent;
        if (percent is null && data.Limits.Count > 0)
            percent = data.HighestPercent;
        return percent;
    }

    /// <summary>Refresh icon colour and tooltip from fresh UsageData.</summary>
    public void Update(UsageData data)
    {
        _icon.Icon = GetCircleIcon(SessionColor(DisplayPercent(data)));
        _icon.Text = ClipTip(data.TooltipText());
    }

    /// <summary>Switch to grey icon and show the error in the tooltip.</summary>
    public void SetError(string message)
    {
        _icon.Icon = GetCircleIcon("grey");
        _icon.Text = ClipTip(I18n.Tr("tray.error", ("message", message)));
    }

    /// <summary>Show a desktop notification. A hint that it can be clicked to
    /// open claude.ai is appended so the affordance is discoverable.</summary>
    public void ShowToast(string title, string message) =>
        _icon.ShowBalloonTip(8000, title, $"{message}\n({I18n.Tr("toast.open_claude")})", ToolTipIcon.Info);

    // Both handlers run on the UI thread: an unhandled exception here (missing
    // file association, unwritable dir) would take down the whole app.
    private static void ViewLog()
    {
        try
        {
            var path = AppPaths.LogFilePath;
            if (!File.Exists(path))
            {
                // Touch an empty file so the click never appears to do nothing.
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllText(path, "");
            }
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        }
        catch (Exception exc)
        {
            Log.Warning("tray", $"Could not open the log file: {exc.Message}");
        }
    }

    private static void OpenAppData()
    {
        try
        {
            Directory.CreateDirectory(AppPaths.ConfigDir);
            Process.Start(new ProcessStartInfo(AppPaths.ConfigDir) { UseShellExecute = true });
        }
        catch (Exception exc)
        {
            Log.Warning("tray", $"Could not open the app-data folder: {exc.Message}");
        }
    }

    public void Dispose()
    {
        _icon.Visible = false;
        _icon.Dispose();
        foreach (var icon in _iconCache.Values)
            icon.Dispose();
        _iconCache.Clear();
    }
}
