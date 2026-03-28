import { useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface TranscriptEntry {
  role: "user" | "assistant" | "system";
  text: string;
  timestamp: number;
}

const ROLE_STYLES: Record<string, string> = {
  user: "bg-primary/10 text-foreground border-l-2 border-primary",
  assistant: "bg-accent/10 text-foreground border-l-2 border-accent",
  system: "bg-muted text-muted-foreground text-xs italic",
};

const ROLE_LABELS: Record<string, string> = {
  user: "You",
  assistant: "Agent",
  system: "System",
};
const TranscriptPanel = ({
  entries,
  partialText,
  setPartialText,
  isEditing,
  setIsEditing
}: {
  entries: TranscriptEntry[];
  partialText: string;
  setPartialText?: (text: string) => void;
  isEditing?: boolean;
  setIsEditing?: (val: boolean) => void;
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, partialText]);

  return (
    <ScrollArea className="flex-1 rounded-lg border border-border bg-card p-4">
      <div className="space-y-2">
        {entries.length === 0 && !partialText && (
          <p className="text-muted-foreground text-sm text-center py-8">
            Connect and start speaking to begin your appointment booking.
          </p>
        )}
        {entries.map((entry, i) => (
          <div key={i} className={`rounded-md px-3 py-2 ${ROLE_STYLES[entry.role]}`}>
            <span className="text-xs font-mono text-muted-foreground mr-2">
              {ROLE_LABELS[entry.role]}
            </span>
            {entry.text}
          </div>
        ))}
        {partialText && (
          <div className="rounded-md px-3 py-2 bg-primary/5 text-muted-foreground border-l-2 border-primary/30 flex items-center">
            <span className="text-xs font-mono mr-2">You</span>
            <input 
              type="text"
              value={partialText}
              onChange={(e) => setPartialText && setPartialText(e.target.value)}
              onFocus={() => setIsEditing?.(true)}
              onBlur={() => setIsEditing?.(false)}
              className="flex-1 bg-transparent border-none outline-none focus:ring-0 text-foreground p-0 m-0 w-full"
              placeholder="Correct transcription here..."
              spellCheck="false"
            />
            <span className="inline-block w-1 h-4 bg-primary ml-2 animate-pulse shrink-0" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
};

export default TranscriptPanel;
