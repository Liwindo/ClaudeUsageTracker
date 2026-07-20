using Xunit;

// I18n is process-global mutable state (I18n.Init switches the active catalog).
// Several test classes assert language-specific output while I18nTests flips the
// catalog to "de" mid-run; with xunit's default per-collection parallelism a
// class could observe another class's language and fail nondeterministically
// (e.g. a toast title "Zurückgesetzt" where "reset" was asserted). The suite is
// tiny (~130 ms), so serialising all collections is the simplest robust fix.
[assembly: CollectionBehavior(DisableTestParallelization = true)]
