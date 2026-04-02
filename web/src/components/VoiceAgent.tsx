import { useState, useRef, useCallback, useEffect } from "react";
import { Mic, MicOff, Phone, PhoneOff, Globe, Send, Trash2, Bell } from "lucide-react";
import TranscriptPanel from "./TranscriptPanel";
import LatencyPanel from "./LatencyPanel";
import StatusBadge from "./StatusBadge";
import AppointmentPanel from "./AppointmentPanel";
import ReasoningPanel from "./ReasoningPanel";


type ConnectionStatus = "disconnected" | "connecting" | "connected";
type Language = "en" | "hi" | "ta";

interface LoggedInUser {
  patient_id: number;
  name: string;
  phone: string;
  language?: Language;
}

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

const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";
const WS_URL = isLocal ? "ws://127.0.0.1:7860/ws/voice" : `${WS_PROTOCOL}//${window.location.host}/ws/voice`;
const API_BASE = isLocal ? "" : `${window.location.protocol}//${window.location.host}`;

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
  const [apptRefresh, setApptRefresh] = useState(0);
  const [latestReasoning, setLatestReasoning] = useState<any>(null);
  const [user, setUser] = useState<LoggedInUser | null>(null);
  const [loginName, setLoginName] = useState("");
  const [loginPhone, setLoginPhone] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);


  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const activeSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const nextPlayTimeRef = useRef<number>(0);
  const audioQueueRef = useRef<Promise<void>>(Promise.resolve());

  const addTranscript = useCallback((role: TranscriptEntry["role"], text: string) => {
    setTranscript((prev) => [...prev, { role, text, timestamp: Date.now() }]);
  }, []);

  useEffect(() => {
    const raw = localStorage.getItem("voice_agent_user");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as LoggedInUser;
      if (parsed?.patient_id && parsed?.name && parsed?.phone) {
        setUser(parsed);
        if (parsed.language) setLanguage(parsed.language);
      }
    } catch {
      localStorage.removeItem("voice_agent_user");
    }
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
      ws.send(
        JSON.stringify({
          type: "config",
          language,
          patient_id: user?.patient_id,
          patient_name: user?.name,
          patient_phone: user?.phone,
        })
      );
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
  }, [language, addTranscript, user]);

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
          addTranscript("assistant", msg.text || "");
          setCurrentState(msg.state || "ACTIVE");
          if (msg.latency) setLatency(msg.latency);
          if (msg.reasoning) setLatestReasoning(msg.reasoning);
          
          // Trigger Appointment refresh if text indicates sub-actions, or payload explicitly has booking/cancellation
          const txt = (msg.text || "").toLowerCase();
          if (
            txt.includes("booked") || 
            txt.includes("confirmed") || 
            txt.includes("cancelled") || 
            txt.includes("rescheduled") ||
            msg.reasoning?.booking?.success ||
            msg.reasoning?.cancelled
          ) {
            setApptRefresh((r) => r + 1);
          }
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

  const stopPlayback = useCallback(() => {
    activeSourcesRef.current.forEach((src) => {
      try { src.stop(); } catch { /* already stopped */ }
    });
    activeSourcesRef.current.clear();
    nextPlayTimeRef.current = 0;
    audioQueueRef.current = Promise.resolve();
    if (playbackContextRef.current) {
      playbackContextRef.current.close().catch(() => {});
      playbackContextRef.current = null;
    }
  }, []);

  const startRecording = useCallback(async () => {
    try {
      // Stop any TTS audio that is currently playing (barge-in)
      stopPlayback();

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
  }, [addTranscript, stopPlayback]);

  const stopRecording = useCallback(() => {
    try { processorRef.current?.disconnect(); } catch (e) { console.error("Error disconnecting processor", e); }
    try { audioContextRef.current?.close(); } catch (e) { console.error("Error closing audio context", e); }
    try { mediaStreamRef.current?.getTracks().forEach((t) => t.stop()); } catch (e) { console.error("Error stopping tracks", e); }
    setIsRecording(false);
  }, []);

  const playAudioChunk = useCallback((data: ArrayBuffer) => {
    if (!playbackContextRef.current) {
      playbackContextRef.current = new AudioContext({ sampleRate: 24000 });
      nextPlayTimeRef.current = 0;
    }
    const ctx = playbackContextRef.current;
    
    audioQueueRef.current = audioQueueRef.current.then(() => {
      return new Promise<void>((resolve) => {
        ctx.decodeAudioData(data.slice(0), (buffer) => {
          const source = ctx.createBufferSource();
          source.buffer = buffer;
          source.connect(ctx.destination);
          activeSourcesRef.current.add(source);
          source.onended = () => activeSourcesRef.current.delete(source);
          
          const currentTime = ctx.currentTime;
          let startTime = Math.max(currentTime, nextPlayTimeRef.current);
          source.start(startTime);
          nextPlayTimeRef.current = startTime + buffer.duration;
          resolve();
        }, (err) => {
          console.error("Failed to decode audio stream from TTS", err);
          resolve();
        });
      });
    });
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
      stopRecording();
    }
  }, [partialText, stopRecording]);

  const clearBuffer = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "clear_buffer" }));
      setPartialText("");
    }
  }, []);

  const triggerCampaign = async () => {
    if (!user?.patient_id) return;
    try {
      await fetch(`${API_BASE}/api/patient/${user.patient_id}/trigger-campaign`, { method: "POST" });
      connect();
    } catch (e) {
      console.error("Failed to trigger campaign", e);
    }
  };

  const login = useCallback(async () => {
    const name = loginName.trim();
    const phone = loginPhone.trim();
    if (!name || !phone) return;

    setLoginLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/patient/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, phone, language }),
      });

      if (!res.ok) {
        throw new Error("Login failed");
      }

      const data = await res.json();
      const loggedIn: LoggedInUser = {
        patient_id: data.patient_id,
        name: data.name,
        phone: data.phone,
        language: (data.language as Language) || language,
      };

      setUser(loggedIn);
      setLanguage(loggedIn.language || "en");
      localStorage.setItem("voice_agent_user", JSON.stringify(loggedIn));
      setTranscript([
        {
          role: "system",
          text: `Welcome ${loggedIn.name}. You are logged in.`,
          timestamp: Date.now(),
        },
      ]);
    } catch {
      addTranscript("system", "Login failed. Please check your name and phone.");
    } finally {
      setLoginLoading(false);
    }
  }, [loginName, loginPhone, language, addTranscript]);

  const logout = useCallback(() => {
    disconnect();
    setUser(null);
    localStorage.removeItem("voice_agent_user");
    setTranscript([]);
    setPartialText("");
    setCurrentState("IDLE");
  }, [disconnect]);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="glass-card w-full max-w-md p-6 space-y-4">
          <h1 className="text-xl font-bold text-white">Login</h1>
          <p className="text-sm text-white/60">Sign in so the agent can personalize conversations with your name.</p>
          <input
            value={loginName}
            onChange={(e) => setLoginName(e.target.value)}
            placeholder="Full name"
            className="w-full rounded-lg bg-white/5 border border-white/15 px-3 py-2 text-sm text-white placeholder:text-white/35 outline-none"
          />
          <input
            value={loginPhone}
            onChange={(e) => setLoginPhone(e.target.value)}
            placeholder="Phone number"
            className="w-full rounded-lg bg-white/5 border border-white/15 px-3 py-2 text-sm text-white placeholder:text-white/35 outline-none"
          />
          <button
            onClick={login}
            disabled={loginLoading || !loginName.trim() || !loginPhone.trim()}
            className="gradient-btn w-full text-sm"
          >
            {loginLoading ? "Signing in..." : "Login"}
          </button>
        </div>
      </div>
    );
  }

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
              <p className="text-[11px] text-white/60">Signed in as {user.name}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={logout} className="ghost-btn text-xs px-2 py-1">Logout</button>
            <StatusBadge status={status} state={currentState} />
            {sessionId && (
              <span className="text-[10px] font-mono text-white/30">
                {sessionId.slice(0, 8)}
              </span>
            )}
          </div>
        </header>

        {/* ═══ MAIN CONTENT (3-column) ═══ */}
        <div className="flex-1 grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_minmax(0,2fr)] gap-5 min-h-0">
          
          {/* LEFT: Orb + Controls */}
          <div className="flex flex-col items-center justify-center gap-6">
            
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
                <>
                  <button onClick={connect} className="gradient-btn flex items-center gap-2 text-xs !px-4 !py-2 shrink-0">
                    <Phone className="h-3.5 w-3.5" /> Connect
                  </button>
                  <button onClick={triggerCampaign} className="ghost-btn flex items-center gap-2 text-xs !px-3 !py-2 text-purple-400 border-purple-400/30 overflow-hidden shrink-0">
                    <Bell className="h-3.5 w-3.5" /> Campaign
                  </button>
                </>
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

          {/* CENTER: Transcript + Reasoning */}
          <div className="flex flex-col min-h-0">
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
            
            <ReasoningPanel reasoning={latestReasoning} />
          </div>

          {/* RIGHT: Appointment Panel */}
          <AppointmentPanel refreshTrigger={apptRefresh} patientId={user.patient_id} />
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
