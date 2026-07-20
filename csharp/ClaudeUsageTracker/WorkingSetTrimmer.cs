// Working-set trimming for a long-running tray app.
//
// The tracker idles almost all the time; trimming pushes cold pages to the
// standby list so the process doesn't pin ~100 MB of working set for a 256 px
// widget. Pages fault back in transparently when actually needed.

using System.Runtime.InteropServices;

namespace ClaudeUsageTracker;

public static class WorkingSetTrimmer
{
    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetProcessWorkingSetSize(IntPtr process, IntPtr min, IntPtr max);

    public static void Trim()
    {
        try
        {
            GC.Collect(2, GCCollectionMode.Optimized, blocking: false);
            SetProcessWorkingSetSize(GetCurrentProcess(), (IntPtr)(-1), (IntPtr)(-1));
        }
        catch (Exception)
        {
            // Purely opportunistic — failing to trim must never affect the app.
        }
    }
}
