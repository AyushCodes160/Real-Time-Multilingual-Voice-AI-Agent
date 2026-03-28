type ConnectionStatus = "disconnected" | "connecting" | "connected";

const STATUS_CONFIG: Record<ConnectionStatus, { color: string; bg: string; border: string }> = {
  disconnected: {
    color: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/20",
  },
  connecting: {
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
  },
  connected: {
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
  },
};

const StatusBadge = ({ status, state }: { status: ConnectionStatus; state: string }) => {
  const config = STATUS_CONFIG[status];

  return (
    <div className="flex items-center gap-2">
      <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wider border ${config.bg} ${config.color} ${config.border}`}>
        {status === "connected" && (
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        )}
        {status === "connecting" && (
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        )}
        {status}
      </div>
      {status === "connected" && (
        <div className="px-2.5 py-1 rounded-full text-[10px] font-mono font-semibold bg-white/[0.04] text-white/40 border border-white/[0.06]">
          {state}
        </div>
      )}
    </div>
  );
};

export default StatusBadge;
