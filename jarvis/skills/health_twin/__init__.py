"""
JARVIS Built-in Skill: Private Health Twin & Lab Report Tracker
===============================================================
Evaluates clinical laboratory biomarkers (Glucose, Cholesterol, Triglycerides, AST, ALT, Uric Acid)
against standard reference ranges, identifies anomalies, and provides lifestyle recommendations
while keeping personal health records 100% private and local.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.health_twin")

# Standard adult reference intervals
REFERENCE_RANGES: dict[str, dict[str, Any]] = {
    "glucose": {"min": 3.9, "max": 5.5, "unit": "mmol/L", "name": "Đường huyết lúc đói (Glucose)", "risk_high": "Nguy cơ tiền tiểu đường / đái tháo đường", "risk_low": "Hạ đường huyết"},
    "cholesterol": {"min": 2.8, "max": 5.2, "unit": "mmol/L", "name": "Cholesterol toàn phần", "risk_high": "Tăng mỡ máu, nguy cơ xơ vữa động mạch", "risk_low": "Thiếu hụt mỡ máu"},
    "triglycerides": {"min": 0.4, "max": 1.7, "unit": "mmol/L", "name": "Triglyceride (Mỡ máu)", "risk_high": "Mỡ máu cao, nguy cơ gan nhiễm mỡ / tim mạch", "risk_low": "Mức bình thường"},
    "uric_acid": {"min": 200, "max": 420, "unit": "µmol/L", "name": "Axit Uric máu", "risk_high": "Tăng axit uric, nguy cơ bệnh Gout", "risk_low": "Thấp"},
    "ast": {"min": 10, "max": 40, "unit": "U/L", "name": "Men gan AST (SGOT)", "risk_high": "Tổn thương tế bào gan / cơ tim", "risk_low": "Bình thường"},
    "alt": {"min": 7, "max": 56, "unit": "U/L", "name": "Men gan ALT (SGPT)", "risk_high": "Viêm gan, gan nhiễm mỡ, men gan cao", "risk_low": "Bình thường"},
}


def analyze_biomarkers(metrics: dict[str, float]) -> dict[str, Any]:
    """Analyze provided biomarker dictionary against clinical thresholds."""
    results: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []

    for key, value in metrics.items():
        norm_key = key.lower().strip().replace(" ", "_")
        ref = REFERENCE_RANGES.get(norm_key)
        if not ref:
            results.append({
                "metric": key,
                "value": value,
                "status": "Chưa có dải tham chiếu chuẩn",
            })
            continue

        min_val = ref["min"]
        max_val = ref["max"]
        unit = ref["unit"]
        name = ref["name"]

        status = "Bình thường"
        flag = "NORMAL"
        explanation = "Nằm trong khoảng an toàn cho phép."

        if value > max_val:
            status = "Cao vượt ngưỡng"
            flag = "HIGH"
            explanation = ref["risk_high"]
            anomalies.append({"metric": name, "value": value, "status": status, "explanation": explanation})
        elif value < min_val:
            status = "Thấp hơn chuẩn"
            flag = "LOW"
            explanation = ref["risk_low"]
            anomalies.append({"metric": name, "value": value, "status": status, "explanation": explanation})

        results.append({
            "metric": name,
            "raw_key": key,
            "value": value,
            "unit": unit,
            "reference": f"{min_val} - {max_val} {unit}",
            "status": status,
            "flag": flag,
            "explanation": explanation,
        })

    return {
        "analyzed_count": len(results),
        "anomalies_count": len(anomalies),
        "results": results,
        "anomalies": anomalies,
    }


def execute(
    metrics: dict[str, float] | None = None,
    biomarkers: dict[str, float] | None = None,
    glucose: float | None = None,
    cholesterol: float | None = None,
    triglycerides: float | None = None,
    uric_acid: float | None = None,
    ast: float | None = None,
    alt: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute lab report biomarker evaluation.
    """
    eval_dict: dict[str, float] = {}
    if metrics and isinstance(metrics, dict):
        eval_dict.update(metrics)
    if biomarkers and isinstance(biomarkers, dict):
        eval_dict.update(biomarkers)
    if kwargs.get("data") and isinstance(kwargs["data"], dict):
        eval_dict.update(kwargs["data"])

    # Allow direct keyword args
    if glucose is not None:
        eval_dict["glucose"] = float(glucose)
    if cholesterol is not None:
        eval_dict["cholesterol"] = float(cholesterol)
    if triglycerides is not None:
        eval_dict["triglycerides"] = float(triglycerides)
    if uric_acid is not None:
        eval_dict["uric_acid"] = float(uric_acid)
    if ast is not None:
        eval_dict["ast"] = float(ast)
    if alt is not None:
        eval_dict["alt"] = float(alt)

    if not eval_dict:
        # Default baseline demo check if no inputs supplied
        eval_dict = {"glucose": 5.2, "cholesterol": 5.8, "triglycerides": 2.1, "alt": 35.0}

    analysis = analyze_biomarkers(eval_dict)
    res_list = analysis["results"]
    anom_list = analysis["anomalies"]

    lines: list[str] = [
        "🩺 **BÁO CÁO PHÂN TÍCH CHỈ SỐ XÉT NGHIỆM SỨC KHỎE (100% PRIVATE)**",
        f"• Đã đánh giá: **{len(res_list)} chỉ số y tế**.",
    ]

    if anom_list:
        lines.append(f"⚠️ Phát hiện **{len(anom_list)} chỉ số cần lưu ý**:")
        for a in anom_list:
            lines.append(f"  • **{a['metric']}**: `{a['value']}` ({a['status']}) ➔ *{a['explanation']}*")
    else:
        lines.append("✅ Tất cả các chỉ số xét nghiệm đều nằm trong ngưỡng an toàn tuyệt đối.")

    lines.append("\n📋 **Chi tiết từng chỉ số:**")
    for r in res_list:
        lines.append(f"  - {r['metric']}: **{r['value']} {r.get('unit', '')}** (Chuẩn: {r.get('reference', 'N/A')}) ➔ `{r['status']}`")

    lines.append("\n💡 *Lời khuyên lối sống:* Uống đủ 2L nước mỗi ngày, hạn chế đồ chiên xào nhiều dầu mỡ và đồ uống có cồn, duy trì đi bộ 30 phút/ngày.")

    msg = "\n".join(lines)
    return {
        "data": {
            "summary": analysis,
            "total_evaluated": len(res_list),
            "abnormal_count": len(anom_list),
            "results": res_list,
            "anomalies": anom_list,
            "success": True,
        },
        "output": msg,
    }
