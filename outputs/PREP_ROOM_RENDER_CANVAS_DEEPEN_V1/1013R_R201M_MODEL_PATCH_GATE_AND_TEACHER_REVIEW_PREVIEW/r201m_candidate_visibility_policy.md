# R201M Candidate Visibility Policy

Baseline view is always the R201K deterministic baseline.

Candidate view may show the model patch preview, but only with explicit review status.

Visibility contract:
- model patch is candidate by default
- teacher acceptance is required before a patch appears in the accepted preview body
- rejected and deferred patches are kept out of the accepted preview body
- accepted patches are still preview-only
- rollback restores the exact R201K baseline hash
