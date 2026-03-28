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

const getColor = (ms: number | undefined, threshold: number) => {
  if (ms === undefined) return "text-muted-foreground";
  if (ms <= threshold) return "text-[hsl(var(--latency-good))]";
  if (ms <= threshold * 2) return "text-[hsl(var(--latency-warn))]";
  return "text-[hsl(var(--latency-bad))]";
};

const Metric = ({ label, value, threshold }: { label: string; value?: number; threshold: number }) => (
  <div className="flex flex-col items-center">
    <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</span>
    <span className={`text-sm font-mono font-semibold ${getColor(value, threshold)}`}>
      {value !== undefined ? `${Math.round(value)}ms` : "—"}
    </span>
  </div>
);

const LatencyPanel = ({ data }: { data: LatencyData }) => {
  const hasData = Object.values(data).some((v) => v !== undefined);

  if (!hasData) return null;

  return (
    <div className="flex items-center justify-center gap-6 py-2 px-4 rounded-lg bg-muted/50 border border-border">
      <Metric label="STT" value={data.stt_ms} threshold={100} />
      <Metric label="LLM" value={data.llm_ms ?? data.llm_internal_ms} threshold={200} />
      <Metric label="Tool" value={data.tool_ms} threshold={50} />
      <Metric label="TTS" value={data.tts_ms} threshold={100} />
      <div className="h-6 w-px bg-border" />
      <Metric label="Total" value={data.total_ms} threshold={450} />
    </div>
  );
};

export default LatencyPanel;
