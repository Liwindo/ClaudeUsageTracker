// Opt the process into Windows' EcoQoS / Efficiency Mode.
//
// The tracker is idle ~99 % of the time; asking Windows to throttle it lets the
// scheduler park it on efficiency cores and clock it down (the "green leaf" in
// Task Manager), which helps battery life on laptops. Purely opportunistic —
// unsupported on older Windows 10 builds, where the call simply no-ops.

using System.Runtime.InteropServices;

namespace ClaudeUsageTracker;

public static class EfficiencyMode
{
    private const int ProcessPowerThrottling = 4;
    private const uint PowerThrottlingCurrentVersion = 1;
    private const uint ProcessPowerThrottlingExecutionSpeed = 0x1;

    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessPowerThrottlingState
    {
        public uint Version;
        public uint ControlMask;
        public uint StateMask;
    }

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetProcessInformation(
        IntPtr process, int informationClass, ref ProcessPowerThrottlingState info, int size);

    public static void Enable()
    {
        try
        {
            var state = new ProcessPowerThrottlingState
            {
                Version = PowerThrottlingCurrentVersion,
                ControlMask = ProcessPowerThrottlingExecutionSpeed,
                StateMask = ProcessPowerThrottlingExecutionSpeed, // throttle = on
            };
            SetProcessInformation(
                GetCurrentProcess(), ProcessPowerThrottling, ref state, Marshal.SizeOf(state));
        }
        catch (Exception)
        {
            // No-op on Windows builds without EcoQoS — never fatal.
        }
    }
}
