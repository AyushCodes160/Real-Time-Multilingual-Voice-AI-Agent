import { useEffect, useState } from "react";
import { Calendar, Clock, User, Stethoscope, CheckCircle2, AlertCircle } from "lucide-react";

interface Appointment {
  id: number;
  doctor: string;
  date: string;
  time?: string;
  status: string;
  patient?: string;
}

const AppointmentPanel = ({ refreshTrigger }: { refreshTrigger: number }) => {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAppointments = async () => {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/patient/appointments");
      const data = await res.json();
      setAppointments(data.reverse().slice(0, 5)); // latest 5
    } catch {
      // Server not ready yet
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAppointments();
  }, [refreshTrigger]);

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString("en-IN", {
        weekday: "short", month: "short", day: "numeric",
      });
    } catch { return iso; }
  };

  const formatTime = (iso: string) => {
    try {
      return new Date(iso).toLocaleTimeString("en-IN", {
        hour: "2-digit", minute: "2-digit",
      });
    } catch { return ""; }
  };

  return (
    <div className="flex flex-col glass-card h-full overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 border-b border-white/[0.06] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Calendar className="h-3.5 w-3.5 text-purple-400" />
          <span className="text-[10px] font-semibold uppercase tracking-widest text-white/50">
            Appointments
          </span>
        </div>
        <button
          onClick={fetchAppointments}
          className="text-[10px] text-white/25 hover:text-white/60 transition-colors font-mono"
        >
          refresh
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-3">
        {loading && (
          <div className="flex items-center justify-center h-24">
            <div className="w-5 h-5 rounded-full border-2 border-purple-400 border-t-transparent animate-spin" />
          </div>
        )}

        {!loading && appointments.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 py-12 text-center">
            <AlertCircle className="h-8 w-8 text-white/15" />
            <p className="text-white/25 text-xs max-w-[160px]">
              No appointments yet. Book one using the voice agent.
            </p>
          </div>
        )}

        {appointments.map((appt) => (
          <div
            key={appt.id}
            className="rounded-xl p-4 bg-gradient-to-br from-purple-500/10 to-pink-500/5 border border-purple-500/20 space-y-3 transition-all hover:border-purple-500/40"
          >
            {/* ID + Status */}
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-white/30">#{appt.id}</span>
              <span className={`text-[9px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full ${
                appt.status === "scheduled"
                  ? "bg-green-500/20 text-green-400"
                  : appt.status === "cancelled"
                  ? "bg-red-500/20 text-red-400"
                  : "bg-blue-500/20 text-blue-400"
              }`}>
                {appt.status}
              </span>
            </div>

            {/* Doctor row */}
            <div className="flex items-center gap-2">
              <Stethoscope className="h-3.5 w-3.5 text-purple-400 shrink-0" />
              <span className="text-sm text-white/85 font-medium capitalize">
                Dr. {appt.doctor}
              </span>
            </div>

            {/* Date/Time row (from doctor's slot start_time which comes as ISO) */}
            {appt.date && (
              <div className="flex items-center justify-between text-xs text-white/50">
                <div className="flex items-center gap-1.5">
                  <Calendar className="h-3 w-3 text-white/30" />
                  {formatDate(appt.date)}
                </div>
                <div className="flex items-center gap-1.5">
                  <Clock className="h-3 w-3 text-white/30" />
                  {formatTime(appt.date)}
                </div>
              </div>
            )}

            {appt.status === "scheduled" && (
              <div className="flex items-center gap-1.5 text-[10px] text-green-400/70">
                <CheckCircle2 className="h-3 w-3" />
                Confirmed
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default AppointmentPanel;
