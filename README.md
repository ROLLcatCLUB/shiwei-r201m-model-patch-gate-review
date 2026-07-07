# R201M Model Patch Gate And Teacher Review Preview

R201M gates R201L real-model candidate patches before any route/render binding.

Decision: model output remains useful only as teacher-review-required candidate patch.

Boundaries:
- no R220F route binding
- no R97B rendering
- no formal apply
- no database / Feishu / memory write
- no R95 export
- no baseline overwrite

Key artifacts:
- `r201m_model_patch_gate_contract.json`
- `r201m_teacher_review_preview_policy.md`
- `r201m_patch_path_normalization_guard.md`
- `r201m_patch_accept_reject_defer_simulation.json`
- `r201m_baseline_vs_model_diff_previews/`
- `r201m_candidate_visibility_policy.md`
- `r201m_rollback_to_baseline_report.md`
- `validate_1013R_R201M_model_patch_gate_and_teacher_review_preview_result.json`

Sample summary:
- `real_downpour_docx`: proposed=8, rejected_by_gate=1, path_normalized=6
- `numbered_colon_old_shoes`: proposed=8, rejected_by_gate=1, path_normalized=0
- `plain_segment_weaving`: proposed=8, rejected_by_gate=1, path_normalized=0
