namespace ClaudeUsageTracker;

/// <summary>Pure geometry helpers for the bottom-anchored widget, extracted from
/// <see cref="WidgetWindow"/> so the anchoring invariant is unit-testable without
/// a live WPF window.
///
/// The invariant: the widget's BOTTOM edge is the authoritative, user-controlled
/// position. When the window height changes at runtime — the peak-hour banner
/// appearing/disappearing, or the footer status text wrapping to more lines — the
/// bottom edge must stay put and the top must move, NOT the other way round.
/// WPF's SizeToContent=Height does the opposite (pins the top, grows downward),
/// which made the widget jump on every peak/non-peak transition. The Python
/// variant hit and fixed the same class of bug in 1.4.1; this helper plus its
/// tests stop the C# port from silently regressing it again.</summary>
internal static class WidgetGeometry
{
    /// <summary>The top the window must take so its bottom edge sits at
    /// <paramref name="bottomAnchor"/> for the current <paramref name="height"/>.
    /// Taller content ⇒ smaller (higher) top; the bottom is unchanged.</summary>
    public static double TopForBottom(double bottomAnchor, double height) =>
        bottomAnchor - height;

    /// <summary>The bottom-edge anchor implied by a given top and height. This is
    /// the height-invariant value that gets persisted, so a restart while the peak
    /// banner is showing cannot bake the banner height into the saved position.</summary>
    public static double BottomOf(double top, double height) =>
        top + height;

    /// <summary>Clamp a restored bottom-edge anchor into the virtual desktop so a
    /// saved position on a monitor that no longer exists can never leave the
    /// widget unreachable.</summary>
    public static double ClampBottom(double bottom, double virtualTop, double virtualHeight) =>
        System.Math.Max(virtualTop + 40, System.Math.Min(bottom, virtualTop + virtualHeight));
}
