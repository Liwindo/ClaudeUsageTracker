// The tray menu's "Release notes" view (REQUIREMENTS.md R-life-8): the update
// dialog in its read-only mode, with every release, the installed one
// selected and no update actions. Mirrors the history tests in
// python/tests/test_update_dialog.py. WPF needs an STA thread.

using System.Runtime.ExceptionServices;
using System.Text.Json;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class ReleaseNotesViewTests
{
    private static ReleaseNotes History(string installed) => ReleaseNotesParser.SelectHistory(
        JsonSerializer.Serialize(new[]
        {
            new { tag_name = "v99.0.0", body = "- Newer than anything" },
            new { tag_name = $"v{installed}", body = "- The installed one" },
            new { tag_name = "v0.0.1", body = "- The first" },
        }))!;

    private static void OnSta(Action test)
    {
        ExceptionDispatchInfo? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                I18n.Init("en");
                test();
            }
            catch (Exception exc)
            {
                failure = ExceptionDispatchInfo.Capture(exc);
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        thread.Join();
        failure?.Throw();
    }

    private static void WithView(ReleaseNotes? notes, Action<UpdateDialog> test) => OnSta(() =>
    {
        var newest = notes?.Versions[0].Version ?? UpdateCheck.CurrentVersion;
        var dialog = new UpdateDialog(new UpdateInfo(newest, UpdateCheck.RepoReleasesListUrl, [], notes),
            "0.0.0", null, () => { }, history: true);
        try
        {
            test(dialog);
        }
        finally
        {
            dialog.Close();
        }
    });

    [Fact]
    public void SelectsTheInstalledVersion() => WithView(History(UpdateCheck.CurrentVersion), d =>
    {
        Assert.Equal(["99.0.0", UpdateCheck.CurrentVersion, "0.0.1"], d.RowLabels);
        Assert.Equal(1, d.SelectedIndex);
        Assert.Equal($"Version {UpdateCheck.CurrentVersion}", d.TitleText);
        Assert.True(d.InstalledChipVisible);
        Assert.False(d.ChipVisible);
        d.Select(0);
        Assert.True(d.ChipVisible);
        Assert.False(d.InstalledChipVisible);
    });

    [Fact]
    public void HasNoUpdateActions() => WithView(History(UpdateCheck.CurrentVersion), d =>
    {
        var texts = d.AllTexts.ToList();
        Assert.Equal("Release notes", d.Title);
        Assert.Contains("Release notes", texts);
        Assert.DoesNotContain("Update available", texts);
        Assert.DoesNotContain(texts, t => t.Contains('→'));
        Assert.DoesNotContain("Skip version", texts);
        Assert.DoesNotContain("Download & install", texts);
        Assert.DoesNotContain("Cancel", texts);
        Assert.Contains("Close", texts);
        Assert.Contains("Open GitHub", texts);
        Assert.Equal("https://github.com/Liwindo/ClaudeUsageTracker/releases", d.Url);
    });

    [Fact]
    public void WithoutTheInstalledVersionStartsAtTheNewest() => WithView(History("0.5.0"), d =>
    {
        Assert.Equal(0, d.SelectedIndex);
        Assert.False(d.InstalledChipVisible);
    });

    [Fact]
    public void UnavailableNotesNameTheRunningVersion() => WithView(null, d =>
    {
        Assert.Empty(d.RowLabels);
        Assert.Equal($"Version {UpdateCheck.CurrentVersion}", d.TitleText);
        Assert.Contains(d.AllTexts, t => t.StartsWith("The release notes could not be loaded", StringComparison.Ordinal));
    });

    [Fact]
    public void WidgetOpensOneViewAtATime() => OnSta(() =>
    {
        var widget = new WidgetWindow(() => { }, () => { }, () => { });
        var first = widget.OpenReleaseNotes(History(UpdateCheck.CurrentVersion));
        try
        {
            Assert.NotNull(first);
            Assert.Null(widget.OpenReleaseNotes(History(UpdateCheck.CurrentVersion)));
        }
        finally
        {
            first?.Close();
            widget.Close();
        }
    });
}
