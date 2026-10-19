// The update dialog (REQUIREMENTS.md R-life-6 / R-life-7): branded, the offered
// versions with the installed one underneath, the selected version's notes, a
// truncated list and unavailable notes. Mirrors python/tests/test_update_dialog.py.
// Looks are checked by screenshot, not here. WPF needs an STA thread, so each
// test builds the (never shown) window on one.

using System.Runtime.ExceptionServices;
using System.Text.Json;
using System.Windows;
using Xunit;

namespace ClaudeUsageTracker.Tests;

public class UpdateDialogTests
{
    private static readonly string Releases = JsonSerializer.Serialize(new[]
    {
        new { tag_name = "v9.2.0", body = "### Fixes\n\n- **Fixed** the thing\n- Second item" },
        new { tag_name = "v9.1.0", body = "- Only in nine one" },
        new { tag_name = "v1.0.0", body = "- Older than anything running" },
    });

    // Selected as if 1.0.0 were running; the dialog itself labels the
    // installed version with the real UpdateCheck.CurrentVersion.
    private static ReleaseNotes? Notes(int max = ReleaseNotesParser.MaxReleases) =>
        ReleaseNotesParser.Select(Releases, "1.0.0", "9.2.0", max);

    private static void OnSta(Action<UpdateDialog> test, ReleaseNotes? notes, Action? onSkip = null)
    {
        ExceptionDispatchInfo? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                I18n.Init("en");
                var info = new UpdateInfo("9.2.0", "https://github.com/x", [], notes);
                var dialog = new UpdateDialog(info, "0.0.0", onSkip, () => { });
                try
                {
                    test(dialog);
                }
                finally
                {
                    dialog.Close();
                }
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

    [Fact]
    public void IsBrandedAndNamesTheVersionJump() => OnSta(d =>
    {
        var texts = d.AllTexts.ToList();
        Assert.Contains("Claude Usage Tracker", texts);
        Assert.Contains("Update available", texts);
        Assert.Contains($"{UpdateCheck.CurrentVersion} → 9.2.0", texts);
    }, Notes());

    [Fact]
    public void ListsOfferedVersionsAndTheInstalledOne() => OnSta(d =>
    {
        Assert.Equal(["9.2.0", "9.1.0"], d.RowLabels);
        var texts = d.AllTexts.ToList();
        Assert.Contains("VERSIONS", texts);
        Assert.Contains("installed", texts);
        Assert.Contains(UpdateCheck.CurrentVersion, texts);
    }, Notes());

    [Fact]
    public void SelectingAVersionShowsItsNotes() => OnSta(d =>
    {
        Assert.Equal("Version 9.2.0", d.TitleText);
        Assert.True(d.ChipVisible);
        Assert.Contains("Fixed the thing", d.NotesText);
        Assert.Contains("Fixes", d.NotesText);

        d.Select(1);
        Assert.Equal("Version 9.1.0", d.TitleText);
        Assert.False(d.ChipVisible);
        Assert.Contains("Only in nine one", d.NotesText);
        Assert.DoesNotContain("Fixed the thing", d.NotesText);
    }, Notes());

    [Fact]
    public void SelectionClampsAtBothEnds() => OnSta(d =>
    {
        d.Select(5);
        Assert.Equal(1, d.SelectedIndex);
        d.Select(-3);
        Assert.Equal(0, d.SelectedIndex);
    }, Notes());

    [Fact]
    public void TruncatedListPointsToGitHub() => OnSta(d =>
    {
        Assert.Single(d.RowLabels);
        Assert.Contains("Older changes are listed on GitHub.", d.AllTexts);
    }, Notes(max: 1));

    [Fact]
    public void UnavailableNotesShowTheHintAndNoList() => OnSta(d =>
    {
        var texts = d.AllTexts.ToList();
        Assert.Empty(d.RowLabels);
        Assert.DoesNotContain("VERSIONS", texts);
        Assert.Contains(texts, t => t.StartsWith("The release notes could not be loaded", StringComparison.Ordinal));
        Assert.Equal("Version 9.2.0", d.TitleText);
        Assert.Contains("installed", texts);
    }, null);

    [Fact]
    public void SkipOnlyWhenOffered()
    {
        OnSta(d => Assert.DoesNotContain("Skip version", d.AllTexts), Notes());
        OnSta(d => Assert.Contains("Skip version", d.AllTexts), Notes(), onSkip: () => { });
    }

    [Fact]
    public void IsResizableWithAFloor() => OnSta(d =>
    {
        Assert.Equal(ResizeMode.CanResize, d.ResizeMode);
        Assert.True(d.MinWidth >= 560 && d.MinHeight >= 360);
    }, Notes());
}
