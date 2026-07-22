// Settings dialog — a native editor over config.toml.
//
// Everything the config file exposes is editable here, so a normal user never
// has to hand-edit TOML (the one "developer hurdle" of the Python variant).
// The window is built in code (no XAML) to match the widget's layout style and
// keep the whole dialog in one file. On save it writes the same TOML the file
// has always used, then hands the fresh Config back so the app can apply what
// can change live (poll interval, thresholds, autostart, log level).

using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Documents;
using System.Windows.Media;
using Binding = System.Windows.Data.Binding;
using Button = System.Windows.Controls.Button;
using Color = System.Windows.Media.Color;
using Orientation = System.Windows.Controls.Orientation;

namespace ClaudeUsageTracker;

/// <summary>Display label + persisted value for a ComboBox entry. Public so WPF
/// data binding / ContentPresenter can reflect over it; the ContentPresenter
/// renders the item via ToString (no DataTemplate), which returns the label.</summary>
public sealed record ComboEntry(string Display, string Value)
{
    public override string ToString() => Display;
}

public sealed class SettingsWindow : Window
{
    // Palette shared with the widget for a consistent look.
    private static readonly Color Bg = FromHex("#16161c");
    private static readonly Color Card = FromHex("#1c1c24");
    private static readonly Color TextColor = FromHex("#ececf2");
    private static readonly Color Dim = FromHex("#9494a0");
    private static readonly Color BorderC = FromHex("#2e2e38");
    private static readonly Color FieldBg = FromHex("#101014");
    private static readonly Color Accent = FromHex("#c96442");
    private static readonly Color Alert = FromHex("#ef4444");

    private readonly Config _config;
    private readonly Action<Config> _onApplied;
    private readonly Action _onCheckForUpdates;

    private readonly TextBox _pollInterval;
    private readonly TextBox _thresholds;
    private readonly ComboBox _language;
    private readonly CheckBox _autostart;
    private readonly CheckBox _updateCheck;
    private readonly TextBox _userAgent;
    private readonly TextBox _firefoxProfile;
    private readonly ComboBox _logLevel;
    private readonly TextBlock _error;

    public SettingsWindow(Config config, Action<Config> onApplied, Action onCheckForUpdates)
    {
        _config = config;
        _onApplied = onApplied;
        _onCheckForUpdates = onCheckForUpdates;

        Title = I18n.Tr("settings.title");
        Background = Solid(Bg);
        SizeToContent = SizeToContent.Height;
        Width = 440;
        ResizeMode = ResizeMode.NoResize;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        ShowInTaskbar = true;
        try
        {
            Icon = new System.Windows.Media.Imaging.BitmapImage(
                new Uri("pack://application:,,,/Assets/logo.png"));
        }
        catch (Exception)
        {
            // A missing icon must never block the dialog.
        }

        var root = new StackPanel { Margin = new Thickness(20) };

        root.Children.Add(SectionHeader(I18n.Tr("settings.section.general")));
        _pollInterval = NumericField();
        root.Children.Add(LabeledRow(I18n.Tr("settings.poll_interval"), _pollInterval));
        _thresholds = TextField();
        root.Children.Add(LabeledRow(I18n.Tr("settings.thresholds"), _thresholds,
            I18n.Tr("settings.thresholds.hint")));
        _language = LanguageBox();
        root.Children.Add(LabeledRow(I18n.Tr("settings.language"), _language,
            I18n.Tr("settings.language_restart_hint")));
        _autostart = CheckRow(I18n.Tr("settings.autostart"));
        root.Children.Add(_autostart);
        _updateCheck = CheckRow(I18n.Tr("settings.update_check"));
        root.Children.Add(_updateCheck);
        // On-demand check, independent of the once-per-start automatic one and
        // of the checkbox above. A previously "skipped" release still surfaces.
        var checkNow = DialogButton(I18n.Tr("settings.check_updates"), primary: false, () => _onCheckForUpdates());
        checkNow.HorizontalAlignment = HorizontalAlignment.Left;
        checkNow.Margin = new Thickness(0, 8, 0, 0);
        root.Children.Add(checkNow);

        root.Children.Add(SectionHeader(I18n.Tr("settings.section.advanced")));
        _logLevel = LogLevelBox();
        root.Children.Add(LabeledRow(I18n.Tr("settings.log_level"), _logLevel));
        _userAgent = TextField();
        root.Children.Add(LabeledRow(I18n.Tr("settings.user_agent"), _userAgent));
        _firefoxProfile = TextField();
        root.Children.Add(LabeledRow(I18n.Tr("settings.firefox_profile"),
            ProfileRow(_firefoxProfile)));

        _error = new TextBlock
        {
            Foreground = Solid(Alert),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 6, 0, 0),
            Visibility = Visibility.Collapsed,
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 12,
        };
        root.Children.Add(_error);

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(0, 16, 0, 0),
        };
        buttons.Children.Add(DialogButton(I18n.Tr("settings.cancel"), primary: false, Close));
        buttons.Children.Add(DialogButton(I18n.Tr("settings.save"), primary: true, OnSave));
        root.Children.Add(buttons);

        Content = root;
        LoadFromConfig();
    }

    // ── Load / save ──────────────────────────────────────────────────────────

    private void LoadFromConfig()
    {
        _pollInterval.Text = _config.PollIntervalSeconds.ToString(CultureInfo.InvariantCulture);
        _thresholds.Text = string.Join(", ", _config.NotificationThresholds);
        SelectComboValue(_language, string.IsNullOrWhiteSpace(_config.Language) ? "auto" : _config.Language);
        _autostart.IsChecked = _config.Autostart;
        _updateCheck.IsChecked = _config.UpdateCheck;
        SelectComboValue(_logLevel, _config.LogLevel.ToUpperInvariant());
        _userAgent.Text = _config.UserAgent;
        _firefoxProfile.Text = _config.FirefoxProfilePath;
    }

    private void OnSave()
    {
        if (!int.TryParse(_pollInterval.Text.Trim(), out var interval) || interval < 10)
        {
            ShowError(I18n.Tr("settings.invalid_interval"));
            return;
        }
        if (!TryParseThresholds(_thresholds.Text, out var thresholds))
        {
            ShowError(I18n.Tr("settings.invalid_thresholds"));
            return;
        }

        _config.PollIntervalSeconds = interval;
        _config.NotificationThresholds = thresholds;
        _config.Language = SelectedValue(_language);
        _config.Autostart = _autostart.IsChecked == true;
        _config.UpdateCheck = _updateCheck.IsChecked == true;
        _config.LogLevel = SelectedValue(_logLevel);
        _config.UserAgent = _userAgent.Text.Trim();
        _config.FirefoxProfilePath = _firefoxProfile.Text.Trim();

        try
        {
            _config.Save();
        }
        catch (Exception exc)
        {
            ShowError(exc.Message);
            return;
        }

        _onApplied(_config);
        Close();
    }

    internal static bool TryParseThresholds(string text, out List<int> result)
    {
        result = [];
        var parts = text.Split([',', ';', ' '], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length == 0)
            return false;
        foreach (var part in parts)
        {
            if (!int.TryParse(part, out var value) || value < 0 || value > 100)
                return false;
            result.Add(value);
        }
        result = [.. result.Distinct().OrderBy(v => v)];
        return true;
    }

    private void ShowError(string message)
    {
        _error.Text = message;
        _error.Visibility = Visibility.Visible;
    }

    // ── Field factories ──────────────────────────────────────────────────────

    private static Color FromHex(string hex) => (Color)ColorConverter.ConvertFromString(hex);

    private static SolidColorBrush Solid(Color color)
    {
        var brush = new SolidColorBrush(color);
        brush.Freeze();
        return brush;
    }

    private TextBlock SectionHeader(string text) => new()
    {
        Text = text,
        FontFamily = new FontFamily("Segoe UI"),
        FontSize = 12,
        FontWeight = FontWeights.Bold,
        Foreground = Solid(Dim),
        Margin = new Thickness(0, 10, 0, 6),
    };

    private FrameworkElement LabeledRow(string label, FrameworkElement field, string? hint = null)
    {
        var stack = new StackPanel { Margin = new Thickness(0, 6, 0, 0) };
        stack.Children.Add(new TextBlock
        {
            Text = label,
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 12.5,
            Foreground = Solid(TextColor),
            Margin = new Thickness(0, 0, 0, 3),
        });
        stack.Children.Add(field);
        if (hint is not null)
        {
            stack.Children.Add(new TextBlock
            {
                Text = hint,
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = 11,
                Foreground = Solid(Dim),
                Margin = new Thickness(0, 2, 0, 0),
            });
        }
        return stack;
    }

    private TextBox TextField() => new()
    {
        FontFamily = new FontFamily("Segoe UI"),
        FontSize = 12.5,
        Foreground = Solid(TextColor),
        CaretBrush = Solid(TextColor),
        Background = Solid(FieldBg),
        BorderBrush = Solid(BorderC),
        BorderThickness = new Thickness(1),
        Padding = new Thickness(6, 4, 6, 4),
    };

    private TextBox NumericField()
    {
        var box = TextField();
        box.PreviewTextInput += (_, e) => e.Handled = !e.Text.All(char.IsDigit);
        return box;
    }

    private FrameworkElement ProfileRow(TextBox field)
    {
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        Grid.SetColumn(field, 0);
        grid.Children.Add(field);
        var browse = DialogButton(I18n.Tr("settings.browse"), primary: false, () =>
        {
            using var dialog = new System.Windows.Forms.FolderBrowserDialog();
            if (!string.IsNullOrWhiteSpace(field.Text))
                dialog.SelectedPath = field.Text;
            if (dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK)
                field.Text = dialog.SelectedPath;
        });
        browse.Margin = new Thickness(6, 0, 0, 0);
        Grid.SetColumn(browse, 1);
        grid.Children.Add(browse);
        return grid;
    }

    private ComboBox StyledCombo()
    {
        // The stock ComboBox chrome ignores a light Foreground in its closed
        // selection box (the content renders black → invisible on the dark
        // field). A compact custom template we fully control fixes that and
        // keeps the dropdown on-theme. Items are ComboEntry data objects shown
        // via ToString (no DataTemplate needed).
        var combo = new ComboBox
        {
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 12.5,
            Foreground = Solid(TextColor),
            Background = Solid(FieldBg),
            BorderBrush = Solid(BorderC),
            Padding = new Thickness(6, 3, 6, 3),
            Template = BuildComboTemplate(),
        };
        var itemStyle = new Style(typeof(ComboBoxItem));
        itemStyle.Setters.Add(new Setter(ForegroundProperty, Solid(TextColor)));
        itemStyle.Setters.Add(new Setter(BackgroundProperty, Solid(FieldBg)));
        itemStyle.Setters.Add(new Setter(PaddingProperty, new Thickness(8, 4, 8, 4)));
        combo.ItemContainerStyle = itemStyle;
        return combo;
    }

    private ControlTemplate BuildComboTemplate()
    {
        var root = new FrameworkElementFactory(typeof(Grid));

        // Clickable field: a ToggleButton wired to the drop-down open state.
        var toggle = new FrameworkElementFactory(typeof(ToggleButton));
        toggle.SetValue(ToggleButton.BackgroundProperty, Solid(FieldBg));
        toggle.SetValue(ToggleButton.BorderBrushProperty, Solid(BorderC));
        toggle.SetValue(ToggleButton.BorderThicknessProperty, new Thickness(1));
        toggle.SetValue(ToggleButton.FocusableProperty, false);
        toggle.SetBinding(ToggleButton.IsCheckedProperty, new Binding("IsDropDownOpen")
        {
            RelativeSource = System.Windows.Data.RelativeSource.TemplatedParent,
            Mode = System.Windows.Data.BindingMode.TwoWay,
        });
        // Minimal flat toggle chrome (border + a ▾ glyph on the right).
        var toggleTemplate = new FrameworkElementFactory(typeof(Border));
        toggleTemplate.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(ToggleButton.BackgroundProperty));
        toggleTemplate.SetValue(Border.BorderBrushProperty, new TemplateBindingExtension(ToggleButton.BorderBrushProperty));
        toggleTemplate.SetValue(Border.BorderThicknessProperty, new TemplateBindingExtension(ToggleButton.BorderThicknessProperty));
        toggleTemplate.SetValue(Border.CornerRadiusProperty, new CornerRadius(4));
        var arrow = new FrameworkElementFactory(typeof(TextBlock));
        arrow.SetValue(TextBlock.TextProperty, ""); // Segoe MDL2 chevron down
        arrow.SetValue(TextBlock.FontFamilyProperty, new FontFamily("Segoe MDL2 Assets"));
        arrow.SetValue(TextBlock.FontSizeProperty, 8.0);
        arrow.SetValue(TextBlock.ForegroundProperty, Solid(Dim));
        arrow.SetValue(HorizontalAlignmentProperty, HorizontalAlignment.Right);
        arrow.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
        arrow.SetValue(MarginProperty, new Thickness(0, 0, 8, 0));
        toggleTemplate.AppendChild(arrow);
        toggle.SetValue(ToggleButton.TemplateProperty,
            new ControlTemplate(typeof(ToggleButton)) { VisualTree = toggleTemplate });
        root.AppendChild(toggle);

        // Selected item, rendered in the light foreground we control.
        var content = new FrameworkElementFactory(typeof(ContentPresenter));
        content.SetValue(ContentPresenter.ContentProperty, new TemplateBindingExtension(ComboBox.SelectionBoxItemProperty));
        content.SetValue(TextElement.ForegroundProperty, Solid(TextColor));
        content.SetValue(MarginProperty, new Thickness(8, 4, 22, 4));
        content.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
        content.SetValue(IsHitTestVisibleProperty, false);
        root.AppendChild(content);

        // Drop-down list.
        var popup = new FrameworkElementFactory(typeof(Popup));
        popup.Name = "PART_Popup";
        popup.SetValue(Popup.AllowsTransparencyProperty, true);
        popup.SetValue(Popup.PlacementProperty, PlacementMode.Bottom);
        popup.SetBinding(Popup.IsOpenProperty, new Binding("IsDropDownOpen")
        {
            RelativeSource = System.Windows.Data.RelativeSource.TemplatedParent,
        });
        var popupBorder = new FrameworkElementFactory(typeof(Border));
        popupBorder.SetValue(Border.BackgroundProperty, Solid(FieldBg));
        popupBorder.SetValue(Border.BorderBrushProperty, Solid(BorderC));
        popupBorder.SetValue(Border.BorderThicknessProperty, new Thickness(1));
        popupBorder.SetValue(Border.CornerRadiusProperty, new CornerRadius(4));
        popupBorder.SetValue(Border.MarginProperty, new Thickness(0, 2, 0, 0));
        popupBorder.SetBinding(FrameworkElement.MinWidthProperty, new Binding("ActualWidth")
        {
            RelativeSource = System.Windows.Data.RelativeSource.TemplatedParent,
        });
        var scroll = new FrameworkElementFactory(typeof(ScrollViewer));
        var items = new FrameworkElementFactory(typeof(ItemsPresenter));
        scroll.AppendChild(items);
        popupBorder.AppendChild(scroll);
        popup.AppendChild(popupBorder);
        root.AppendChild(popup);

        return new ControlTemplate(typeof(ComboBox)) { VisualTree = root };
    }

    private ComboBox LanguageBox()
    {
        var combo = StyledCombo();
        combo.Items.Add(new ComboEntry(I18n.Tr("settings.language.auto"), "auto"));
        foreach (var code in I18n.AvailableLanguages.OrderBy(c => c))
        {
            string label;
            try
            {
                var native = CultureInfo.GetCultureInfo(code).NativeName;
                label = $"{char.ToUpper(native[0])}{native[1..]} ({code})";
            }
            catch (CultureNotFoundException)
            {
                label = code;
            }
            combo.Items.Add(new ComboEntry(label, code));
        }
        return combo;
    }

    private ComboBox LogLevelBox()
    {
        var combo = StyledCombo();
        foreach (var level in new[] { "DEBUG", "INFO", "WARNING", "ERROR" })
            combo.Items.Add(new ComboEntry(level, level));
        return combo;
    }

    private static string SelectedValue(ComboBox combo) => ((ComboEntry)combo.SelectedItem).Value;

    private static void SelectComboValue(ComboBox combo, string value)
    {
        foreach (ComboEntry entry in combo.Items)
        {
            if (string.Equals(entry.Value, value, StringComparison.OrdinalIgnoreCase))
            {
                combo.SelectedItem = entry;
                return;
            }
        }
        if (combo.Items.Count > 0)
            combo.SelectedIndex = 0;
    }

    private CheckBox CheckRow(string label) => new()
    {
        Content = label,
        FontFamily = new FontFamily("Segoe UI"),
        FontSize = 12.5,
        Foreground = Solid(TextColor),
        Margin = new Thickness(0, 10, 0, 0),
    };

    private Button DialogButton(string text, bool primary, Action onClick)
    {
        var button = new Button
        {
            Content = text,
            FontFamily = new FontFamily("Segoe UI"),
            FontSize = 12.5,
            Foreground = Solid(primary ? Colors.White : TextColor),
            Background = Solid(primary ? Accent : Card),
            BorderBrush = Solid(BorderC),
            BorderThickness = new Thickness(primary ? 0 : 1),
            Padding = new Thickness(16, 6, 16, 6),
            Margin = new Thickness(8, 0, 0, 0),
            Cursor = System.Windows.Input.Cursors.Hand,
        };
        var borderFactory = new FrameworkElementFactory(typeof(Border));
        borderFactory.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(BackgroundProperty));
        borderFactory.SetValue(Border.BorderBrushProperty, new TemplateBindingExtension(BorderBrushProperty));
        borderFactory.SetValue(Border.BorderThicknessProperty, new TemplateBindingExtension(BorderThicknessProperty));
        borderFactory.SetValue(Border.CornerRadiusProperty, new CornerRadius(5));
        borderFactory.SetValue(Border.PaddingProperty, new TemplateBindingExtension(PaddingProperty));
        var content = new FrameworkElementFactory(typeof(ContentPresenter));
        content.SetValue(HorizontalAlignmentProperty, HorizontalAlignment.Center);
        content.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
        borderFactory.AppendChild(content);
        button.Template = new ControlTemplate(typeof(Button)) { VisualTree = borderFactory };
        button.Click += (_, _) => onClick();
        return button;
    }
}
