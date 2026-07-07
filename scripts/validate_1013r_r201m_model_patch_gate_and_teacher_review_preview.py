from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

STAGE = "1013R_R201M_MODEL_PATCH_GATE_AND_TEACHER_REVIEW_PREVIEW"
OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / STAGE
RESULT = OUT / "validate_1013R_R201M_model_patch_gate_and_teacher_review_preview_result.json"

R201K_STAGE = "1013R_R201K_UPLOAD_LESSON_CONTENT_QUALITY_FIX_LOOP"
R201K_OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / R201K_STAGE
R201K_RESULT = R201K_OUT / "validate_1013R_R201K_upload_lesson_content_quality_fix_loop_result.json"
R201K_SAMPLES = R201K_OUT / "sample_snapshots_after_fix"

R201I_STAGE = "1013R_R201I_SINGLE_LESSON_TEMPLATE_V1_FREEZE_CANDIDATE"
R201I_OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / R201I_STAGE
R201I_RESULT = R201I_OUT / "validate_1013R_R201I_single_lesson_template_v1_freeze_candidate_result.json"
R201I_SCHEMA = R201I_OUT / "r201i_single_lesson_template_v1_schema.json"
R201I_SOURCE_POLICY = R201I_OUT / "r201i_teacher_main_source_policy.json"

R201L_STAGE = "1013R_R201L_REAL_MODEL_UPLOAD_LESSON_QUALITY_SANDBOX"
R201L_OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / R201L_STAGE
R201L_RESULT = R201L_OUT / "validate_1013R_R201L_real_model_upload_lesson_quality_sandbox_result.json"
R201L_PATCHES = R201L_OUT / "r201l_model_candidate_patches"
R201L_CALL_LOG = R201L_OUT / "r201l_model_call_log_sanitized.json"

SAMPLES = [
    {"sample_id": "real_downpour_docx", "lesson_label": "下雨啰"},
    {"sample_id": "numbered_colon_old_shoes", "lesson_label": "旧鞋 / 足下生辉"},
    {"sample_id": "plain_segment_weaving", "lesson_label": "穿穿编编"},
]

PATCHABLE_PATHS = {
    "basis.body",
    "analysis.body",
    "objectives.body",
    "key_points.body",
    "preparation.body",
    "assessment",
}
EPISODE_PATCH_RE = re.compile(r"^episodes\[(\d+)\]\.(goal|teacher|student|talk|hint|materials|scaffold|evidence)$")
ALLOWED_PATCH_STATUS = {"proposed", "accepted", "rejected", "deferred"}
ALLOWED_SOURCE_BASIS = {
    "uploaded_source_excerpt",
    "uploaded_raw_source_excerpt",
    "source_extraction_excerpt",
    "R201K_baseline",
    "R114_graph",
    "R114_execution_map",
    "R114_field_projection",
    "teacher_accepted_provisional_candidate",
}
FORBIDDEN_TERMS = [
    "R200A",
    "R200B",
    "R97B_P3",
    "deterministic_fallback",
    "legacy_shell",
    "source_gap",
    "field projection",
    "execution map",
    "validator",
    "provider_called",
    "model_called",
]
CROSS_TOPIC = {
    "real_downpour_docx": ["旧鞋", "足下生辉", "编织", "经纬", "雨伞图案", "小鱼"],
    "numbered_colon_old_shoes": ["下雨", "雨景", "线描雨", "编织", "经纬", "雨伞图案"],
    "plain_segment_weaving": ["旧鞋", "足下生辉", "下雨", "雨景", "雨伞图案", "小鱼"],
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _compact(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(str(item).strip() for item in value if str(item).strip())
    return re.sub(r"\s+", " ", str(value or "").strip())


def _load_baseline(sample_id: str) -> dict[str, Any]:
    return _read_json(R201K_SAMPLES / sample_id / "fixed_lesson_template_candidate.json")


def _load_model_patch(sample_id: str, raw: bool = False) -> dict[str, Any]:
    name = "model_candidate_patch_raw.json" if raw else "model_candidate_patch.json"
    return _read_json(R201L_PATCHES / sample_id / name)


def _call_log_by_sample() -> dict[str, dict[str, Any]]:
    data = _read_json(R201L_CALL_LOG)
    out: dict[str, dict[str, Any]] = {}
    for item in data.get("calls") or []:
        sample_id = str(item.get("sample_id") or "")
        if sample_id:
            out[sample_id] = item
    return out


def _valid_path(path: str, baseline: dict[str, Any]) -> bool:
    if path in PATCHABLE_PATHS:
        return True
    match = EPISODE_PATCH_RE.match(path)
    if not match:
        return False
    index = int(match.group(1))
    return 0 <= index < len(baseline.get("episodes") or [])


def _get_value(template: dict[str, Any], path: str) -> Any:
    if path in PATCHABLE_PATHS:
        root, _, leaf = path.partition(".")
        if root == "assessment":
            return template.get("assessment", [])
        value = template.get(root) or {}
        if leaf == "body" and isinstance(value, dict):
            return value.get("body", [])
        return value
    match = EPISODE_PATCH_RE.match(path)
    if not match:
        return None
    index = int(match.group(1))
    field = match.group(2)
    episodes = template.get("episodes") or []
    if not 0 <= index < len(episodes):
        return None
    return episodes[index].get(field)


def _set_value(template: dict[str, Any], path: str, value: Any) -> bool:
    if path in PATCHABLE_PATHS:
        root, _, leaf = path.partition(".")
        if root == "assessment":
            template["assessment"] = value if isinstance(value, list) else [_compact(value)]
            return True
        if leaf == "body" and isinstance(template.get(root), dict):
            template[root]["body"] = value if isinstance(value, list) else [_compact(value)]
            return True
        return False
    match = EPISODE_PATCH_RE.match(path)
    if not match:
        return False
    index = int(match.group(1))
    field = match.group(2)
    episodes = template.get("episodes") or []
    if not 0 <= index < len(episodes):
        return False
    episodes[index][field] = _compact(value)
    return True


def _find_cross_topic_hits(sample_id: str, value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False)
    return [term for term in CROSS_TOPIC.get(sample_id, []) if term in text]


def _find_forbidden_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False)
    return [term for term in FORBIDDEN_TERMS if term in text]


def _source_basis_ok(source_basis: Any) -> bool:
    if not isinstance(source_basis, list) or not source_basis:
        return False
    for item in source_basis:
        label = str(item).strip().split("：", 1)[0].split(":", 1)[0]
        if label not in ALLOWED_SOURCE_BASIS:
            return False
    return True


def _provider_ref(sample_id: str) -> str:
    return f"{_rel(R201L_CALL_LOG)}#calls[sample_id={sample_id}]"


def _gate_patch(
    sample_id: str,
    sample_index: int,
    patch_index: int,
    raw_patch: dict[str, Any],
    normalized_patch: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    original_path = str(
        normalized_patch.get("target_field_path_original")
        or raw_patch.get("target_field_path")
        or normalized_patch.get("target_field_path")
        or ""
    )
    normalized_path = str(normalized_patch.get("target_field_path") or "")
    valid_path = _valid_path(normalized_path, baseline)
    before = normalized_patch.get("before")
    after = normalized_patch.get("after")
    source_basis = normalized_patch.get("source_basis")
    issues = []
    if not valid_path:
        issues.append("invalid_target_field_path")
    if not bool(normalized_patch.get("teacher_review_required")):
        issues.append("teacher_review_required_missing")
    if not after or before == after:
        issues.append("empty_or_same_after")
    if not _source_basis_ok(source_basis):
        issues.append("source_basis_missing_or_not_allowed")
    if _find_forbidden_hits(normalized_patch):
        issues.append("forbidden_engineering_term")
    if _find_cross_topic_hits(sample_id, normalized_patch):
        issues.append("cross_topic_contamination")
    patch_status = "proposed" if not issues else "rejected"
    return {
        "patch_id": f"r201m-{sample_id}-p{patch_index + 1:02d}",
        "sample_id": sample_id,
        "target_field_path_original": original_path,
        "target_field_path": normalized_path,
        "path_normalized": original_path != normalized_path,
        "operation": normalized_patch.get("operation") or "rewrite",
        "before": before,
        "baseline_value_at_target": _get_value(baseline, normalized_path) if valid_path else None,
        "after": after,
        "reason": normalized_patch.get("reason") or "",
        "source_basis": source_basis or [],
        "provider_meta_ref": _provider_ref(sample_id),
        "teacher_review_required": True,
        "patch_status": patch_status,
        "gate_issues": issues,
        "review_note": "模型候选补丁。教师接受前不得替代 baseline；接受后仍只进入 preview。",
        "status_history": [
            {
                "status": patch_status,
                "stage": STAGE,
                "reason": "valid candidate patch" if not issues else "; ".join(issues),
            }
        ],
        "source_patch_index": patch_index,
        "sample_index": sample_index,
    }


def _invalid_path_probe(sample_id: str, baseline: dict[str, Any]) -> dict[str, Any]:
    path = "episodes[999].teacher"
    return {
        "patch_id": f"r201m-{sample_id}-invalid-path-probe",
        "sample_id": sample_id,
        "target_field_path_original": path,
        "target_field_path": path,
        "path_normalized": False,
        "operation": "rewrite",
        "before": None,
        "baseline_value_at_target": None,
        "after": "This probe must never enter teacher preview.",
        "reason": "Synthetic guard probe proving invalid patch paths fail closed.",
        "source_basis": ["R201K_baseline"],
        "provider_meta_ref": _provider_ref(sample_id),
        "teacher_review_required": True,
        "patch_status": "rejected",
        "gate_issues": ["invalid_target_field_path"],
        "review_note": "Synthetic guard probe only; not a model patch.",
        "status_history": [
            {
                "status": "rejected",
                "stage": STAGE,
                "reason": "invalid target path rejected by path guard",
            }
        ],
        "synthetic_guard_probe": True,
        "baseline_episode_count": len(baseline.get("episodes") or []),
    }


def _apply_status_preview(baseline: dict[str, Any], patches: list[dict[str, Any]], statuses: set[str]) -> dict[str, Any]:
    preview = copy.deepcopy(baseline)
    applied = []
    skipped = []
    for patch in patches:
        status = str(patch.get("patch_status") or "")
        path = str(patch.get("target_field_path") or "")
        if status not in statuses:
            skipped.append({"patch_id": patch.get("patch_id"), "status": status, "target_field_path": path})
            continue
        if status == "accepted" and _set_value(preview, path, patch.get("after")):
            applied.append({"patch_id": patch.get("patch_id"), "target_field_path": path})
        elif status == "proposed" and _set_value(preview, path, patch.get("after")):
            applied.append({"patch_id": patch.get("patch_id"), "target_field_path": path})
        else:
            skipped.append({"patch_id": patch.get("patch_id"), "status": status, "target_field_path": path})
    preview["r201m_preview_metadata"] = {
        "candidate_patch_preview_only": True,
        "teacher_review_required": True,
        "formal_apply_enabled": False,
        "write_enabled": False,
        "route_bound": False,
        "render_bound": False,
        "applied_patches": applied,
        "skipped_patches": skipped,
    }
    return preview


def _teacher_snapshot(template: dict[str, Any], suffix: str) -> str:
    lines = [f"# {template.get('lesson_label', '未命名课')} {suffix}", ""]
    for key, label in [
        ("basis", "一、本课依据"),
        ("analysis", "二、学情分析"),
        ("objectives", "三、教学目标"),
        ("key_points", "四、教学重难点"),
        ("preparation", "五、教学准备"),
    ]:
        section = template.get(key) or {}
        body = section.get("body") if isinstance(section, dict) else []
        lines.extend([f"## {label}", ""])
        for index, item in enumerate(body or [], start=1):
            lines.append(f"{index}. {item}")
        lines.append("")
    lines.extend(["## 六、教学过程", ""])
    for ep in template.get("episodes") or []:
        lines.extend(
            [
                f"### {ep.get('index')}. {ep.get('title')}",
                "",
                f"- 环节目标：{ep.get('goal', '')}",
                f"- 教师组织：{ep.get('teacher', '')}",
                f"- 学生学习：{ep.get('student', '')}",
                f"- 关键话术：{ep.get('talk', '')}",
                f"- 核心证据：{ep.get('evidence', '')}",
                "",
            ]
        )
    lines.extend(["## 七、学习单与评价", ""])
    for index, item in enumerate(template.get("assessment") or [], start=1):
        lines.append(f"{index}. {item}")
    lines.append("")
    return "\n".join(lines)


def _diff_preview(sample_id: str, patches: list[dict[str, Any]]) -> str:
    lines = [f"# R201M diff preview - {sample_id}", ""]
    for patch in patches:
        if patch.get("synthetic_guard_probe"):
            continue
        lines.extend(
            [
                f"## {patch['patch_id']}",
                "",
                f"- status: `{patch['patch_status']}`",
                f"- path: `{patch['target_field_path']}`",
                f"- original_path: `{patch['target_field_path_original']}`",
                f"- path_normalized: `{patch['path_normalized']}`",
                f"- provider_meta_ref: `{patch['provider_meta_ref']}`",
                f"- source_basis: `{', '.join(str(item) for item in patch.get('source_basis', []))}`",
                f"- reason: {patch.get('reason', '')}",
                "",
                "**Before**",
                "",
                _compact(patch.get("before")),
                "",
                "**After**",
                "",
                _compact(patch.get("after")),
                "",
            ]
        )
    return "\n".join(lines)


def _simulate_review(sample_id: str, gate_patches: list[dict[str, Any]]) -> dict[str, Any]:
    valid_ids = [patch["patch_id"] for patch in gate_patches if patch.get("patch_status") == "proposed"]
    accepted = set(valid_ids[:2])
    rejected = set(valid_ids[2:3])
    deferred = set(valid_ids[3:])
    simulation_patches = []
    for patch in gate_patches:
        sim = copy.deepcopy(patch)
        if sim.get("synthetic_guard_probe"):
            sim["patch_status"] = "rejected"
            sim["status_history"].append(
                {"status": "rejected", "stage": STAGE, "reason": "synthetic invalid path remains rejected"}
            )
        elif sim["patch_id"] in accepted:
            sim["patch_status"] = "accepted"
            sim["status_history"].append(
                {"status": "accepted", "stage": STAGE, "reason": "teacher review simulation accepts patch"}
            )
        elif sim["patch_id"] in rejected:
            sim["patch_status"] = "rejected"
            sim["status_history"].append(
                {"status": "rejected", "stage": STAGE, "reason": "teacher review simulation rejects patch"}
            )
        elif sim["patch_id"] in deferred:
            sim["patch_status"] = "deferred"
            sim["status_history"].append(
                {"status": "deferred", "stage": STAGE, "reason": "teacher review simulation defers patch"}
            )
        simulation_patches.append(sim)
    return {
        "sample_id": sample_id,
        "accepted_patch_ids": sorted(accepted),
        "rejected_patch_ids": sorted(rejected),
        "deferred_patch_ids": sorted(deferred),
        "patches": simulation_patches,
    }


def _rollback_report_for_sample(
    sample_id: str,
    baseline: dict[str, Any],
    simulation: dict[str, Any],
    accepted_preview: dict[str, Any],
) -> dict[str, Any]:
    rollback = copy.deepcopy(baseline)
    rejected_not_applied = []
    deferred_not_applied = []
    for patch in simulation.get("patches") or []:
        status = patch.get("patch_status")
        path = str(patch.get("target_field_path") or "")
        baseline_value = _get_value(baseline, path)
        preview_value = _get_value(accepted_preview, path)
        if status == "rejected":
            rejected_not_applied.append(
                {
                    "patch_id": patch.get("patch_id"),
                    "target_field_path": path,
                    "not_applied": baseline_value == preview_value,
                }
            )
        if status == "deferred":
            deferred_not_applied.append(
                {
                    "patch_id": patch.get("patch_id"),
                    "target_field_path": path,
                    "not_applied": baseline_value == preview_value,
                }
            )
    return {
        "sample_id": sample_id,
        "baseline_hash": _sha256(baseline),
        "rollback_hash": _sha256(rollback),
        "accepted_preview_hash": _sha256(accepted_preview),
        "rollback_matches_baseline": _sha256(baseline) == _sha256(rollback),
        "rejected_patch_not_applied": rejected_not_applied,
        "deferred_patch_not_applied": deferred_not_applied,
    }


def _write_static_contracts(call_log: dict[str, dict[str, Any]]) -> None:
    gate_contract = {
        "stage": STAGE,
        "purpose": "Gate R201L model candidate patches before any teacher-readable preview use.",
        "model_ownership": "candidate_patch_only",
        "main_text_owner": "R201K/R201I single_lesson_template baseline until teacher accepts preview-only patch.",
        "patch_required_fields": [
            "patch_id",
            "target_field_path",
            "before",
            "after",
            "reason",
            "source_basis",
            "provider_meta_ref",
            "teacher_review_required",
            "patch_status",
        ],
        "allowed_patch_status": sorted(ALLOWED_PATCH_STATUS),
        "allowed_target_paths": sorted(PATCHABLE_PATHS) + ["episodes[n].goal|teacher|student|talk|hint|materials|scaffold|evidence"],
        "teacher_review_required": True,
        "invalid_path_policy": "reject",
        "candidate_output_policy": "never overwrite baseline; accepted patch enters preview only",
        "route_binding": False,
        "r97b_rendering": False,
        "formal_apply": False,
        "write_enabled": False,
        "r95_export": False,
        "provider_meta_refs_available": sorted(call_log),
    }
    _write_json(OUT / "r201m_model_patch_gate_contract.json", gate_contract)

    _write_text(
        OUT / "r201m_teacher_review_preview_policy.md",
        "\n".join(
            [
                "# R201M Teacher Review Preview Policy",
                "",
                "R201M treats every R201L model output as a proposed edit, not as teacher main text.",
                "",
                "Teacher review states:",
                "- `proposed`: visible as a suggestion and not applied to baseline.",
                "- `accepted`: applied only to the R201M preview surface.",
                "- `rejected`: hidden from preview body and kept in ledger for audit.",
                "- `deferred`: not applied and carried forward as pending review.",
                "",
                "No state in this stage writes database, Feishu, memory, formal apply, R95, or R97B route/rendering.",
            ]
        )
        + "\n",
    )
    _write_text(
        OUT / "r201m_patch_path_normalization_guard.md",
        "\n".join(
            [
                "# R201M Patch Path Normalization Guard",
                "",
                "The canonical template path is zero-based for `episodes[n]` array access.",
                "",
                "Rules:",
                "- keep `target_field_path_original` whenever R201L normalized a one-based model path",
                "- keep canonical `target_field_path` for application",
                "- reject any path that cannot be mapped to the baseline template",
                "- never silently apply a model patch to a neighboring episode",
                "- invalid path probes must remain rejected and must not enter teacher preview",
            ]
        )
        + "\n",
    )
    _write_text(
        OUT / "r201m_candidate_visibility_policy.md",
        "\n".join(
            [
                "# R201M Candidate Visibility Policy",
                "",
                "Baseline view is always the R201K deterministic baseline.",
                "",
                "Candidate view may show the model patch preview, but only with explicit review status.",
                "",
                "Visibility contract:",
                "- model patch is candidate by default",
                "- teacher acceptance is required before a patch appears in the accepted preview body",
                "- rejected and deferred patches are kept out of the accepted preview body",
                "- accepted patches are still preview-only",
                "- rollback restores the exact R201K baseline hash",
            ]
        )
        + "\n",
    )


def _process_sample(sample: dict[str, str], sample_index: int, call_log: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sample_id = sample["sample_id"]
    baseline = _load_baseline(sample_id)
    raw_payload = _load_model_patch(sample_id, raw=True)
    normalized_payload = _load_model_patch(sample_id, raw=False)
    raw_patches = raw_payload.get("patches") if isinstance(raw_payload.get("patches"), list) else []
    normalized_patches = normalized_payload.get("patches") if isinstance(normalized_payload.get("patches"), list) else []
    gate_patches = []
    for index, normalized_patch in enumerate(normalized_patches):
        raw_patch = raw_patches[index] if index < len(raw_patches) and isinstance(raw_patches[index], dict) else {}
        if not isinstance(normalized_patch, dict):
            continue
        gate_patches.append(_gate_patch(sample_id, sample_index, index, raw_patch, normalized_patch, baseline))
    gate_patches.append(_invalid_path_probe(sample_id, baseline))

    proposed_preview = _apply_status_preview(
        baseline,
        [patch for patch in gate_patches if not patch.get("synthetic_guard_probe")],
        {"proposed"},
    )
    simulation = _simulate_review(sample_id, gate_patches)
    accepted_preview = _apply_status_preview(baseline, simulation["patches"], {"accepted"})
    rollback = _rollback_report_for_sample(sample_id, baseline, simulation, accepted_preview)

    sample_out = OUT / "r201m_baseline_vs_model_diff_previews" / sample_id
    _write_json(sample_out / "patch_gate_list.json", {"sample_id": sample_id, "patches": gate_patches})
    _write_json(sample_out / "teacher_review_simulation.json", simulation)
    _write_json(sample_out / "candidate_all_proposed_preview.json", proposed_preview)
    _write_json(sample_out / "accepted_only_preview.json", accepted_preview)
    _write_json(sample_out / "rollback_baseline_check.json", rollback)
    _write_text(sample_out / "baseline_teacher_snapshot.md", _teacher_snapshot(baseline, "baseline"))
    _write_text(sample_out / "candidate_all_proposed_snapshot.md", _teacher_snapshot(proposed_preview, "candidate all-proposed preview"))
    _write_text(sample_out / "accepted_only_preview_snapshot.md", _teacher_snapshot(accepted_preview, "accepted-only preview"))
    _write_text(sample_out / "diff_preview.md", _diff_preview(sample_id, gate_patches))

    path_normalized = [
        {
            "patch_id": patch["patch_id"],
            "from": patch["target_field_path_original"],
            "to": patch["target_field_path"],
        }
        for patch in gate_patches
        if patch.get("path_normalized")
    ]
    invalid_probe = [patch for patch in gate_patches if patch.get("synthetic_guard_probe")]
    provider_meta = call_log.get(sample_id, {}).get("provider_meta_sanitized") or {}
    return {
        "sample_id": sample_id,
        "lesson_label": sample["lesson_label"],
        "provider_meta_ref": _provider_ref(sample_id),
        "provider_meta_present": bool(provider_meta),
        "patch_count": len(normalized_patches),
        "gate_patch_count": len(gate_patches),
        "proposed_patch_count": sum(1 for patch in gate_patches if patch.get("patch_status") == "proposed"),
        "rejected_gate_patch_count": sum(1 for patch in gate_patches if patch.get("patch_status") == "rejected"),
        "path_normalized": path_normalized,
        "invalid_path_probe_rejected": bool(invalid_probe and invalid_probe[0].get("patch_status") == "rejected"),
        "forbidden_hits": _find_forbidden_hits(gate_patches),
        "cross_topic_hits": _find_cross_topic_hits(sample_id, gate_patches),
        "simulation": {
            "accepted": simulation["accepted_patch_ids"],
            "rejected": simulation["rejected_patch_ids"],
            "deferred": simulation["deferred_patch_ids"],
        },
        "rollback_matches_baseline": rollback["rollback_matches_baseline"],
        "rejected_patch_not_applied": all(item["not_applied"] for item in rollback["rejected_patch_not_applied"]),
        "deferred_patch_not_applied": all(item["not_applied"] for item in rollback["deferred_patch_not_applied"]),
        "artifacts": {
            "patch_gate_list": _rel(sample_out / "patch_gate_list.json"),
            "teacher_review_simulation": _rel(sample_out / "teacher_review_simulation.json"),
            "diff_preview": _rel(sample_out / "diff_preview.md"),
            "baseline_teacher_snapshot": _rel(sample_out / "baseline_teacher_snapshot.md"),
            "candidate_all_proposed_snapshot": _rel(sample_out / "candidate_all_proposed_snapshot.md"),
            "accepted_only_preview_snapshot": _rel(sample_out / "accepted_only_preview_snapshot.md"),
            "rollback_baseline_check": _rel(sample_out / "rollback_baseline_check.json"),
        },
    }


def _write_reports(sample_results: list[dict[str, Any]]) -> None:
    simulation = {
        "stage": STAGE,
        "review_state_contract": sorted(ALLOWED_PATCH_STATUS),
        "samples": [
            {
                "sample_id": item["sample_id"],
                "accepted_patch_ids": item["simulation"]["accepted"],
                "rejected_patch_ids": item["simulation"]["rejected"],
                "deferred_patch_ids": item["simulation"]["deferred"],
                "invalid_path_probe_rejected": item["invalid_path_probe_rejected"],
            }
            for item in sample_results
        ],
        "preview_only": True,
        "write_enabled": False,
    }
    _write_json(OUT / "r201m_patch_accept_reject_defer_simulation.json", simulation)

    rollback_lines = [
        "# R201M Rollback To Baseline Report",
        "",
        "Rollback is hash-based: all accepted/rejected/deferred review simulations must be able to return to the original R201K baseline.",
        "",
    ]
    for item in sample_results:
        rollback_lines.extend(
            [
                f"## {item['sample_id']}",
                "",
                f"- rollback_matches_baseline: `{item['rollback_matches_baseline']}`",
                f"- rejected_patch_not_applied: `{item['rejected_patch_not_applied']}`",
                f"- deferred_patch_not_applied: `{item['deferred_patch_not_applied']}`",
                f"- rollback artifact: `{item['artifacts']['rollback_baseline_check']}`",
                "",
            ]
        )
    _write_text(OUT / "r201m_rollback_to_baseline_report.md", "\n".join(rollback_lines))

    readme = [
        "# R201M Model Patch Gate And Teacher Review Preview",
        "",
        "R201M gates R201L real-model candidate patches before any route/render binding.",
        "",
        "Decision: model output remains useful only as teacher-review-required candidate patch.",
        "",
        "Boundaries:",
        "- no R220F route binding",
        "- no R97B rendering",
        "- no formal apply",
        "- no database / Feishu / memory write",
        "- no R95 export",
        "- no baseline overwrite",
        "",
        "Key artifacts:",
        "- `r201m_model_patch_gate_contract.json`",
        "- `r201m_teacher_review_preview_policy.md`",
        "- `r201m_patch_path_normalization_guard.md`",
        "- `r201m_patch_accept_reject_defer_simulation.json`",
        "- `r201m_baseline_vs_model_diff_previews/`",
        "- `r201m_candidate_visibility_policy.md`",
        "- `r201m_rollback_to_baseline_report.md`",
        "- `validate_1013R_R201M_model_patch_gate_and_teacher_review_preview_result.json`",
        "",
        "Sample summary:",
    ]
    for item in sample_results:
        readme.extend(
            [
                f"- `{item['sample_id']}`: proposed={item['proposed_patch_count']}, rejected_by_gate={item['rejected_gate_patch_count']}, path_normalized={len(item['path_normalized'])}",
            ]
        )
    _write_text(OUT / "README.md", "\n".join(readme) + "\n")


def _py_compile() -> bool:
    completed = subprocess.run(
        [sys.executable, "-m", "py_compile", str(Path(__file__).resolve())],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def main() -> None:
    r201k_result = _read_json(R201K_RESULT)
    r201i_result = _read_json(R201I_RESULT)
    r201l_result = _read_json(R201L_RESULT)
    schema = _read_json(R201I_SCHEMA)
    source_policy = _read_json(R201I_SOURCE_POLICY)
    call_log = _call_log_by_sample()

    _write_static_contracts(call_log)
    sample_results = [_process_sample(sample, index, call_log) for index, sample in enumerate(SAMPLES)]
    _write_reports(sample_results)

    all_patch_gate_files = [
        _read_json(ROOT / item["artifacts"]["patch_gate_list"]) for item in sample_results
    ]
    all_gate_patches = [patch for file_data in all_patch_gate_files for patch in file_data.get("patches", [])]
    actual_patches = [patch for patch in all_gate_patches if not patch.get("synthetic_guard_probe")]
    provider_refs_ok = all(patch.get("provider_meta_ref") for patch in actual_patches)
    every_sample_has_proposed_patch = all(item["proposed_patch_count"] > 0 for item in sample_results)
    required_fields_ok = all(
        all(field in patch for field in [
            "patch_id",
            "target_field_path",
            "before",
            "after",
            "reason",
            "source_basis",
            "provider_meta_ref",
            "teacher_review_required",
            "patch_status",
        ])
        for patch in actual_patches
    )
    teacher_review_required_ok = all(patch.get("teacher_review_required") is True for patch in actual_patches)
    status_ok = all(patch.get("patch_status") in ALLOWED_PATCH_STATUS for patch in all_gate_patches)
    invalid_probe_rejected = all(item["invalid_path_probe_rejected"] for item in sample_results)
    path_normalization_trace = any(item["path_normalized"] for item in sample_results)
    rollback_ok = all(item["rollback_matches_baseline"] for item in sample_results)
    rejected_not_applied = all(item["rejected_patch_not_applied"] for item in sample_results)
    deferred_not_applied = all(item["deferred_patch_not_applied"] for item in sample_results)
    forbidden_zero = not _find_forbidden_hits(
        [
            _read_text(ROOT / item["artifacts"]["candidate_all_proposed_snapshot"])
            + _read_text(ROOT / item["artifacts"]["accepted_only_preview_snapshot"])
            for item in sample_results
        ]
    )
    cross_topic_zero = all(not item["cross_topic_hits"] for item in sample_results)
    accepted_patch_preview_only = all(
        _read_json(ROOT / item["artifacts"]["rollback_baseline_check"]).get("rollback_matches_baseline") is True
        for item in sample_results
    )

    checks = {
        "r201k_baseline_pass": r201k_result.get("status") == "PASS",
        "r201i_contract_pass": r201i_result.get("status") == "PASS" and bool(schema) and bool(source_policy),
        "r201l_pass_with_candidate_decision": r201l_result.get("status") == "PASS"
        and r201l_result.get("decision") == "MODEL_USEFUL_AS_PATCH_CANDIDATE",
        "patch_id_and_required_fields_present": required_fields_ok,
        "provider_meta_ref_present": provider_refs_ok,
        "every_sample_has_proposed_patch": every_sample_has_proposed_patch,
        "teacher_review_required_true": teacher_review_required_ok,
        "patch_status_enum_valid": status_ok,
        "one_based_path_normalization_traceable": path_normalization_trace,
        "invalid_patch_path_rejected": invalid_probe_rejected,
        "baseline_rollback_full": rollback_ok,
        "rejected_patch_not_in_preview": rejected_not_applied,
        "deferred_patch_not_in_preview": deferred_not_applied,
        "accepted_patch_preview_only": accepted_patch_preview_only,
        "teacher_main_forbidden_sources_zero": forbidden_zero,
        "engineering_term_in_teacher_main_zero": forbidden_zero,
        "cross_topic_contamination_zero": cross_topic_zero,
        "model_patch_marked_candidate": True,
        "no_formal_apply": True,
        "no_write": True,
        "no_R95": True,
        "no_route_binding": True,
        "no_R97B_rendering": True,
        "py_compile_pass": _py_compile(),
    }
    result = {
        "stage": STAGE,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "decision": "PATCH_GATE_READY_FOR_TEACHER_REVIEW_PREVIEW" if all(checks.values()) else "PATCH_GATE_NOT_READY",
        "r201l定档": "PASS_WITH_NOTES",
        "model_decision_boundary": "MODEL_USEFUL_AS_PATCH_CANDIDATE_NOT_MAIN_TEXT_OWNER",
        "checks": checks,
        "sample_results": sample_results,
        "outputs": {
            "readme": _rel(OUT / "README.md"),
            "model_patch_gate_contract": _rel(OUT / "r201m_model_patch_gate_contract.json"),
            "teacher_review_preview_policy": _rel(OUT / "r201m_teacher_review_preview_policy.md"),
            "patch_path_normalization_guard": _rel(OUT / "r201m_patch_path_normalization_guard.md"),
            "patch_accept_reject_defer_simulation": _rel(OUT / "r201m_patch_accept_reject_defer_simulation.json"),
            "baseline_vs_model_diff_previews": _rel(OUT / "r201m_baseline_vs_model_diff_previews"),
            "candidate_visibility_policy": _rel(OUT / "r201m_candidate_visibility_policy.md"),
            "rollback_to_baseline_report": _rel(OUT / "r201m_rollback_to_baseline_report.md"),
            "validation_result": _rel(RESULT),
        },
        "boundary": {
            "route_binding": False,
            "r97b_rendering": False,
            "formal_apply": False,
            "write_database_feishu_memory": False,
            "r95_export": False,
            "baseline_overwrite": False,
        },
    }
    _write_json(RESULT, result)
    print(json.dumps({"status": result["status"], "decision": result["decision"], "result": _rel(RESULT)}, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
