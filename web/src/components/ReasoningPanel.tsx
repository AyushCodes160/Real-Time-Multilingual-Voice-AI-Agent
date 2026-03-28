import { BrainCircuit, Database } from "lucide-react";

export default function ReasoningPanel({ reasoning }: { reasoning?: any }) {
  if (!reasoning || Object.keys(reasoning).length === 0) return null;

  return (
    <div className="mt-3 p-3 rounded-xl bg-[#1e1b4b]/50 border border-purple-500/20 text-xs text-white/60 space-y-2 shrink-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex gap-2 items-center text-purple-300 font-semibold mb-1">
        <BrainCircuit className="w-3.5 h-3.5" /> LLM Reasoning Trace
      </div>
      
      {reasoning.intent && (
        <div className="flex justify-between items-center">
          <span className="text-white/40">Intent:</span> 
          <span className="text-blue-300 font-mono tracking-wide">{reasoning.intent}</span>
        </div>
      )}
      
      {reasoning.extracted_info && Object.keys(reasoning.extracted_info).length > 0 && typeof reasoning.extracted_info === 'object' && (
        <div className="pt-1.5 border-t border-white/5">
          <span className="text-white/40 block mb-1.5">Parsed Entities:</span>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(reasoning.extracted_info).filter(([_, v]) => v).map(([k, v]) => (
               <span key={k} className="px-2 py-0.5 bg-blue-500/10 rounded border border-blue-500/20 text-[10px] text-blue-200 uppercase tracking-wider">
                 {k}: {String(v)}
               </span>
            ))}
          </div>
        </div>
      )}
      
      {reasoning.tool_name && (
        <div className="mt-2 flex items-center justify-between bg-orange-500/10 rounded border border-orange-500/20 overflow-hidden">
           <div className="flex items-center gap-1.5 px-2 py-1.5 bg-orange-500/20 text-orange-300">
             <Database className="w-3 h-3" />
             <span className="font-mono text-[10px]">TOOL</span>
           </div>
           <span className="text-orange-200 px-2 font-mono text-[10px]">{reasoning.tool_name}</span>
        </div>
      )}
    </div>
  );
}
