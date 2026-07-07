# R201M Patch Path Normalization Guard

The canonical template path is zero-based for `episodes[n]` array access.

Rules:
- keep `target_field_path_original` whenever R201L normalized a one-based model path
- keep canonical `target_field_path` for application
- reject any path that cannot be mapped to the baseline template
- never silently apply a model patch to a neighboring episode
- invalid path probes must remain rejected and must not enter teacher preview
