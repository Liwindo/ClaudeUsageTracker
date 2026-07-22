// Persistent always-on-top mini-widget showing Claude usage statistics.
//
// WPF port of the tkinter widget: opaque "glass" card with a vertical
// gradient, rounded corners, gradient pill progress bars, glowing status dot,
// hover-revealed buttons, drag-to-move, width resize grip, peak-hour banner
// and position persistence. Built entirely in code (no XAML) so the whole
// widget lives in one file, mirroring the Python module layout.

using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;
using System.Windows.Threading;
using Brush = System.Windows.Media.Brush;
using Button = System.Windows.Controls.Button;
using Color = System.Windows.Media.Color;
using ContextMenu = System.Windows.Controls.ContextMenu;

namespace ClaudeUsageTracker;

public sealed class WidgetWindow : Window
{
    // ── Design tokens — identical palette to the Python widget ───────────────
    private static readonly Color BgRim = FromHex("#2c2c36");
    private static readonly Color BgSheen = FromHex("#1e1e26");
    private static readonly Color Bg = FromHex("#16161c");
    private static readonly Color BgBase = FromHex("#10101a");
    private static readonly Color BgShadow = FromHex("#08080d");
    private static readonly Color TextColor = FromHex("#ececf2");
    private static readonly Color Dim = FromHex("#9494a0");
    private static readonly Color FootC = FromHex("#7a7a84");
    private static readonly Color BorderC = FromHex("#2e2e38");
    private static readonly Color Track = FromHex("#1f1f27");
    private static readonly Color BtnBg = FromHex("#26262e");
    private static readonly Color BtnHov = FromHex("#34343e");

    // Status colours — identical to TrayIcon so widget and icon stay in sync.
    private static readonly Color Ok = FromHex("#22c55e");
    private static readonly Color Yellow = FromHex("#eab308");
    private static readonly Color Warn = FromHex("#f97316");
    private static readonly Color Alert = FromHex("#ef4444");

    private const double DefaultWidth = 256;
    private const double MinWidgetWidth = 200;
    private const double BarHeight = 6;

    private static readonly string[] WeeklyKeys =
    [
        "seven_day", "seven_day_sonnet", "seven_day_opus",
        "seven_day_omelette", "seven_day_cowork",
    ];

    private readonly Action _onRefresh;
    private readonly Action _onSettings;
    private readonly Action _onQuit;

    private TextBlock _versionLabel = null!;
    private TextBlock _peakBanner = null!;
    private TextBlock _sessionPct = null!;
    private TextBlock _weeklyPct = null!;
    private Border _sessionFill = null!;
    private Border _weeklyFill = null!;
    private Border _sessionTrack = null!;
    private Border _weeklyTrack = null!;
    private Ellipse _dotGlow = null!;
    private Ellipse _dotCore = null!;
    private TextBlock _footerText = null!;
    private StackPanel _buttonPanel = null!;

    private UsageData? _lastData;
    private string? _lastError;
    private bool _minimized;
    private Window? _updateWindow;
    private readonly DispatcherTimer _peakTimer;

    // Bottom-anchored geometry. The peak banner (and wrapped footer text) change
    // the window height at runtime; SizeToContent=Height would keep the TOP fixed
    // and grow the window DOWNWARD, so the widget's resting bottom corner jumps on
    // every peak/non-peak transition. To match the Python variant (whose 1.4.1
    // bugfix pinned the bottom edge), `_bottomAnchor` holds the authoritative
    // screen-Y of the bottom edge — the value the user controls by dragging and
    // the value persisted. On any height change the top is moved so the bottom
    // stays put. `_pendingBottom` carries a restored anchor across to first layout
    // (ActualHeight is only known then); null means migrate from a legacy top.
    private double _bottomAnchor;
    private bool _anchorReady;
    private bool _adjustingTop;
    private double? _pendingBottom;

    public WidgetWindow(Action onRefresh, Action onSettings, Action onQuit)
    {
        _onRefresh = onRefresh;
        _onSettings = onSettings;
        _onQuit = onQuit;

        Title = "Claude Status";
        WindowStyle = WindowStyle.None;
        ResizeMode = ResizeMode.NoResize;
        AllowsTransparency = true;
        Background = Brushes.Transparent;
        Topmost = true;
        ShowInTaskbar = false;
        SizeToContent = SizeToContent.Height;
        Width = DefaultWidth;

        Content = BuildUi();
        RestorePosition();

        MouseLeftButtonDown += OnDragStart;
        MouseEnter += (_, _) => FadeChrome(visible: true);
        MouseLeave += (_, _) => FadeChrome(visible: false);
        ContextMenu = BuildContextMenu();

        // Re-check the peak-hour state once per minute.
        _peakTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(60) };
        _peakTimer.Tick += (_, _) => RefreshPeakBanner();
        _peakTimer.Start();

        Loaded += (_, _) =>
        {
            // Establish the authoritative bottom anchor from the banner-free
            // layout, BEFORE any data or peak banner grows the window, so every
            // subsequent height change pins the bottom edge instead of moving it.
            if (_pendingBottom is double bottom)
                Top = WidgetGeometry.TopForBottom(bottom, ActualHeight);
            _bottomAnchor = WidgetGeometry.BottomOf(Top, ActualHeight);
            _anchorReady = true;

            // Render any snapshot that arrived before the UI was shown (the
            // first poll usually completes before the window is up).
            if (_lastError is not null)
                ApplyError(_lastError);
            else if (_lastData is not null)
                ApplyData(_lastData);
            RefreshPeakBanner();
        };
    }

    public bool StartMinimized => _minimized;

    // ── Public API (thread-safe) ─────────────────────────────────────────────

    public void Post(Action action)
    {
        try
        {
            Dispatcher.BeginInvoke(action);
        }
        catch (Exception)
        {
            // Tolerate shutdown races: a late poll result must never crash.
        }
    }

    public void UpdateData(UsageData data) => Post(() => ApplyData(data));

    public void SetError(string message) => Post(() => ApplyError(message));

    public void Toggle() => Post(() =>
    {
        if (IsVisible)
        {
            Hide();
            _minimized = true;
        }
        else
        {
            Show();
            Topmost = true;
            _minimized = false;
            RefreshPeakBanner();
        }
        SavePosition();
    });

    public void NotifyUpdate(UpdateInfo info, string versionFloor, Action? onSkip) =>
        Post(() => ShowUpdateDialog(info, versionFloor, onSkip));

    public void Shutdown() => Post(() =>
    {
        _peakTimer.Stop();
        Close();
    });

    // ── UI construction ──────────────────────────────────────────────────────

    private static Color FromHex(string hex) => (Color)ColorConverter.ConvertFromString(hex);

    // Frozen-brush caches: the palette is tiny and every setter runs once per
    // poll, so reusing frozen brushes avoids per-update allocations and lets
    // WPF share the render resources.
    private static readonly Dictionary<Color, Brush> SolidCache = [];
    private static readonly Dictionary<Color, Brush> BarGradientCache = [];
    private static readonly Dictionary<Color, Brush> GlowCache = [];

    private static Brush Solid(Color color)
    {
        if (!SolidCache.TryGetValue(color, out var brush))
        {
            brush = new SolidColorBrush(color);
            brush.Freeze();
            SolidCache[color] = brush;
        }
        return brush;
    }

    private static Brush BarGradient(Color color)
    {
        if (!BarGradientCache.TryGetValue(color, out var brush))
        {
            var dark = Color.FromRgb((byte)(color.R * 0.72), (byte)(color.G * 0.72), (byte)(color.B * 0.72));
            var gradient = new LinearGradientBrush(dark, color,
                new System.Windows.Point(0, 0), new System.Windows.Point(1, 0));
            gradient.Freeze();
            BarGradientCache[color] = brush = gradient;
        }
        return brush;
    }

    private static Brush Glow(Color color)
    {
        if (!GlowCache.TryGetValue(color, out var brush))
        {
            var glow = new RadialGradientBrush(
                Color.FromArgb(90, color.R, color.G, color.B),
                Color.FromArgb(0, color.R, color.G, color.B));
            glow.Freeze();
            GlowCache[color] = brush = glow;
        }
        return brush;
    }

    private FrameworkElement BuildUi()
    {
        // Vertical-gradient surface: rim highlight → sheen → body → base → shadow.
        var gradient = new LinearGradientBrush
        {
            StartPoint = new System.Windows.Point(0, 0),
            EndPoint = new System.Windows.Point(0, 1),
        };
        gradient.GradientStops.Add(new GradientStop(BgRim, 0.0));
        gradient.GradientStops.Add(new GradientStop(BgSheen, 0.012));
        gradient.GradientStops.Add(new GradientStop(Bg, 0.03));
        gradient.GradientStops.Add(new GradientStop(Bg, 0.97));
        gradient.GradientStops.Add(new GradientStop(BgBase, 0.988));
        gradient.GradientStops.Add(new GradientStop(BgShadow, 1.0));
        gradient.Freeze();

        var card = new StackPanel { Margin = new Thickness(18, 14, 18, 14) };

        // Title row: app name + hover-revealed version.
        var titleRow = new DockPanel { Margin = new Thickness(0, 0, 0, 10) };
        _versionLabel = new TextBlock
        {
            Text = $"v{UpdateCheck.CurrentVersion}",
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 11,
            Foreground = Solid(FootC),
            Opacity = 0,
            HorizontalAlignment = HorizontalAlignment.Right,
        };
        DockPanel.SetDock(_versionLabel, Dock.Right);
        titleRow.Children.Add(_versionLabel);
        titleRow.Children.Add(new TextBlock
        {
            Text = "Claude Usage Tracker",
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 13.5,
            FontWeight = FontWeights.Bold,
            Foreground = Solid(TextColor),
        });
        card.Children.Add(titleRow);

        // Peak-hour banner — collapsed outside Anthropic's peak window.
        _peakBanner = new TextBlock
        {
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 11,
            Foreground = Solid(Warn),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 0, 0, 8),
            Visibility = Visibility.Collapsed,
        };
        card.Children.Add(_peakBanner);

        (var sessionRow, _sessionPct, _sessionTrack, _sessionFill) =
            BuildMetricRow(I18n.Tr("widget.metric.session"));
        card.Children.Add(sessionRow);
        card.Children.Add(new Border { Height = 10 });
        (var weeklyRow, _weeklyPct, _weeklyTrack, _weeklyFill) =
            BuildMetricRow(I18n.Tr("widget.metric.weekly"));
        card.Children.Add(weeklyRow);

        // Divider whose alpha fades to 0 at both ends.
        var dividerBrush = new LinearGradientBrush
        {
            StartPoint = new System.Windows.Point(0, 0),
            EndPoint = new System.Windows.Point(1, 0),
        };
        dividerBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, BorderC.R, BorderC.G, BorderC.B), 0));
        dividerBrush.GradientStops.Add(new GradientStop(Color.FromArgb(220, BorderC.R, BorderC.G, BorderC.B), 0.5));
        dividerBrush.GradientStops.Add(new GradientStop(Color.FromArgb(0, BorderC.R, BorderC.G, BorderC.B), 1));
        dividerBrush.Freeze();
        card.Children.Add(new Border
        {
            Height = 1,
            Background = dividerBrush,
            Margin = new Thickness(0, 12, 0, 8),
        });

        // Footer: status dot + status text + hover-revealed buttons.
        var footer = new DockPanel { LastChildFill = true };

        _buttonPanel = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Opacity = 0,
            VerticalAlignment = VerticalAlignment.Center,
        };
        _buttonPanel.Children.Add(MakeFooterButton("⟳", () => _onRefresh()));
        _buttonPanel.Children.Add(MakeFooterButton("−", Minimize));
        _buttonPanel.Children.Add(MakeFooterButton("×", () => _onQuit()));
        DockPanel.SetDock(_buttonPanel, Dock.Right);
        footer.Children.Add(_buttonPanel);

        var dotGrid = new Grid
        {
            Width = 14,
            Height = 14,
            VerticalAlignment = VerticalAlignment.Center,
        };
        _dotGlow = new Ellipse { Width = 14, Height = 14 };
        _dotCore = new Ellipse
        {
            Width = 5.2,
            Height = 5.2,
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
        };
        dotGrid.Children.Add(_dotGlow);
        dotGrid.Children.Add(_dotCore);
        DockPanel.SetDock(dotGrid, Dock.Left);
        footer.Children.Add(dotGrid);
        SetDotColor(Ok);

        _footerText = new TextBlock
        {
            Text = I18n.Tr("widget.status.connecting"),
            FontFamily = new FontFamily("Consolas"),
            FontSize = 11,
            Foreground = Solid(FootC),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(6, 0, 0, 0),
            VerticalAlignment = VerticalAlignment.Center,
        };
        footer.Children.Add(_footerText);
        card.Children.Add(footer);

        var border = new Border
        {
            CornerRadius = new CornerRadius(10),
            Background = gradient,
            BorderBrush = Solid(BorderC),
            BorderThickness = new Thickness(1),
            Child = card,
        };

        // Width resize grip in the bottom-right corner (height fits content).
        var grip = new Thumb
        {
            Width = 14,
            Height = 14,
            HorizontalAlignment = HorizontalAlignment.Right,
            VerticalAlignment = VerticalAlignment.Bottom,
            Cursor = Cursors.SizeWE,
            Opacity = 0,
            Template = BuildGripTemplate(),
        };
        grip.DragDelta += (_, e) =>
        {
            Width = Math.Max(MinWidgetWidth, Width + e.HorizontalChange);
        };
        grip.DragCompleted += (_, _) =>
        {
            UpdateBarWidths();
            SavePosition();
        };

        var root = new Grid();
        root.Children.Add(border);
        root.Children.Add(grip);

        SizeChanged += (_, e) =>
        {
            UpdateBarWidths();
            if (e.HeightChanged)
                AnchorBottom();
        };
        return root;
    }

    /// <summary>Keep the window's bottom edge pinned to <see cref="_bottomAnchor"/>
    /// when its height changes (peak banner appearing/disappearing, footer text
    /// wrapping): move the top up/down by the delta instead of letting
    /// SizeToContent grow the window downward. Setting Top is a move, not a
    /// resize, so it raises no further SizeChanged; the guard is belt-and-braces.
    /// A no-op while the anchor is not yet established (before first layout) or
    /// while we are the ones adjusting the top.</summary>
    private void AnchorBottom()
    {
        if (!_anchorReady || _adjustingTop)
            return;
        var desiredTop = WidgetGeometry.TopForBottom(_bottomAnchor, ActualHeight);
        if (Math.Abs(Top - desiredTop) > 0.5)
        {
            _adjustingTop = true;
            Top = desiredTop;
            _adjustingTop = false;
        }
    }

    private static ControlTemplate BuildGripTemplate()
    {
        var factory = new FrameworkElementFactory(typeof(TextBlock));
        factory.SetValue(TextBlock.TextProperty, "◢");
        factory.SetValue(TextBlock.FontSizeProperty, 11.0);
        factory.SetValue(TextBlock.ForegroundProperty, Solid(BorderC));
        factory.SetValue(TextBlock.MarginProperty, new Thickness(0, 0, 3, 1));
        return new ControlTemplate(typeof(Thumb)) { VisualTree = factory };
    }

    private (FrameworkElement Row, TextBlock Pct, Border Track, Border Fill) BuildMetricRow(string label)
    {
        var row = new StackPanel();

        var top = new DockPanel();
        var pct = new TextBlock
        {
            Text = "—",
            FontFamily = new FontFamily("Consolas"),
            FontSize = 15,
            FontWeight = FontWeights.Bold,
            Foreground = Solid(Alert),
        };
        DockPanel.SetDock(pct, Dock.Right);
        top.Children.Add(pct);
        top.Children.Add(new TextBlock
        {
            Text = label,
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 11,
            Foreground = Solid(Dim),
            VerticalAlignment = VerticalAlignment.Center,
        });
        row.Children.Add(top);

        var fill = new Border
        {
            CornerRadius = new CornerRadius(BarHeight / 2),
            HorizontalAlignment = HorizontalAlignment.Left,
            Width = 0,
        };
        var track = new Border
        {
            Height = BarHeight,
            CornerRadius = new CornerRadius(BarHeight / 2),
            Background = Solid(Track),
            Margin = new Thickness(0, 5, 0, 0),
            Child = fill,
        };
        row.Children.Add(track);

        return (row, pct, track, fill);
    }

    private Button MakeFooterButton(string glyph, Action onClick)
    {
        var button = new Button
        {
            Content = glyph,
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 12,
            Foreground = Solid(FootC),
            Background = Solid(BtnBg),
            BorderThickness = new Thickness(0),
            Padding = new Thickness(6, 1, 6, 1),
            Margin = new Thickness(1, 0, 1, 0),
            Cursor = Cursors.Hand,
            Focusable = false,
        };
        // Flat template: WPF's default button chrome ignores Background on hover.
        var borderFactory = new FrameworkElementFactory(typeof(Border));
        borderFactory.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(BackgroundProperty));
        borderFactory.SetValue(Border.CornerRadiusProperty, new CornerRadius(3));
        borderFactory.SetValue(Border.PaddingProperty, new TemplateBindingExtension(PaddingProperty));
        var contentFactory = new FrameworkElementFactory(typeof(ContentPresenter));
        contentFactory.SetValue(HorizontalAlignmentProperty, HorizontalAlignment.Center);
        contentFactory.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
        borderFactory.AppendChild(contentFactory);
        button.Template = new ControlTemplate(typeof(Button)) { VisualTree = borderFactory };
        button.MouseEnter += (_, _) =>
        {
            button.Background = Solid(BtnHov);
            button.Foreground = Solid(TextColor);
        };
        button.MouseLeave += (_, _) =>
        {
            button.Background = Solid(BtnBg);
            button.Foreground = Solid(FootC);
        };
        button.Click += (_, _) => onClick();
        return button;
    }

    private ContextMenu BuildContextMenu()
    {
        var menu = new ContextMenu();
        var refresh = new MenuItem { Header = I18n.Tr("widget.menu.refresh") };
        refresh.Click += (_, _) => _onRefresh();
        menu.Items.Add(refresh);
        var settings = new MenuItem { Header = I18n.Tr("widget.menu.settings") };
        settings.Click += (_, _) => _onSettings();
        menu.Items.Add(settings);
        var quit = new MenuItem { Header = I18n.Tr("widget.menu.quit") };
        quit.Click += (_, _) => _onQuit();
        menu.Items.Add(quit);
        return menu;
    }

    // ── Hover fade ───────────────────────────────────────────────────────────

    private void FadeChrome(bool visible)
    {
        var animation = new DoubleAnimation(visible ? 1 : 0, TimeSpan.FromMilliseconds(130));
        _buttonPanel.BeginAnimation(OpacityProperty, animation);
        _versionLabel.BeginAnimation(OpacityProperty, animation);
    }

    // ── Drag ─────────────────────────────────────────────────────────────────

    private void OnDragStart(object sender, MouseButtonEventArgs e)
    {
        if (e.OriginalSource is DependencyObject source && HasButtonAncestor(source))
            return;
        try
        {
            DragMove(); // blocks until the button is released
        }
        catch (InvalidOperationException)
        {
            return; // button already released
        }
        SnapToEdges();
        // The user just chose a new resting place — re-anchor the bottom edge to
        // it so a later peak-banner grow keeps this position, not a stale one.
        _bottomAnchor = WidgetGeometry.BottomOf(Top, ActualHeight);
        SavePosition();
    }

    /// <summary>Snap the window flush against the nearest working-area edge when
    /// it is dropped within a small threshold — the widget clicks into the
    /// corner instead of floating a few pixels off. DPI-correct: the WinForms
    /// working area is device pixels, so it is scaled to WPF DIPs first.</summary>
    private void SnapToEdges()
    {
        const double threshold = 24; // DIP
        const double margin = 12;    // resting gap from the edge
        try
        {
            var handle = new System.Windows.Interop.WindowInteropHelper(this).Handle;
            var screen = System.Windows.Forms.Screen.FromHandle(handle);
            var dpi = VisualTreeHelper.GetDpi(this);
            var wa = screen.WorkingArea; // device px
            double left = wa.Left / dpi.DpiScaleX;
            double top = wa.Top / dpi.DpiScaleY;
            double right = wa.Right / dpi.DpiScaleX;
            double bottom = wa.Bottom / dpi.DpiScaleY;

            if (Math.Abs(Left - left) <= threshold)
                Left = left + margin;
            else if (Math.Abs(right - (Left + ActualWidth)) <= threshold)
                Left = right - ActualWidth - margin;

            if (Math.Abs(Top - top) <= threshold)
                Top = top + margin;
            else if (Math.Abs(bottom - (Top + ActualHeight)) <= threshold)
                Top = bottom - ActualHeight - margin;
        }
        catch (Exception)
        {
            // Snapping is cosmetic — never let a monitor-query hiccup matter.
        }
    }

    private static bool HasButtonAncestor(DependencyObject node)
    {
        for (DependencyObject? current = node; current is not null;
             current = VisualTreeHelper.GetParent(current))
        {
            if (current is Button or Thumb)
                return true;
        }
        return false;
    }

    // ── Colour helpers ───────────────────────────────────────────────────────

    internal static Color PctColor(int pct)
    {
        if (pct >= 85)
            return Alert;
        if (pct >= 60)
            return Warn;
        if (pct >= 40)
            return Yellow;
        return Ok;
    }

    /// <summary>Green = reset imminent (limit refreshes soon), red = far away.</summary>
    private static Color ResetColor(LimitInfo? li)
    {
        if (li is null)
            return Ok;
        var secs = li.ResetsInSeconds;
        if (secs < 15 * 60)
            return Ok;
        if (secs < 30 * 60)
            return Yellow;
        if (secs < 90 * 60)
            return Warn;
        return Alert;
    }

    // ── Peak-hour banner ─────────────────────────────────────────────────────

    /// <summary>If now lies inside Anthropic's peak window (weekdays
    /// 05:00–11:00 Pacific Time), return its (start, end) wall-clock times in
    /// the OS's local zone as "HH:mm" strings; null otherwise. Minutes matter:
    /// half-hour zones land the window off the full hour.</summary>
    internal static (string Start, string End)? PeakHourWindowLocal(DateTimeOffset? nowUtc = null)
    {
        TimeZoneInfo peakTz;
        try
        {
            peakTz = TimeZoneInfo.FindSystemTimeZoneById("Pacific Standard Time");
        }
        catch (Exception exc) when (exc is TimeZoneNotFoundException or InvalidTimeZoneException)
        {
            // No usable Pacific zone data → no banner; never crash the timer.
            return null;
        }
        var now = nowUtc ?? DateTimeOffset.UtcNow;
        var nowPt = TimeZoneInfo.ConvertTime(now, peakTz);
        if (nowPt.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday)
            return null;
        const int peakStart = 5;
        const int peakEnd = 11; // exclusive
        if (nowPt.Hour < peakStart || nowPt.Hour >= peakEnd)
            return null;

        DateTimeOffset AtPtHour(int hour)
        {
            var local = new DateTime(nowPt.Year, nowPt.Month, nowPt.Day, hour, 0, 0, DateTimeKind.Unspecified);
            return new DateTimeOffset(local, peakTz.GetUtcOffset(local));
        }
        var startLocal = AtPtHour(peakStart).ToLocalTime();
        var endLocal = AtPtHour(peakEnd).ToLocalTime();
        return ($"{startLocal:HH\\:mm}", $"{endLocal:HH\\:mm}");
    }

    private void RefreshPeakBanner()
    {
        if (_minimized)
            return;
        var window = PeakHourWindowLocal();
        if (window is null)
        {
            _peakBanner.Visibility = Visibility.Collapsed;
        }
        else
        {
            _peakBanner.Text = I18n.Tr("widget.peak_banner",
                ("start", window.Value.Start), ("end", window.Value.End));
            _peakBanner.Visibility = Visibility.Visible;
        }
    }

    // ── State updates (always called on the dispatcher thread) ───────────────

    private void ApplyData(UsageData data)
    {
        _lastData = data;
        _lastError = null;
        var session = data.SessionPercent;
        var weekly = FindWeekly(data);

        SetMetric(_sessionPct, _sessionTrack, _sessionFill, session);
        SetMetric(_weeklyPct, _weeklyTrack, _weeklyFill, weekly);

        var li = data.Limits.FirstOrDefault(l => l.Key == "five_hour");
        string status;
        if (li is null)
        {
            status = I18n.Tr("widget.status.active");
        }
        else if (li.ResetsInSeconds <= 0)
        {
            // The 5 h window has ended; claude.ai starts a new one only with
            // the first token use, so there is no countdown to show.
            status = I18n.Tr("widget.status.waiting_first_message");
        }
        else
        {
            status = I18n.Tr("widget.status.reset_in", ("countdown", li.ResetCountdown));
        }
        _footerText.Text = status;
        _footerText.ToolTip = null;
        SetDotColor(ResetColor(li));
        RefreshPeakBanner();
    }

    private void ApplyError(string message)
    {
        _lastError = message;
        SetMetric(_sessionPct, _sessionTrack, _sessionFill, null);
        SetMetric(_weeklyPct, _weeklyTrack, _weeklyFill, null);

        _footerText.Text = I18n.Tr(ClassifyErrorKey(message));
        _footerText.ToolTip = message + "\n\n" + I18n.Tr("widget.tooltip.log", ("path", AppPaths.LogFilePath));
        SetDotColor(Alert);
        RefreshPeakBanner();
    }

    /// <summary>Map a raw error text to the i18n key of the short footer hint.
    /// The keyword matching runs against the raw (deliberately untranslated,
    /// English) exception texts — only the short text shown is localised.</summary>
    internal static string ClassifyErrorKey(string message)
    {
        var lc = message.ToLowerInvariant();
        if (lc.Contains("expired") || lc.Contains("401"))
            return "widget.error.session_expired";
        if (lc.Contains("403") || lc.Contains("cloudflare"))
            return "widget.error.cloudflare";
        if (lc.Contains("cookie") || lc.Contains("firefox") || lc.Contains("log in"))
            return "widget.error.login";
        if (lc.Contains("429") || lc.Contains("rate"))
            return "widget.error.rate_limited";
        if (lc.Contains("network") || lc.Contains("connect") || lc.Contains("timeout"))
            return "widget.error.network";
        return "widget.error.generic";
    }

    private void SetMetric(TextBlock pctLabel, Border track, Border fill, int? pct)
    {
        if (pct is null)
        {
            pctLabel.Text = "—";
            pctLabel.Foreground = Solid(Alert);
            SetBar(track, fill, 0, Ok);
        }
        else
        {
            var color = PctColor(pct.Value);
            pctLabel.Text = $"{pct}%";
            pctLabel.Foreground = Solid(color);
            SetBar(track, fill, pct.Value, color);
        }
    }

    private void SetBar(Border track, Border fill, int pct, Color color)
    {
        fill.Tag = pct; // remember for width recalculation on resize
        fill.Background = BarGradient(color);
        ApplyBarWidth(track, fill, animate: true);
    }

    private void ApplyBarWidth(Border track, Border fill, bool animate = false)
    {
        var pct = fill.Tag is int p ? p : 0;
        var trackWidth = track.ActualWidth > 1 ? track.ActualWidth : Width - 36;
        var target = Math.Max(0, trackWidth * Math.Min(pct, 100) / 100.0);
        if (animate && fill.IsLoaded)
        {
            // Ease the fill to its new value so a poll update glides instead of
            // snapping — cheap polish the tkinter variant couldn't do.
            var anim = new DoubleAnimation(target, TimeSpan.FromMilliseconds(320))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut },
            };
            fill.BeginAnimation(WidthProperty, anim);
        }
        else
        {
            // Layout changes (resize) must be instant, not animated.
            fill.BeginAnimation(WidthProperty, null); // release any running animation's hold
            fill.Width = target;
        }
    }

    private void UpdateBarWidths()
    {
        ApplyBarWidth(_sessionTrack, _sessionFill);
        ApplyBarWidth(_weeklyTrack, _weeklyFill);
    }

    private void SetDotColor(Color color)
    {
        _dotGlow.Fill = Glow(color);
        _dotCore.Fill = Solid(color);
    }

    /// <summary>Worst-case weekly utilization across all known weekly buckets.
    /// On Max plans the API exposes multiple model-specific weekly buckets;
    /// returning just the first could under-report.</summary>
    internal static int? FindWeekly(UsageData data)
    {
        var weekly = data.Limits.Where(li => WeeklyKeys.Contains(li.Key)).Select(li => li.Percent).ToList();
        if (weekly.Count > 0)
            return weekly.Max();
        var nonSession = data.Limits.Where(li => li.Key != "five_hour").Select(li => li.Percent).ToList();
        return nonSession.Count > 0 ? nonSession.Max() : null;
    }

    private void Minimize()
    {
        Hide();
        _minimized = true;
        SavePosition();
    }

    // ── Position persistence ─────────────────────────────────────────────────

    private void RestorePosition()
    {
        var x = SystemParameters.VirtualScreenLeft + SystemParameters.VirtualScreenWidth - DefaultWidth - 16;
        var y = 16.0;
        var w = DefaultWidth;
        double? bottom = null;
        var posFile = AppPaths.WidgetPosFilePath;
        if (File.Exists(posFile))
        {
            try
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(posFile));
                var root = doc.RootElement;
                if (root.TryGetProperty("x", out var xEl))
                    x = xEl.GetDouble();
                if (root.TryGetProperty("w", out var wEl))
                    w = Math.Max(MinWidgetWidth, wEl.GetDouble());
                if (root.TryGetProperty("minimized", out var minEl))
                    _minimized = minEl.GetBoolean();
                // Preferred: the height-invariant bottom-edge anchor. Legacy
                // files only stored the top ("y"); treat it as a provisional top
                // and let first layout derive the anchor from it.
                if (root.TryGetProperty("bottom", out var bEl))
                    bottom = bEl.GetDouble();
                else if (root.TryGetProperty("y", out var yEl))
                    y = yEl.GetDouble();
            }
            catch (Exception)
            {
                // Corrupt file → defaults.
            }
        }
        // Saved coords may point at a monitor that no longer exists — clamp
        // into the virtual desktop so the widget is never unreachable.
        var vx = SystemParameters.VirtualScreenLeft;
        var vy = SystemParameters.VirtualScreenTop;
        var vw = SystemParameters.VirtualScreenWidth;
        var vh = SystemParameters.VirtualScreenHeight;
        if (vw > 0 && vh > 0)
        {
            x = Math.Max(vx, Math.Min(x, vx + vw - 60));
            y = Math.Max(vy, Math.Min(y, vy + vh - 40));
            if (bottom is double bv)
                bottom = WidgetGeometry.ClampBottom(bv, vy, vh);
        }
        _pendingBottom = bottom;
        Left = x;
        Top = y;
        Width = w;
    }

    private void SavePosition()
    {
        try
        {
            Directory.CreateDirectory(AppPaths.ConfigDir);
            // Persist the bottom-edge anchor (height-invariant) once it exists,
            // so restarting during peak hours cannot bake the banner height into
            // the saved position. Before first layout, fall back to the legacy
            // top so we never write a bogus zero anchor.
            object payload = _anchorReady
                ? new { x = Left, bottom = _bottomAnchor, w = Width, minimized = _minimized }
                : new { x = Left, y = Top, w = Width, minimized = _minimized };
            File.WriteAllText(AppPaths.WidgetPosFilePath, JsonSerializer.Serialize(payload));
        }
        catch (Exception)
        {
            // Best-effort — persistence failing must never crash the widget.
        }
    }

    // ── Update dialog ────────────────────────────────────────────────────────

    private void ShowUpdateDialog(UpdateInfo info, string versionFloor, Action? onSkip)
    {
        if (_updateWindow is not null)
            return;
        var latestVersion = info.LatestVersion;
        var url = info.Url;

        var card = new StackPanel { Margin = new Thickness(22, 18, 22, 18) };

        // Branded header: app logo + name, so it is unmistakably *this* app
        // that is reporting the update.
        var header = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 14) };
        try
        {
            var logo = new System.Windows.Controls.Image
            {
                Source = new System.Windows.Media.Imaging.BitmapImage(
                    new Uri("pack://application:,,,/Assets/logo.png")),
                Width = 48,
                Height = 48,
                Margin = new Thickness(0, 0, 12, 0),
            };
            header.Children.Add(logo);
        }
        catch (Exception)
        {
            // A missing/corrupt asset must never block the update dialog.
        }
        var brand = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        brand.Children.Add(new TextBlock
        {
            Text = "Claude Usage Tracker",
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 13.5,
            FontWeight = FontWeights.Bold,
            Foreground = Solid(TextColor),
        });
        brand.Children.Add(new TextBlock
        {
            Text = I18n.Tr("update.available"),
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 11,
            Foreground = Solid(Ok),
            Margin = new Thickness(0, 2, 0, 0),
        });
        header.Children.Add(brand);
        card.Children.Add(header);

        card.Children.Add(new Border { Height = 1, Background = Solid(BorderC), Margin = new Thickness(0, 0, 0, 14) });

        card.Children.Add(new TextBlock
        {
            Text = I18n.Tr("update.version_available", ("version", latestVersion)),
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 13.5,
            FontWeight = FontWeights.Bold,
            Foreground = Solid(TextColor),
        });
        card.Children.Add(new TextBlock
        {
            Text = I18n.Tr("update.running_version", ("version", UpdateCheck.CurrentVersion)),
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 11,
            Foreground = Solid(Dim),
            Margin = new Thickness(0, 4, 0, 14),
        });

        var win = new Window
        {
            Title = I18n.Tr("update.window_title"),
            Background = Solid(Bg),
            SizeToContent = SizeToContent.WidthAndHeight,
            ResizeMode = ResizeMode.NoResize,
            Topmost = true,
            WindowStartupLocation = WindowStartupLocation.CenterScreen,
            Content = card,
        };
        _updateWindow = win;
        win.Closed += (_, _) => _updateWindow = null;

        void CloseDialog() => win.Close();

        // Progress/error line for the in-app installer; hidden until used.
        var statusText = new TextBlock
        {
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 11,
            TextWrapping = TextWrapping.Wrap,
            Foreground = Solid(Dim),
            Margin = new Thickness(0, 0, 0, 10),
            Visibility = Visibility.Collapsed,
            MaxWidth = 300,
        };
        card.Children.Add(statusText);

        var buttonRow = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
        };
        Button MakeDialogButton(string text, Action onClick)
        {
            var button = MakeFooterButton(text, onClick);
            button.FontSize = 12;
            button.Padding = new Thickness(12, 4, 12, 4);
            button.Margin = new Thickness(8, 0, 0, 0);
            return button;
        }
        void OpenGithub()
        {
            try
            {
                System.Diagnostics.Process.Start(
                    new System.Diagnostics.ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch (Exception exc)
            {
                Log.Warning("widget", $"Could not open release page: {exc.Message}");
            }
        }

        // Windows button order: [primary] [secondary] [cancel].
#if INSTALLER_UPDATER
        // Installed build: offer verified download-and-install. The bytes are
        // signature- and hash-checked (UpdateInstaller) before anything runs;
        // on success the app quits so the installer can replace it in place and
        // the new version relaunches.
        Button? installButton = null;
        void StartInstall()
        {
            installButton!.IsEnabled = false;
            statusText.Visibility = Visibility.Visible;
            statusText.Text = I18n.Tr("update.downloading");
            System.Threading.Tasks.Task.Run(() =>
            {
                var outcome = UpdateInstaller.Run(info, versionFloor, stage =>
                    Post(() => statusText.Text = stage switch
                    {
                        UpdateStage.Downloading => I18n.Tr("update.downloading"),
                        UpdateStage.Verifying => I18n.Tr("update.verifying"),
                        UpdateStage.Installing => I18n.Tr("update.installing"),
                        _ => statusText.Text,
                    }));
                Post(() =>
                {
                    if (outcome.Started)
                    {
                        statusText.Text = I18n.Tr("update.installing");
                        // The visible installer wizard is now on screen; quit so
                        // the in-use EXE unlocks. The installer relaunches the new
                        // version from its Finish page ([Run] postinstall).
                        _onQuit();
                    }
                    else
                    {
                        statusText.Foreground = Solid(Alert);
                        statusText.Text = I18n.Tr("update.failed");
                    }
                });
            });
        }
        installButton = MakeDialogButton(I18n.Tr("update.download_install"), StartInstall);
        buttonRow.Children.Add(installButton);
        buttonRow.Children.Add(MakeDialogButton(I18n.Tr("update.open_github"), () => { OpenGithub(); CloseDialog(); }));
#else
        buttonRow.Children.Add(MakeDialogButton(I18n.Tr("update.open_github"), () => { OpenGithub(); CloseDialog(); }));
#endif
        if (onSkip is not null)
        {
            buttonRow.Children.Add(MakeDialogButton(I18n.Tr("update.skip"), () =>
            {
                onSkip();
                CloseDialog();
            }));
        }
        buttonRow.Children.Add(MakeDialogButton(I18n.Tr("update.cancel"), CloseDialog));
        card.Children.Add(buttonRow);

        win.KeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape)
                CloseDialog();
        };
        win.Show();
    }
}
