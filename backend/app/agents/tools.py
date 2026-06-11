"""MES agent tool definitions using Pydantic AI function calling."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from pydantic_ai import RunContext
from sqlalchemy import select, text

from app.agents.deps import MesDeps
from app.models.anomaly import AnomalyEvent
from app.models.equipment import Equipment, MaintenanceReport
from app.services.simulator import AnomalyType

logger = logging.getLogger(__name__)


async def query_process_data(
    ctx: RunContext[MesDeps],
    line_id: int,
    station: str,
    param: str,
    minutes: int = 30,
) -> str:
    """공정 라인의 특정 파라미터 시계열 데이터를 조회합니다.

    Args:
        line_id: 라인 번호 (1 또는 2)
        station: 공정 스테이션 (coating, calendering, slitting, winding)
        param: 파라미터명 (예: tension_supply, coating_thickness)
        minutes: 조회 기간 (분, 기본 30분)
    """
    if ctx.deps.db is None:
        return "DB 연결 없음"
    try:
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        from app.models.process import ProcessData
        import numpy as np
        rows = await ctx.deps.db.execute(
            select(ProcessData)
            .where(
                ProcessData.line_id == line_id,
                ProcessData.station == station,
                ProcessData.param == param,
                ProcessData.time >= since,
            )
            .order_by(ProcessData.time.desc())
            .limit(200)
        )
        data = [{"time": r.time.isoformat(), "value": r.value} for r in rows.scalars()]
        if not data:
            return f"Line {line_id} {station}.{param}: 최근 {minutes}분 데이터 없음"

        values = [d["value"] for d in data]
        mean_v, std_v = float(np.mean(values)), float(np.std(values))
        min_v, max_v = min(values), max(values)
        latest = data[0]["value"]

        from app.services.simulator import STATION_PARAMS
        thresholds: dict = {}
        for p in STATION_PARAMS.get(station, []):
            if p.name == param:
                thresholds = {"low": p.low, "high": p.high}
                break

        status = "정상"
        if thresholds:
            if latest < thresholds["low"] * 0.9 or latest > thresholds["high"] * 1.1:
                status = "⚠️ 위험"
            elif latest < thresholds["low"] or latest > thresholds["high"]:
                status = "🟡 주의"

        return (
            f"[Line {line_id} / {station} / {param}] 최근 {minutes}분 ({len(data)}개 샘플)\n"
            f"- 현재값: {latest:.3f} | 평균: {mean_v:.3f} | 표준편차: {std_v:.3f}\n"
            f"- 범위: {min_v:.3f} ~ {max_v:.3f}\n"
            f"- 정상 범위: {thresholds.get('low', 'N/A')} ~ {thresholds.get('high', 'N/A')}\n"
            f"- 상태: {status}"
        )
    except Exception as exc:
        logger.exception("query_process_data error")
        return f"데이터 조회 오류: {exc}"


async def get_anomaly_history(
    ctx: RunContext[MesDeps],
    line_id: int | None = None,
    severity: str | None = None,
    hours: int = 24,
) -> str:
    """이상 탐지 이력을 조회합니다.

    Args:
        line_id: 라인 번호 필터 (None이면 전체)
        severity: 심각도 필터 (INFO/WARNING/CRITICAL, None이면 전체)
        hours: 조회 기간 (시간)
    """
    if ctx.deps.db is None:
        return "DB 연결 없음"
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        q = select(AnomalyEvent).where(AnomalyEvent.detected_at >= since)
        if line_id is not None:
            q = q.where(AnomalyEvent.line_id == line_id)
        if severity:
            q = q.where(AnomalyEvent.severity == severity.upper())
        q = q.order_by(AnomalyEvent.detected_at.desc()).limit(50)

        rows = await ctx.deps.db.execute(q)
        events = list(rows.scalars())
        if not events:
            return f"최근 {hours}시간 이상 이벤트 없음"

        counts: dict[str, int] = {}
        for e in events:
            counts[e.severity] = counts.get(e.severity, 0) + 1

        lines_out = []
        for e in events[:10]:
            lines_out.append(
                f"- [{e.severity}] {e.detected_at.strftime('%m/%d %H:%M')} "
                f"Line{e.line_id} {e.station}.{e.param} = {e.value:.3f} (패턴: {e.pattern_type})"
            )

        summary = " | ".join(f"{k}: {v}건" for k, v in counts.items())
        return f"최근 {hours}시간 이상 이력 (총 {len(events)}건: {summary})\n" + "\n".join(lines_out)
    except Exception as exc:
        logger.exception("get_anomaly_history error")
        return f"이상 이력 조회 오류: {exc}"


async def analyze_correlation(
    ctx: RunContext[MesDeps],
    line_id: int = 1,
    station: str = "coating",
    window_minutes: int = 30,
) -> str:
    """공정 파라미터 간 상관관계를 분석합니다.

    Args:
        line_id: 라인 번호
        station: 분석할 스테이션
        window_minutes: 분석 기간 (분)
    """
    if ctx.deps.db is None:
        return "DB 연결 없음"
    try:
        from app.services.correlation import compute_correlation_matrix
        results = await compute_correlation_matrix(ctx.deps.db, line_id, station, window_minutes)
        if not results:
            return f"Line {line_id} {station}: 충분한 데이터 없음 (30분 이상 누적 필요)"

        strong = [r for r in results if abs(r["r"]) >= 0.6 and r["p_value"] < 0.05]
        lines_out = [f"Line {line_id} {station} 상관관계 분석 (상위 {min(5, len(results))}개):"]
        for r in results[:5]:
            sig = "✓" if r["p_value"] < 0.05 else "✗"
            lines_out.append(
                f"  {r['param_a']} ↔ {r['param_b']}: r={r['r']:.3f} {sig} — {r['interpretation']}"
            )
        if strong:
            lines_out.append(f"\n⚠️ 강한 상관 {len(strong)}쌍 발견 — 공정 변수 간 영향 주의 필요")
        return "\n".join(lines_out)
    except Exception as exc:
        logger.exception("analyze_correlation error")
        return f"상관관계 분석 오류: {exc}"


async def get_equipment_status(
    ctx: RunContext[MesDeps],
    equipment_id: int,
) -> str:
    """설비 상태와 정비 이력을 조회합니다.

    Args:
        equipment_id: 설비 ID
    """
    if ctx.deps.db is None:
        return "DB 연결 없음"
    try:
        eq = await ctx.deps.db.get(Equipment, equipment_id)
        if eq is None:
            return f"설비 ID {equipment_id} 없음 (seed.py를 먼저 실행하세요)"

        now = datetime.now(timezone.utc)
        days_since = (now - eq.last_maintenance).days if eq.last_maintenance else None
        days_until = (eq.next_maintenance - now).days if eq.next_maintenance else None

        urgency = ""
        if days_until is not None:
            if days_until < 0:
                urgency = "🔴 정비 기한 초과!"
            elif days_until <= 3:
                urgency = "🟠 긴급 정비 필요"
            elif days_until <= 7:
                urgency = "🟡 정비 임박"

        return (
            f"[설비: {eq.name}] Line {eq.line_id} / {eq.station}\n"
            f"- 누적 운전시간: {eq.total_hours:.0f}h\n"
            f"- 마지막 정비: {eq.last_maintenance.strftime('%Y-%m-%d') if eq.last_maintenance else '기록 없음'}"
            + (f" ({days_since}일 전)" if days_since else "") + "\n"
            f"- 다음 정비 예정: {eq.next_maintenance.strftime('%Y-%m-%d') if eq.next_maintenance else '미정'}"
            + (f" ({days_until}일 후)" if days_until else "") + "\n"
            f"- 상태: {urgency or '✅ 정상'}"
        )
    except Exception as exc:
        logger.exception("get_equipment_status error")
        return f"설비 조회 오류: {exc}"


async def predict_failure_risk(
    ctx: RunContext[MesDeps],
    equipment_id: int,
) -> str:
    """설비의 고장 위험도를 예측하고 예지보전 리포트를 반환합니다.

    Args:
        equipment_id: 설비 ID
    """
    if ctx.deps.db is None:
        return "DB 연결 없음"
    from app.services.predictive import predict_maintenance
    try:
        report = await predict_maintenance(equipment_id, ctx.deps.db)
        return report.get("llm_summary", "리포트 생성 실패")
    except Exception as e:
        return f"예측 오류: {e}"


async def generate_shift_report(
    ctx: RunContext[MesDeps],
    line_id: int,
    hours: int = 8,
) -> str:
    """교대 근무 기간의 공정 요약 보고서를 생성합니다.

    Args:
        line_id: 라인 번호
        hours: 교대 기간 (시간, 기본 8시간)
    """
    if ctx.deps.db is None:
        return "DB 연결 없음"
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        rows = await ctx.deps.db.execute(
            text("""
                SELECT severity, COUNT(*) as cnt
                FROM anomaly_events
                WHERE line_id = :line AND detected_at >= :since
                GROUP BY severity
            """),
            {"line": line_id, "since": since},
        )
        severity_counts = {r[0]: r[1] for r in rows}

        metrics_summary = ""
        if ctx.deps.redis:
            critical_params = [
                ("coating", "tension_supply"),
                ("coating", "coating_thickness"),
                ("calendering", "roll_pressure"),
            ]
            param_lines = []
            for station, param in critical_params:
                raw = await ctx.deps.redis.hget("process:latest", f"line:{line_id}:{station}:{param}")
                if raw:
                    d = json.loads(raw)
                    param_lines.append(f"  {station}.{param}: {d['value']:.3f} {d['unit']}")
            if param_lines:
                metrics_summary = "\n현재 주요 파라미터:\n" + "\n".join(param_lines)

        total_anomalies = sum(severity_counts.values())
        critical = severity_counts.get("CRITICAL", 0)
        warning = severity_counts.get("WARNING", 0)
        status = "✅ 양호" if critical == 0 and warning <= 2 else ("⚠️ 주의 필요" if critical == 0 else "🔴 조치 필요")

        return (
            f"[Line {line_id} 교대 보고서] 최근 {hours}시간\n"
            f"- 전체 이상 탐지: {total_anomalies}건 (CRITICAL: {critical}, WARNING: {warning})\n"
            f"- 공정 상태: {status}"
            + metrics_summary
        )
    except Exception as exc:
        logger.exception("generate_shift_report error")
        return f"교대 보고서 생성 오류: {exc}"


async def inject_test_anomaly(
    ctx: RunContext[MesDeps],
    anomaly_type: str,
    line_id: int = 1,
) -> str:
    """테스트용 이상 시나리오를 주입합니다 (데모/시연용).

    Args:
        anomaly_type: 이상 유형 (TENSION_SPIKE/THICKNESS_DRIFT/TEMP_DEVIATION/VISCOSITY_RISE/PRESSURE_OSC)
        line_id: 라인 번호
    """
    if ctx.deps.simulator is None:
        return "시뮬레이터 연결 없음"
    try:
        atype = AnomalyType(anomaly_type.upper())
        result = ctx.deps.simulator.inject_anomaly(atype, line_id)  # type: ignore[attr-defined]
        return f"이상 주입 완료: {atype} → Line {line_id} {result['station']}.{result['param']}"
    except ValueError:
        valid = [e.value for e in AnomalyType]
        return f"유효하지 않은 이상 유형. 가능한 값: {valid}"


MES_TOOLS = (
    query_process_data,
    get_anomaly_history,
    analyze_correlation,
    get_equipment_status,
    predict_failure_risk,
    generate_shift_report,
    inject_test_anomaly,
)
