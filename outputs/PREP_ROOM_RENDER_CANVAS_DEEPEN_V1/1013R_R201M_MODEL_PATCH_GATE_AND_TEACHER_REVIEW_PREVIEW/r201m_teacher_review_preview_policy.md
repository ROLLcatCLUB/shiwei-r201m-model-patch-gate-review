# R201M Teacher Review Preview Policy

R201M treats every R201L model output as a proposed edit, not as teacher main text.

Teacher review states:
- `proposed`: visible as a suggestion and not applied to baseline.
- `accepted`: applied only to the R201M preview surface.
- `rejected`: hidden from preview body and kept in ledger for audit.
- `deferred`: not applied and carried forward as pending review.

No state in this stage writes database, Feishu, memory, formal apply, R95, or R97B route/rendering.
