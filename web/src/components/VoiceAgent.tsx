import { useState, useRef, useCallback, useEffect } from "react";
import { Mic, MicOff, Phone, PhoneOff, Globe, Send, Trash2 } from "lucide-react";
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
const WS_URL = "ws://127.0.0.1:8000/ws/voice";

const WAVEFORM_BARS = 24;

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
    <>
      {/* Animated gradient background */}
      <div className="glass-bg">
        <div className="glass-blob-3" />
      </div>

      {/* Main layout */}
      <div className="relative z-10 flex flex-col h-screen max-w-5xl mx-auto px-6 py-5 gap-5">
        
        {/* ═══ HEADER ═══ */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" x2="12" y1="19" y2="22"/>
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">Clinical Voice AI</h1>
              <p className="text-[11px] text-white/40 font-medium tracking-wide">REAL-TIME MULTILINGUAL AGENT</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={status} state={currentState} />
            {sessionId && (
              <span className="text-[10px] font-mono text-white/30">
                {sessionId.slice(0, 8)}
              </span>
            )}
          </div>
        </header>

        {/* ═══ MAIN CONTENT (2-column on large) ═══ */}
        <div className="flex-1 flex gap-5 min-h-0">
          
          {/* LEFT: Orb + Controls */}
          <div className="flex flex-col items-center justify-center gap-6 w-2/5">
            
            {/* Listening badge */}
            {isRecording && (
              <div className="listening-badge">
                <span className="listening-dot" />
                LISTENING
              </div>
            )}

            {/* Voice Orb */}
            <div className="voice-orb-container">
              <div className={`voice-orb ${isRecording ? 'active' : ''}`} />
              <div className="ripple-ring" />
              <div className="ripple-ring" />
              <div className="ripple-ring" />
            </div>

            {/* Waveform */}
            <div className="waveform-container">
              {Array.from({ length: WAVEFORM_BARS }).map((_, i) => (
                <div
                  key={i}
                  className={`waveform-bar ${isRecording ? 'active' : ''}`}
                  style={{
                    height: isRecording ? undefined : '6px',
                    animationDelay: `${i * 0.05}s`,
                    background: `linear-gradient(to top, #8b5cf6, #ec4899, #60a5fa)`,
                    opacity: 0.5 + Math.sin(i / WAVEFORM_BARS * Math.PI) * 0.5,
                  }}
                />
              ))}
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-center flex-wrap gap-2 z-10">
              {/* Language */}
              <button onClick={cycleLanguage} className="ghost-btn flex items-center gap-2 text-xs px-3 py-2">
                <Globe className="h-3.5 w-3.5 text-blue-400" />
                {LANG_LABELS[language]}
              </button>

              {/* Connect / Disconnect */}
              {status === "disconnected" ? (
                <button onClick={connect} className="gradient-btn flex items-center gap-2 text-xs !px-4 !py-2">
                  <Phone className="h-3.5 w-3.5" /> Connect
                </button>
              ) : (
                <button onClick={disconnect} className="ghost-btn flex items-center gap-2 text-xs px-3 py-2 text-red-400 border-red-400/30">
                  <PhoneOff className="h-3.5 w-3.5" /> End
                </button>
              )}

              {/* Mic */}
              <button
                disabled={status !== "connected"}
                onClick={isRecording ? stopRecording : startRecording}
                className={`w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 shrink-0 ${
                  isRecording
                    ? 'bg-red-500 shadow-lg shadow-red-500/30 animate-pulse-ring'
                    : 'ghost-btn !p-0'
                }`}
              >
                {isRecording ? <MicOff className="h-4 w-4 text-white" /> : <Mic className="h-4 w-4" />}
              </button>
            </div>

            {/* Latency stats */}
            <LatencyPanel data={latency} />
          </div>

          {/* RIGHT: Transcript */}
          <div className="flex-1 flex flex-col min-h-0">
            <TranscriptPanel
              entries={transcript}
              partialText={partialText}
              setPartialText={setPartialText}
              isEditing={isEditing}
              setIsEditing={setIsEditing}
            />

            {/* Send / Clear controls */}
            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={clearBuffer}
                disabled={status !== "connected" || !partialText.trim()}
                className="ghost-btn flex items-center gap-2 text-sm text-red-400"
              >
                <Trash2 className="h-3.5 w-3.5" /> Clear
              </button>
              <button
                onClick={sendManualMessage}
                disabled={status !== "connected" || !partialText.trim()}
                className="gradient-btn flex items-center gap-2 text-sm"
              >
                <Send className="h-3.5 w-3.5" /> Send
              </button>
            </div>
          </div>
        </div>

        {/* ═══ FOOTER ═══ */}
        <footer className="flex items-center justify-between py-3 px-5 glass-card-sm">
          <span className="text-xs text-white/40 font-medium">Voice AI Agent • v2.0</span>
          <span className="text-xs font-semibold gradient-text tracking-wide">REAL-TIME INTELLIGENCE</span>
        </footer>
      </div>
    </>
  );
};

export default VoiceAgent;
