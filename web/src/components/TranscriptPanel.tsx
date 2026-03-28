import { useRef, useEffect } from "react";

interface TranscriptEntry {
  role: "user" | "assistant" | "system";
  text: string;
  timestamp: number;
}

const ROLE_CONFIG: Record<string, { label: string; gradient: string; border: string }> = {
  user: {
    label: "You",
    gradient: "from-purple-500/10 to-pink-500/5",
    border: "border-purple-500/40",
  },
  assistant: {
    label: "Agent",
    gradient: "from-blue-500/10 to-cyan-500/5",
    border: "border-blue-500/40",
  },
  system: {
    label: "System",
    gradient: "from-white/[0.02] to-white/[0.01]",
    border: "border-white/10",
  },
};

const TranscriptPanel = ({
  entries,
  partialText,
  setPartialText,
  isEditing,
  setIsEditing,
}: {
  entries: TranscriptEntry[];
  partialText: string;
  setPartialText?: (text: string) => void;
  isEditing?: boolean;
  setIsEditing?: (val: boolean) => void;
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, partialText]);

  return (
    <div className="flex-1 flex flex-col glass-card overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 border-b border-white/[0.06] flex items-center justify-between">
        <div className="live-transcript-label">LIVE TRANSCRIPT</div>
        <span className="text-[10px] font-mono text-white/25">{entries.length} messages</span>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-2.5">
        {entries.length === 0 && !partialText && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3 py-12">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="rgba(168,85,247,0.6)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" x2="12" y1="19" y2="22"/>
              </svg>
            </div>
            <p className="text-white/30 text-sm max-w-[200px]">
              Connect and start speaking to begin your appointment.
            </p>
          </div>
        )}

        {entries.map((entry, i) => {
          const config = ROLE_CONFIG[entry.role];
          return (
            <div
              key={i}
              className={`rounded-xl px-4 py-3 bg-gradient-to-r ${config.gradient} border-l-2 ${config.border} transition-all duration-300`}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <span className="text-[10px] font-semibold uppercase tracking-wider text-white/35 block mb-1">
                {config.label}
              </span>
              <span className={`text-sm leading-relaxed ${entry.role === 'system' ? 'text-white/40 italic' : 'text-white/85'}`}>
                {entry.text}
              </span>
            </div>
          );
        })}

        {/* Partial / Live input */}
        {partialText && (
          <div className="rounded-xl px-4 py-3 bg-gradient-to-r from-purple-500/5 to-transparent border-l-2 border-purple-400/30 flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-purple-400/50">You</span>
            <input
              type="text"
              value={partialText}
              onChange={(e) => setPartialText && setPartialText(e.target.value)}
              onFocus={() => setIsEditing?.(true)}
              onBlur={() => setIsEditing?.(false)}
              className="flex-1 bg-transparent border-none outline-none focus:ring-0 text-white/80 text-sm p-0 m-0 w-full placeholder:text-white/20"
              placeholder="Correct transcription here..."
              spellCheck="false"
            />
            <span className="inline-block w-0.5 h-4 bg-purple-400 animate-pulse shrink-0 rounded-full" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};

export default TranscriptPanel;
