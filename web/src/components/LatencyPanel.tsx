interface LatencyData {
  stt_ms?: number;
  llm_ms?: number;
  llm_internal_ms?: number;
  tool_ms?: number;
  tts_ms?: number;
  total_ms?: number;
  memory_load?: number;
  memory_save?: number;
}

const getColor = (ms: number | undefined, threshold: number): string => {
  if (ms === undefined) return "text-white/25";
  if (ms <= threshold) return "text-emerald-400";
  if (ms <= threshold * 2) return "text-amber-400";
  return "text-red-400";
};

const Metric = ({ label, value, threshold }: { label: string; value?: number; threshold: number }) => (
  <div className="flex flex-col items-center gap-0.5">
    <span className="text-[9px] uppercase tracking-widest text-white/30 font-semibold">{label}</span>
    <span className={`text-xs font-mono font-bold ${getColor(value, threshold)}`}>
      {value !== undefined ? `${Math.round(value)}ms` : "—"}
    </span>
  </div>
);

const LatencyPanel = ({ data }: { data: LatencyData }) => {
  const hasData = Object.values(data).some((v) => v !== undefined);

  if (!hasData) return null;

  return (
    <div className="flex items-center justify-center gap-5 py-2.5 px-5 glass-card-sm">
      <Metric label="STT" value={data.stt_ms} threshold={100} />
      <Metric label="LLM" value={data.llm_ms ?? data.llm_internal_ms} threshold={200} />
      <Metric label="Tool" value={data.tool_ms} threshold={50} />
      <Metric label="TTS" value={data.tts_ms} threshold={100} />
      <div className="h-5 w-px bg-white/10" />
      <Metric label="Total" value={data.total_ms} threshold={450} />
    </div>
  );
};

export default LatencyPanel;
