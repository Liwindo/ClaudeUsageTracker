// The update dialog: the offered versions on the left, the selected version's
// release notes on the right (REQUIREMENTS.md R-life-6 / R-life-7).
//
// Layout and colours match python/src/claude_usage_monitor/update_dialog.py;
// only the corners differ (tkinter cannot round them). The window is
// resizable, but its size is never remembered.
//
// The release notes are untrusted text (R-net-8): they become plain Runs with
// a bold weight at most, nothing in them is clickable or editable. The only
// ways out of the dialog stay "Open GitHub" (URL validated in UpdateCheck,
// R-net-7) and, in the installer build, the signature-checked install.

using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;
using Button = System.Windows.Controls.Button;
using Color = System.Windows.Media.Color;
using static ClaudeUsageTracker.WidgetWindow;

namespace ClaudeUsageTracker;

internal sealed class UpdateDialog : Window
{
    // Same values as widget.py's update-dialog tokens.
    private static readonly Color Sidebar = FromHex("#121217");
    private static readonly Color Divider = FromHex("#24242c");
    private static readonly Color Body = FromHex("#b4b4c0");
    private static readonly Color RowHov = FromHex("#1a1a21");
    private static readonly Color ChipBg = FromHex("#15291d");
    private static readonly Color OnOk = FromHex("#0b1a10");
    private static readonly Color OkHov = FromHex("#16a34a");
    private static readonly Color InfoBg = FromHex("#1c1c23");

    // Default size; the user may resize, the size is not stored.
    private const double DefaultWidth = 700;
    private const double DefaultHeight = 470;
    private const double MinW = 560;
    private const double MinH = 360;
    private const double SidebarWidth = 220;
    private const double Pad = 26;

    // DWMWA_USE_IMMERSIVE_DARK_MODE: 20 from Windows 10 20H1 on, 19 before that.
    private static readonly int[] DwmDarkModeAttrs = [20, 19];

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    private static readonly FontFamily Segoe = new("Segoe UI");

    private readonly UpdateInfo _info;
    private readonly string _latest;
    private readonly ReleaseNotes? _notes;
    private readonly List<Button> _rows = [];
    private readonly TextBlock _title = new() { FontSize = 20, FontWeight = FontWeights.Bold, Foreground = Solid(TextColor) };
    private readonly Border _chip;
    private readonly StackPanel _notesPanel = new() { Margin = new Thickness(0, 0, 12, 10) };
    private readonly ScrollViewer _notesScroll;
    private readonly FrameworkElement _sidebar;
    private int _selected;

    public UpdateDialog(UpdateInfo info, string versionFloor, Action? onSkip, Action onQuit)
    {
        _info = info;
        _latest = info.LatestVersion;
        _notes = info.Notes;

        Title = I18n.Tr("update.window_title");
        Background = Solid(Bg);
        FontFamily = Segoe;
        Width = DefaultWidth;
        Height = DefaultHeight;
        MinWidth = MinW;
        MinHeight = MinH;
        ResizeMode = ResizeMode.CanResize;
        Topmost = true;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        try
        {
            Icon = BitmapFrame.Create(new Uri("pack://application:,,,/Assets/logo_tile.ico"));
        }
        catch (Exception)
        {
            // A missing/corrupt asset must never block the update dialog.
        }

        _chip = new Border
        {
            Background = Solid(ChipBg),
            CornerRadius = new CornerRadius(10),
            Padding = new Thickness(8, 2, 8, 2),
            Margin = new Thickness(10, 3, 0, 0),
            VerticalAlignment = VerticalAlignment.Center,
            Child = new TextBlock
            {
                Text = I18n.Tr("update.latest"),
                FontSize = 11,
                FontWeight = FontWeights.SemiBold,
                Foreground = Solid(Ok),
            },
        };
        _notesScroll = new ScrollViewer
        {
            Content = _notesPanel,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            Focusable = false,
            Margin = new Thickness(Pad, 0, 8, 0),
        };
        _notesScroll.Resources[typeof(ScrollBar)] = DarkScrollBarStyle();

        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(SidebarWidth) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        _sidebar = BuildSidebar(onSkip);
        grid.Children.Add(_sidebar);
        var divider = new Border { Background = Solid(Divider) };
        Grid.SetColumn(divider, 1);
        grid.Children.Add(divider);
        var main = BuildMain(versionFloor, onQuit);
        Grid.SetColumn(main, 2);
        grid.Children.Add(main);
        Content = grid;

        SourceInitialized += (_, _) => UseDarkTitleBar();
        Loaded += (_, _) => FitSidebar();
        KeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape)
                Close();
            else if (e.Key == Key.Up)
                Select(_selected - 1);
            else if (e.Key == Key.Down)
                Select(_selected + 1);
        };
        if (_notes is not null)
            Select(0);
    }

    // ── Building ─────────────────────────────────────────────────────────────

    private static TextBlock Text(string text, double size, Color color, FontWeight? weight = null) => new()
    {
        Text = text,
        FontSize = size,
        Foreground = Solid(color),
        FontWeight = weight ?? FontWeights.Normal,
        TextWrapping = TextWrapping.Wrap,
    };

    private FrameworkElement BuildSidebar(Action? onSkip)
    {
        var dock = new DockPanel { Background = Solid(Sidebar), LastChildFill = true };
        if (onSkip is not null)
        {
            var skip = MakeLinkButton(I18n.Tr("update.skip"), () =>
            {
                onSkip();
                Close();
            });
            DockPanel.SetDock(skip, Dock.Bottom);
            dock.Children.Add(skip);
        }

        var stack = new StackPanel { Margin = new Thickness(12, 20, 12, 8) };
        var header = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(6, 0, 6, 0) };
        try
        {
            header.Children.Add(new Image
            {
                Source = new BitmapImage(new Uri("pack://application:,,,/Assets/logo_tile.png")),
                Width = 36,
                Height = 36,
                Margin = new Thickness(0, 0, 10, 0),
            });
        }
        catch (Exception)
        {
            // A missing/corrupt asset must never block the update dialog.
        }
        var brand = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        brand.Children.Add(Text("Claude Usage Tracker", 13.5, TextColor, FontWeights.Bold));
        brand.Children.Add(Text(I18n.Tr("update.available"), 11, Ok));
        header.Children.Add(brand);
        stack.Children.Add(header);

        var jump = Text($"{UpdateCheck.CurrentVersion} → {_latest}", 12, Dim);
        jump.Margin = new Thickness(6, 12, 6, 0);
        stack.Children.Add(jump);

        if (_notes is not null)
        {
            var label = Text(I18n.Tr("update.versions").ToUpperInvariant(), 11, Dim, FontWeights.SemiBold);
            label.Margin = new Thickness(6, 18, 6, 6);
            stack.Children.Add(label);
            for (var i = 0; i < _notes.Versions.Count; i++)
            {
                var index = i;
                var row = MakeRow(_notes.Versions[i].Version, () => Select(index));
                _rows.Add(row);
                stack.Children.Add(row);
            }
            if (_notes.Truncated)
            {
                var more = Text(I18n.Tr("update.notes_more"), 11, Dim);
                more.Margin = new Thickness(10, 8, 10, 0);
                stack.Children.Add(more);
            }
        }

        stack.Children.Add(new Border
        {
            Height = 1,
            Background = Solid(Divider),
            Margin = new Thickness(10, _notes is not null ? 10 : 18, 10, 4),
        });
        var installed = new DockPanel { Margin = new Thickness(10, 4, 10, 0) };
        var installedLabel = Text(I18n.Tr("update.installed"), 11, Dim);
        installedLabel.VerticalAlignment = VerticalAlignment.Center;
        DockPanel.SetDock(installedLabel, Dock.Right);
        installed.Children.Add(installedLabel);
        installed.Children.Add(Text(UpdateCheck.CurrentVersion, 12, Dim));
        stack.Children.Add(installed);

        dock.Children.Add(stack);
        return dock;
    }

    private Grid BuildMain(string versionFloor, Action onQuit)
    {
        var main = new Grid();
        main.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        main.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        main.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1) });
        main.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        var head = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(Pad, 20, Pad, 8) };
        head.Children.Add(_title);
        head.Children.Add(_chip);
        main.Children.Add(head);

        FrameworkElement body;
        if (_notes is not null)
        {
            body = _notesScroll;
        }
        else
        {
            _title.Text = I18n.Tr("update.notes_version", ("version", _latest));
            body = BuildUnavailable();
        }
        Grid.SetRow(body, 1);
        main.Children.Add(body);

        var line = new Border { Background = Solid(Divider) };
        Grid.SetRow(line, 2);
        main.Children.Add(line);

        var foot = new StackPanel { Margin = new Thickness(Pad, 14, Pad, 16) };
        Grid.SetRow(foot, 3);
        main.Children.Add(foot);

        // Progress/error line for the in-app installer; hidden until used.
        var status = Text("", 12, Body);
        status.Margin = new Thickness(0, 0, 0, 10);
        status.Visibility = Visibility.Collapsed;
        foot.Children.Add(status);

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        foot.Children.Add(buttons);
        buttons.Children.Add(MakeButton(I18n.Tr("update.cancel"), primary: false, Close));
#if INSTALLER_UPDATER
        // Installed build: verified download-and-install is the primary action.
        // The bytes are signature- and hash-checked (UpdateInstaller) before
        // anything runs; on success the app quits so the installer can replace
        // it in place and the new version relaunches.
        buttons.Children.Add(MakeButton(I18n.Tr("update.open_github"), primary: false, () => { OpenGithub(); Close(); }));
        Button? install = null;
        install = MakeButton(I18n.Tr("update.download_install"), primary: true, () =>
        {
            install!.IsEnabled = false;
            status.Visibility = Visibility.Visible;
            status.Foreground = Solid(Body);
            status.Text = I18n.Tr("update.downloading");
            System.Threading.Tasks.Task.Run(() =>
            {
                var outcome = UpdateInstaller.Run(_info, versionFloor, stage =>
                    Post(() => status.Text = stage switch
                    {
                        UpdateStage.Downloading => I18n.Tr("update.downloading"),
                        UpdateStage.Verifying => I18n.Tr("update.verifying"),
                        UpdateStage.Installing => I18n.Tr("update.installing"),
                        _ => status.Text,
                    }));
                Post(() =>
                {
                    if (outcome.Started)
                    {
                        status.Text = I18n.Tr("update.installing");
                        // The visible installer wizard is now on screen; quit so
                        // the in-use EXE unlocks. The installer relaunches the new
                        // version from its Finish page ([Run] postinstall).
                        onQuit();
                    }
                    else
                    {
                        status.Foreground = Solid(Alert);
                        status.Text = I18n.Tr("update.failed");
                        install.IsEnabled = true;
                    }
                });
            });
        });
        buttons.Children.Add(install);
#else
        _ = versionFloor;
        _ = onQuit;
        _ = status;
        buttons.Children.Add(MakeButton(I18n.Tr("update.open_github"), primary: true, () => { OpenGithub(); Close(); }));
#endif
        return main;
    }

    private Border BuildUnavailable()
    {
        var icon = new Canvas { Width = 18, Height = 18, Margin = new Thickness(0, 1, 12, 0), VerticalAlignment = VerticalAlignment.Top };
        icon.Children.Add(new Ellipse { Width = 14.5, Height = 14.5, Stroke = Solid(Dim), StrokeThickness = 1.5, Margin = new Thickness(1.75) });
        icon.Children.Add(new Line { X1 = 9, Y1 = 8, X2 = 9, Y2 = 12.5, Stroke = Solid(Dim), StrokeThickness = 1.5, StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round });
        var dot = new Ellipse { Width = 1.8, Height = 1.8, Fill = Solid(Dim) };
        Canvas.SetLeft(dot, 8.1);
        Canvas.SetTop(dot, 4.7);
        icon.Children.Add(dot);
        var row = new DockPanel();
        DockPanel.SetDock(icon, Dock.Left);
        row.Children.Add(icon);
        row.Children.Add(Text(I18n.Tr("update.notes_unavailable"), 12, Body));
        return new Border
        {
            Background = Solid(InfoBg),
            CornerRadius = new CornerRadius(6),
            Padding = new Thickness(16, 14, 16, 14),
            Margin = new Thickness(Pad, 10, Pad, 0),
            VerticalAlignment = VerticalAlignment.Top,
            Child = row,
        };
    }

    /// <summary>Flat button with a hover colour; WPF's default chrome ignores
    /// Background on hover.</summary>
    private static Button MakeButton(string text, bool primary, Action onClick)
    {
        var (bg, hover, fg) = primary ? (Ok, OkHov, OnOk) : (BtnBg, BtnHov, TextColor);
        var button = new Button
        {
            Content = text,
            FontSize = 12.5,
            FontWeight = primary ? FontWeights.SemiBold : FontWeights.Normal,
            Foreground = Solid(fg),
            Background = Solid(bg),
            Padding = new Thickness(16, 7, 16, 7),
            Margin = new Thickness(8, 0, 0, 0),
            Cursor = Cursors.Hand,
        };
        button.Template = FlatTemplate(new CornerRadius(6), HorizontalAlignment.Center);
        button.MouseEnter += (_, _) => button.Background = Solid(hover);
        button.MouseLeave += (_, _) => button.Background = Solid(bg);
        button.IsEnabledChanged += (_, _) => button.Opacity = button.IsEnabled ? 1 : 0.5;
        button.Click += (_, _) => onClick();
        return button;
    }

    private static Button MakeLinkButton(string text, Action onClick)
    {
        var button = new Button
        {
            Content = text,
            FontSize = 12,
            Foreground = Solid(Dim),
            Background = Brushes.Transparent,
            Padding = new Thickness(22, 8, 12, 14),
            Cursor = Cursors.Hand,
            HorizontalAlignment = HorizontalAlignment.Stretch,
            Template = FlatTemplate(new CornerRadius(0), HorizontalAlignment.Left),
        };
        button.MouseEnter += (_, _) => button.Foreground = Solid(TextColor);
        button.MouseLeave += (_, _) => button.Foreground = Solid(Dim);
        button.Click += (_, _) => onClick();
        return button;
    }

    private Button MakeRow(string version, Action onClick)
    {
        var button = new Button
        {
            Content = version,
            FontSize = 12.5,
            FontWeight = FontWeights.SemiBold,
            Padding = new Thickness(10, 7, 10, 7),
            Margin = new Thickness(0, 0, 0, 2),
            Cursor = Cursors.Hand,
            Focusable = false,
            HorizontalAlignment = HorizontalAlignment.Stretch,
            Template = FlatTemplate(new CornerRadius(6), HorizontalAlignment.Left),
        };
        button.MouseEnter += (_, _) => PaintRows(hovered: button);
        button.MouseLeave += (_, _) => PaintRows(hovered: null);
        button.Click += (_, _) => onClick();
        return button;
    }

    private static ControlTemplate FlatTemplate(CornerRadius radius, HorizontalAlignment content)
    {
        var border = new FrameworkElementFactory(typeof(Border));
        border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(BackgroundProperty));
        border.SetValue(Border.CornerRadiusProperty, radius);
        border.SetValue(Border.PaddingProperty, new TemplateBindingExtension(PaddingProperty));
        var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
        presenter.SetValue(HorizontalAlignmentProperty, content);
        presenter.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
        border.AppendChild(presenter);
        return new ControlTemplate(typeof(Button)) { VisualTree = border };
    }

    /// <summary>Slim dark scrollbar: the default Aero one is light grey.</summary>
    private static Style DarkScrollBarStyle() => (Style)XamlReader.Parse("""
        <Style xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
               xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
               TargetType="ScrollBar">
          <Setter Property="Width" Value="8"/>
          <Setter Property="MinWidth" Value="8"/>
          <Setter Property="Template">
            <Setter.Value>
              <ControlTemplate TargetType="ScrollBar">
                <Track x:Name="PART_Track" IsDirectionReversed="True">
                  <Track.DecreaseRepeatButton>
                    <RepeatButton Command="ScrollBar.PageUpCommand" Opacity="0" Focusable="False"/>
                  </Track.DecreaseRepeatButton>
                  <Track.IncreaseRepeatButton>
                    <RepeatButton Command="ScrollBar.PageDownCommand" Opacity="0" Focusable="False"/>
                  </Track.IncreaseRepeatButton>
                  <Track.Thumb>
                    <Thumb>
                      <Thumb.Template>
                        <ControlTemplate TargetType="Thumb">
                          <Border x:Name="Bar" CornerRadius="4" Background="#34343e"/>
                          <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                              <Setter TargetName="Bar" Property="Background" Value="#4a4a58"/>
                            </Trigger>
                            <Trigger Property="IsDragging" Value="True">
                              <Setter TargetName="Bar" Property="Background" Value="#4a4a58"/>
                            </Trigger>
                          </ControlTemplate.Triggers>
                        </ControlTemplate>
                      </Thumb.Template>
                    </Thumb>
                  </Track.Thumb>
                </Track>
              </ControlTemplate>
            </Setter.Value>
          </Setter>
        </Style>
        """);

    // ── Behaviour ────────────────────────────────────────────────────────────

    // Read-only views for UpdateDialogTests.
    internal IReadOnlyList<string> RowLabels => [.. _rows.Select(r => (string)r.Content)];
    internal int SelectedIndex => _selected;
    internal string TitleText => _title.Text;
    internal bool ChipVisible => _chip.Visibility == Visibility.Visible;
    internal string NotesText => string.Join("\n", Descendants(_notesPanel).OfType<TextBlock>()
        .Select(tb => string.Concat(tb.Inlines.OfType<System.Windows.Documents.Run>().Select(r => r.Text)) is { Length: > 0 } runs ? runs : tb.Text));

    private static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        foreach (var child in LogicalTreeHelper.GetChildren(root).OfType<DependencyObject>())
        {
            yield return child;
            foreach (var grandchild in Descendants(child))
                yield return grandchild;
        }
    }

    /// <summary>Every piece of text in the dialog, for tests.</summary>
    internal IEnumerable<string> AllTexts => Descendants(this).Select(d => d switch
    {
        TextBlock tb => tb.Text,
        Button b => b.Content as string ?? "",
        _ => "",
    }).Where(t => t.Length > 0);

    /// <summary>Show the notes of the index-th offered version (clamped).</summary>
    internal void Select(int index)
    {
        if (_notes is null)
            return;
        index = Math.Clamp(index, 0, _notes.Versions.Count - 1);
        _selected = index;
        var version = _notes.Versions[index];
        _title.Text = I18n.Tr("update.notes_version", ("version", version.Version));
        _chip.Visibility = version.Version == _latest ? Visibility.Visible : Visibility.Collapsed;
        PaintRows(hovered: null);
        Render(version);
    }

    private void PaintRows(Button? hovered)
    {
        for (var i = 0; i < _rows.Count; i++)
        {
            var row = _rows[i];
            // WidgetWindow.Track, not Primitives.Track (the scrollbar part).
            var (bg, fg) = i == _selected ? (WidgetWindow.Track, Ok)
                : row == hovered ? (RowHov, TextColor)
                : (Sidebar, TextColor);
            row.Background = Solid(bg);
            row.Foreground = Solid(fg);
        }
    }

    private static TextBlock NoteLine(IEnumerable<NoteSpan> spans, double size, Color color, bool allBold)
    {
        var tb = new TextBlock
        {
            FontSize = size,
            LineHeight = size * 1.5,
            Foreground = Solid(color),
            TextWrapping = TextWrapping.Wrap,
        };
        foreach (var span in spans)
        {
            var run = new System.Windows.Documents.Run(span.Text);
            if (allBold || span.Bold)
            {
                run.FontWeight = FontWeights.SemiBold;
                run.Foreground = Solid(TextColor);
            }
            tb.Inlines.Add(run);
        }
        return tb;
    }

    private void Render(VersionNotes version)
    {
        _notesPanel.Children.Clear();
        for (var i = 0; i < version.Blocks.Count; i++)
        {
            var block = version.Blocks[i];
            var first = i == 0;
            switch (block.Kind)
            {
                case "heading":
                    var heading = NoteLine(block.Spans, 13.3, TextColor, allBold: true);
                    heading.Margin = new Thickness(0, first ? 2 : 14, 0, 2);
                    _notesPanel.Children.Add(heading);
                    break;
                case "bullet":
                    // Hanging indent: the marker has its own column, so wrapped
                    // lines line up with the text, not the bullet.
                    var row = new Grid { Margin = new Thickness(block.Level * 16, first ? 2 : block.Level == 0 ? 6 : 4, 0, 0) };
                    row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(16) });
                    row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                    row.Children.Add(Text(block.Level == 0 ? "•" : "◦", 12, Ok));
                    var text = NoteLine(block.Spans, 12, Body, allBold: false);
                    Grid.SetColumn(text, 1);
                    row.Children.Add(text);
                    _notesPanel.Children.Add(row);
                    break;
                default:
                    var para = NoteLine(block.Spans, 12, Body, allBold: false);
                    para.Margin = new Thickness(0, first ? 2 : 8, 0, 0);
                    _notesPanel.Children.Add(para);
                    break;
            }
        }
        _notesScroll.ScrollToTop();
    }

    /// <summary>Grow the window when a long version list needs it, like the
    /// Python variant: the sidebar never scrolls.</summary>
    private void FitSidebar()
    {
        _sidebar.Measure(new Size(SidebarWidth, double.PositiveInfinity));
        var chrome = ActualHeight - ((FrameworkElement)Content).ActualHeight;
        var needed = _sidebar.DesiredSize.Height + chrome;
        MinHeight = Math.Max(MinH, needed);
        if (Height < needed)
            Height = needed;
    }

    private void UseDarkTitleBar()
    {
        try
        {
            var hwnd = new WindowInteropHelper(this).Handle;
            var on = 1;
            foreach (var attr in DwmDarkModeAttrs)
            {
                if (DwmSetWindowAttribute(hwnd, attr, ref on, sizeof(int)) == 0)
                    return;
            }
        }
        catch (Exception)
        {
            // Older Windows: keep the light caption.
        }
    }

    private void Post(Action action)
    {
        try
        {
            Dispatcher.BeginInvoke(action);
        }
        catch (Exception)
        {
            // Tolerate shutdown races.
        }
    }

    private void OpenGithub()
    {
        try
        {
            System.Diagnostics.Process.Start(
                new System.Diagnostics.ProcessStartInfo(_info.Url) { UseShellExecute = true });
        }
        catch (Exception exc)
        {
            Log.Warning("widget", $"Could not open release page: {exc.Message}");
        }
    }
}
