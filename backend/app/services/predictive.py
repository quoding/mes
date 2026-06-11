"""RAG-like predictive maintenance.

No vector DB required. Instead:
1. Extract rolling statistics (features) from current sensor data.
2. Search anomaly_events history for similar past patterns (parameter range filter).
3. Rank candidates by normalized Euclidean distance.
4. Inject top-3 similar cases as context into the LLM to generate a report.

This mimics RAG semantics without embeddings — the "retrieval" is statistical
pattern matching, and the "generation" is LLM synthesis of retrieved context.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Feature window for current sensor state
FEATURE_WINDOW_MINUTES = 30
# How far back to search for similar historical cases
HISTORY_LOOKBACK_DAYS = 90


def _extract_features(values: list[float]) -> dict[str, float]:
    """Extract statistical feature vector from a time-series window."""
    if not values:
        return {}
    arr = np.array(values, dtype=float)
    # Trend: linear regression slope
    x = np.arange(len(arr))
    slope = float(np.polyfit(x, arr, 1)[0]) if len(arr) >= 2 else 0.0
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "skewness": float(_skewness(arr)),
        "trend_slope": slope,
    }


def _skewness(arr: np.ndarray) -> float:
    if arr.std() < 1e-9:
        return 0.0
    return float(((arr - arr.mean()) ** 3).mean() / arr.std() ** 3)


def _euclidean_distance(a: dict, b: dict) -> float:
    """Normalized Euclidean distance between two feature dicts."""
    keys = set(a) & set(b)
    if not keys:
        return float("inf")
    diffs = [(a[k] - b.get(k, 0)) for k in keys]
    return float(np.linalg.norm(diffs))


def _risk_score(similar_cases: list[dict], current_features: dict) -> float:
    """
    Compute risk score 0–100 based on:
    - Proximity to past failure patterns (lower distance → higher risk)
    - Recency of anomalies
    - Trend slope magnitude
    """
    if not similar_cases:
        base = 20.0
    else:
        # Closest match distance
        distances = [c.get("distance", 100.0) for c in similar_cases]
        min_dist = min(distances)
        # Sigmoid-like: distance 0 → risk 90, distance large → risk 20
        proximity_risk = 90 / (1 + min_dist * 0.1)
        base = float(np.clip(proximity_risk, 20, 90))

    # Boost for high std or strong trend
    std_val = current_features.get("std", 0)
    trend = abs(current_features.get("trend_slope", 0))
    boost = min(10, std_val * 0.5 + trend * 2)

    return round(min(100, base + boost), 1)


async def _fetch_current_features(db: AsyncSession, equipment) -> dict[str, float]:
    """Fetch recent sensor data for the equipment's station and compute features."""
    since = datetime.now(timezone.utc) - timedelta(minutes=FEATURE_WINDOW_MINUTES)
    rows = await db.execute(
        text("""
            SELECT param, value FROM process_data
            WHERE line_id = :line AND station = :station AND time >= :since
            ORDER BY time
        """),
        {"line": equipment.line_id, "station": equipment.station, "since": since},
    )
    by_param: dict[str, list[float]] = {}
    for param, value in rows:
        by_param.setdefault(param, []).append(value)

    # Aggregate features across all params
    all_values = [v for vals in by_param.values() for v in vals]
    features = _extract_features(all_values)
    features["param_count"] = len(by_param)
    features["sample_count"] = len(all_values)
    return features


async def _fetch_similar_cases(
    db: AsyncSession, equipment, current_features: dict
) -> list[dict]:
    """Find historical anomaly events with similar statistical fingerprints."""
    since = datetime.now(timezone.utc) - timedelta(days=HISTORY_LOOKBACK_DAYS)
    rows = await db.execute(
        text("""
            SELECT id, detected_at, severity, param, value, pattern_type, feature_snapshot
            FROM anomaly_events
            WHERE station = :station AND detected_at >= :since
            ORDER BY detected_at DESC
            LIMIT 200
        """),
        {"station": equipment.station, "since": since},
    )
    candidates: list[dict] = []
    for row in rows:
        eid, detected_at, severity, param, value, pattern_type, snapshot = row
        hist_features: dict = {}
        if snapshot:
            try:
                hist_features = json.loads(snapshot)
            except Exception:
                pass

        dist = _euclidean_distance(current_features, hist_features) if hist_features else 50.0
        candidates.append({
            "id": eid,
            "date": detected_at.strftime("%Y-%m-%d %H:%M"),
            "severity": severity,
            "param": param,
            "value": round(value, 3),
            "pattern_type": pattern_type,
            "distance": round(dist, 2),
        })

    # Sort by distance (most similar first)
    candidates.sort(key=lambda c: c["distance"])
    return candidates[:3]


async def _generate_llm_report(
    equipment, risk_score: float, similar_cases: list[dict], current_features: dict
) -> str:
    """Use the LLM to synthesize a predictive maintenance report."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    context = {
        "equipment": {
            "name": equipment.name,
            "station": equipment.station,
            "line_id": equipment.line_id,
            "total_hours": equipment.total_hours,
            "last_maintenance": equipment.last_maintenance.strftime("%Y-%m-%d") if equipment.last_maintenance else "기록 없음",
        },
        "current_state": current_features,
        "similar_past_cases": similar_cases,
        "risk_score": risk_score,
    }

    prompt = f"""
다음 설비의 현재 공정 데이터 패턴과 과거 이상 이력을 분석하여 예지보전 리포트를 작성하세요.

## 분석 데이터
{json.dumps(context, ensure_ascii=False, indent=2)}

## 리포트 형식
**[위험도: {risk_score:.0f}/100]**

**예상 고장 부위:** (추론)

**근거:**
- 현재 패턴 특성
- 유사 과거 사례 참조

**권장 조치:**
- 구체적인 점검 항목과 시기

응답은 한국어로, 수치 근거를 포함하여 간결하게 작성하세요. (200자 이내)
"""

    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model_default,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=400,
        )
        return resp.choices[0].message.content or "리포트 생성 실패"
    except Exception as e:
        logger.exception("LLM report generation failed")
        # Fallback: rule-based summary
        urgency = "🔴 위험" if risk_score >= 70 else ("🟠 주의" if risk_score >= 40 else "✅ 정상")
        return (
            f"**[위험도: {risk_score:.0f}/100 {urgency}]**\n\n"
            f"설비: {equipment.name} ({equipment.station})\n"
            f"현재 상태: 평균={current_features.get('mean', 0):.3f}, "
            f"표준편차={current_features.get('std', 0):.3f}, "
            f"추세={current_features.get('trend_slope', 0):.4f}/tick\n"
            + (f"\n유사 사례 {len(similar_cases)}건 발견" if similar_cases else "")
        )


async def predict_maintenance(equipment_id: int, db: AsyncSession) -> dict:
    """Full predictive maintenance pipeline for one equipment."""
    from app.models.equipment import Equipment, MaintenanceReport

    eq = await db.get(Equipment, equipment_id)
    if eq is None:
        return {"error": f"Equipment {equipment_id} not found"}

    current_features = await _fetch_current_features(db, eq)
    similar_cases = await _fetch_similar_cases(db, eq, current_features)
    risk_score = _risk_score(similar_cases, current_features)
    llm_summary = await _generate_llm_report(eq, risk_score, similar_cases, current_features)

    # Persist report
    similar_date = None
    if similar_cases:
        try:
            similar_date = datetime.strptime(similar_cases[0]["date"], "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone.utc
            )
        except Exception:
            pass

    report = MaintenanceReport(
        generated_at=datetime.now(timezone.utc),
        equipment_id=equipment_id,
        risk_score=risk_score,
        similar_case_date=similar_date,
        llm_summary=llm_summary,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return {
        "equipment_id": equipment_id,
        "equipment_name": eq.name,
        "risk_score": risk_score,
        "similar_cases_count": len(similar_cases),
        "llm_summary": llm_summary,
        "generated_at": report.generated_at.isoformat(),
    }
