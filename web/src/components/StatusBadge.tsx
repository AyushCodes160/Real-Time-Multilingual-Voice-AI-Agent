import { Badge } from "@/components/ui/badge";

type ConnectionStatus = "disconnected" | "connecting" | "connected";

const STATUS_STYLES: Record<ConnectionStatus, string> = {
  disconnected: "bg-[hsl(var(--status-disconnected))]/15 text-[hsl(var(--status-disconnected))] border-[hsl(var(--status-disconnected))]/30",
  connecting: "bg-[hsl(var(--latency-warn))]/15 text-[hsl(var(--latency-warn))] border-[hsl(var(--latency-warn))]/30",
  connected: "bg-[hsl(var(--status-connected))]/15 text-[hsl(var(--status-connected))] border-[hsl(var(--status-connected))]/30",
};

const StatusBadge = ({ status, state }: { status: ConnectionStatus; state: string }) => (
  <div className="flex items-center gap-2">
    <Badge variant="outline" className={`text-xs font-mono ${STATUS_STYLES[status]}`}>
      {status === "connected" && (
        <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--status-connected))] mr-1.5 animate-pulse" />
      )}
      {status}
    </Badge>
    {status === "connected" && (
      <Badge variant="outline" className="text-xs font-mono bg-secondary/50 text-secondary-foreground">
        {state}
      </Badge>
    )}
  </div>
);

export default StatusBadge;
