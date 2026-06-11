import { AgentChat } from "@/components/AgentChat/AgentChat";

export default function AgentPage() {

  return (
    <div className="p-6 h-full flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold text-white">공정 AI 에이전트</h1>
        <p className="text-sm text-[#6b7280]">
          공정 데이터, 이상 이력, 예지보전을 자연어로 질의합니다.
          Tool Use 기반으로 실시간 DB를 조회하여 답변합니다.
        </p>
      </div>

      <div className="flex-1 max-w-2xl">
        <AgentChat />
      </div>

      {/* Capability cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 max-w-2xl">
        {[
          { title: "공정 데이터 조회", desc: "파라미터 시계열, 현재값, 임계값 비교" },
          { title: "이상 이력 분석", desc: "심각도별 이상 패턴 조회 및 원인 추론" },
          { title: "상관관계 분석", desc: "파라미터 간 Pearson 상관계수 계산" },
          { title: "설비 상태 조회", desc: "정비 이력, 운전 시간, 다음 정비 일정" },
          { title: "예지보전 예측", desc: "고장 위험도 점수 + GPT 리포트 생성" },
          { title: "교대 보고서", desc: "8시간 교대 구간 공정 요약 자동 생성" },
        ].map(({ title, desc }) => (
          <div key={title} className="bg-[#111827] border border-[#1f2937] rounded-xl p-3">
            <div className="text-xs font-semibold text-blue-400 mb-1">{title}</div>
            <div className="text-xs text-[#6b7280]">{desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
