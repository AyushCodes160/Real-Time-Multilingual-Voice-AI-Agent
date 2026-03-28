import { useState, useRef, useCallback, useEffect } from "react";
import { Mic, MicOff, Phone, PhoneOff, Globe, Activity, Send, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import TranscriptPanel from "./TranscriptPanel";
import LatencyPanel from "./LatencyPanel";
import StatusBadge from "./StatusBadge";

type ConnectionStatus = "disconnected" | "connecting" | "connected";
type Language = "en" | "hi" | "ta";

interface LatencyData {
  stt_ms?: number;
  llm_ms?: number;
  tool_ms?: number;
  tts_ms?: number;
  total_ms?: number;
}

interface TranscriptEntry {
  role: "user" | "assistant" | "system";
  text: string;
  timestamp: number;
}

const LANG_LABELS: Record<Language, string> = {
  en: "English",
  hi: "हिन्दी",
  ta: "தமிழ்",
};

// For local deployment: "ws://localhost:8000/ws/voice"
// For HuggingFace: "wss://" + window.location.host + "/ws/voice"
const WS_URL = "ws://localhost:8000/ws/voice";

const VoiceAgent = () => {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [isRecording, setIsRecording] = useState(false);
  const [language, setLanguage] = useState<Language>("en");
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [partialText, setPartialText] = useState("");
  const [currentState, setCurrentState] = useState("IDLE");
  const [latency, setLatency] = useState<LatencyData>({});
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);

  const addTranscript = useCallback((role: TranscriptEntry["role"], text: string) => {
    setTranscript((prev) => [...prev, { role, text, timestamp: Date.now() }]);
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus("connecting");
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setStatus("connected");
      addTranscript("system", "Connected to Voice AI Agent");
      ws.send(JSON.stringify({ type: "config", language, patient_phone: "" }));
    };

    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
      } else {
        // Binary audio data — play it
        playAudioChunk(event.data);
      }
    };

    ws.onclose = () => {
      setStatus("disconnected");
      setIsRecording(false);
      addTranscript("system", "Disconnected");
    };

    ws.onerror = () => {
      setStatus("disconnected");
      addTranscript("system", "Connection error — is the server running?");
    };
  }, [language, addTranscript]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    stopRecording();
    setStatus("disconnected");
    setSessionId(null);
  }, []);

  const handleServerMessage = useCallback(
    (msg: any) => {
      switch (msg.type) {
        case "session_start":
          setSessionId(msg.session_id);
          break;
        case "partial":
          if (!isEditing) {
            setPartialText(msg.text);
          }
          break;
        case "transcript":
          setPartialText("");
          addTranscript("user", msg.text);
          break;
        case "response":
          addTranscript("assistant", msg.text);
          setCurrentState(msg.state);
          if (msg.latency) setLatency(msg.latency);
          break;
        case "barge_in":
          addTranscript("system", "⚡ Barge-in detected — TTS interrupted");
          break;
        case "audio_end":
          if (msg.tts_latency_ms) {
            setLatency((prev) => ({ ...prev, tts_ms: msg.tts_latency_ms }));
          }
          break;
        case "config_ack":
          addTranscript("system", `Language set to ${msg.language}`);
          break;
        case "error":
          addTranscript("system", `Error: ${msg.message}`);
          break;
      }
    },
    [addTranscript]
  );

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
      });
      mediaStreamRef.current = stream;

      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(8192, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (wsRef.current?.readyState !== WebSocket.OPEN) return;
        const float32 = e.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32767)));
        }
        wsRef.current.send(int16.buffer);
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
      setIsRecording(true);
    } catch (err) {
      addTranscript("system", "Microphone access denied");
    }
  }, [addTranscript]);

  const stopRecording = useCallback(() => {
    processorRef.current?.disconnect();
    audioContextRef.current?.close();
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    setIsRecording(false);
  }, []);

  const playAudioChunk = useCallback((data: ArrayBuffer) => {
    if (!playbackContextRef.current) {
      playbackContextRef.current = new AudioContext({ sampleRate: 24000 });
    }
    const ctx = playbackContextRef.current;
    const int16 = new Int16Array(data);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768;
    }
    const buffer = ctx.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.start();
  }, []);

  const cycleLanguage = useCallback(() => {
    const langs: Language[] = ["en", "hi", "ta"];
    const next = langs[(langs.indexOf(language) + 1) % langs.length];
    setLanguage(next);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "config", language: next }));
    }
  }, [language]);

  const sendManualMessage = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "send_message", text: partialText.trim() }));
      setPartialText("");
    }
  }, [partialText]);

  const clearBuffer = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "clear_buffer" }));
      setPartialText("");
    }
  }, []);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto p-4 gap-4">
      {/* Header */}
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Activity className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-bold text-foreground">Clinical Voice AI</h1>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={status} state={currentState} />
          {sessionId && (
            <span className="text-xs font-mono text-muted-foreground">
              {sessionId.slice(0, 8)}
            </span>
          )}
        </div>
      </header>

      {/* Transcript */}
      <TranscriptPanel 
        entries={transcript} 
        partialText={partialText} 
        setPartialText={setPartialText} 
        isEditing={isEditing}
        setIsEditing={setIsEditing}
      />

      {/* Latency */}
      <LatencyPanel data={latency} />

      {/* Controls */}
      <footer className="flex items-center justify-center gap-3 py-4">
        <Button
          variant="outline"
          size="icon"
          className="relative pointer-events-none"
          title="Auto-Detect Languages"
        >
          <Globe className="h-4 w-4 text-blue-600" />
          <span className="absolute -bottom-1 -right-1 text-[10px] font-bold bg-blue-600 text-white rounded px-1">
            AUTO
          </span>
        </Button>

        {status === "disconnected" ? (
          <Button onClick={connect} className="gap-2 bg-primary text-primary-foreground hover:bg-primary/90">
            <Phone className="h-4 w-4" /> Connect
          </Button>
        ) : (
          <Button onClick={disconnect} variant="destructive" className="gap-2">
            <PhoneOff className="h-4 w-4" /> Disconnect
          </Button>
        )}

        <Button
          size="icon"
          disabled={status !== "connected"}
          onClick={isRecording ? stopRecording : startRecording}
          className={
            isRecording
              ? "bg-[hsl(var(--recording))] hover:bg-[hsl(var(--recording))]/90 text-primary-foreground animate-pulse-ring"
              : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
          }
        >
          {isRecording ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
        </Button>
        
        <Button
          onClick={clearBuffer}
          disabled={status !== "connected" || !partialText.trim()}
          variant="outline"
          className="gap-2 text-red-500 border-red-500 hover:bg-red-500 hover:text-white"
        >
          <Trash2 className="h-4 w-4" /> Clear
        </Button>
        
        <Button
          onClick={sendManualMessage}
          disabled={status !== "connected" || !partialText.trim()}
          className="gap-2 bg-emerald-600 text-white hover:bg-emerald-700"
        >
          <Send className="h-4 w-4" /> Send Voice
        </Button>
      </footer>
    </div>
  );
};

export default VoiceAgent;
