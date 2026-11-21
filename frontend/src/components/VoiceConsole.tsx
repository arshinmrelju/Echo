import React, { useCallback, useRef, useState } from 'react';
import {
  AlertTriangle,
  Mic,
  MicOff,
  Power,
  Radio,
  Settings2,
  ShieldCheck,
  Square,
  Timer,
  Volume2,
  X,
} from 'lucide-react';
import { VoiceMode, VoiceState, VoiceStatus, VoiceTranscript } from '../types';
import { VoiceOrb } from './VoiceOrb';

export interface VoiceNotice {
  kind: 'info' | 'wake' | 'error' | 'interrupted';
  text: string;
}

interface VoiceConsoleProps {
  status: VoiceStatus | null;
  level: number;
  transcript: VoiceTranscript | null;
  notice: VoiceNotice | null;
  isConnected: boolean;
  onStart: () => void;
  onStop: () => void;
  onMute: () => void;
  onUnmute: () => void;
  onStopSpeaking: () => void;
  onDismiss: () => void;
  onOpenSettings: () => void;
  onModeChange: (mode: VoiceMode) => void;
  onPttStart: () => void;
  onPttStop: () => void;
  onClose: () => void;
}

const MODES: { id: VoiceMode; label: string; hint: string }[] = [
  { id: 'push_to_talk', label: 'PUSH', hint: 'Hold to talk' },
  { id: 'wake_word', label: 'WAKE', hint: 'Say the wake word' },
  { id: 'continuous', label: 'LIVE', hint: 'Open conversation' },
];

const STATE_LABEL: Record<VoiceState, string> = {
  idle: 'READY',
  listening: 'LISTENING',
  processing: 'TRANSCRIBING',
  speaking: 'SPEAKING',
  muted: 'MUTED',
  error: 'FAULT',
};

const stateAccent = (state: VoiceState) => {
  switch (state) {
    case 'listening':
    case 'speaking':
      return 'text-echo-cyan';
    case 'processing':
      return 'text-echo-blue';
    case 'error':
      return 'text-echo-danger';
    case 'muted':
      return 'text-echo-muted';
    default:
      return 'text-echo-cyan-dim';
  }
};

const LevelMeter: React.FC<{ level: number; active: boolean; muted: boolean }> = ({
  level,
  active,
  muted,
}) => {
  const bars = 32;
  const lit = Math.round(Math.max(0, Math.min(1, level)) * bars);
  return (
    <div className="flex items-end gap-[3px] h-7" aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => {
        const height = 4 + Math.round((i % 8) * 1.4);
        const on = active && !muted && i < lit;
        return (
          <span
            key={i}
            className={`w-[3px] rounded-sm transition-colors duration-75 ${
              on ? 'bg-echo-cyan' : 'bg-echo-border'
            }`}
            style={{ height: `${height + 4}px` }}
          />
        );
      })}
    </div>
  );
};

export const VoiceConsole: React.FC<VoiceConsoleProps> = ({
  status,
  level,
  transcript,
  notice,
  isConnected,
  onStart,
  onStop,
  onMute,
  onUnmute,
  onStopSpeaking,
  onDismiss,
  onOpenSettings,
  onModeChange,
  onPttStart,
  onPttStop,
  onClose,
}) => {
  const [holding, setHolding] = useState(false);
  const holdRef = useRef(false);

  const running = status?.running ?? false;
  const muted = status?.muted ?? false;
  const mode = status?.mode ?? 'wake_word';
  const state: VoiceState = !status ? 'muted' : muted ? 'muted' : status.state;
  const speaking = status?.speaking ?? false;
  const safeLevel = muted ? 0 : level;

  const startHold = useCallback(() => {
    if (holdRef.current) return;
    holdRef.current = true;
    setHolding(true);
    onPttStart();
  }, [onPttStart]);

  const endHold = useCallback(() => {
    if (!holdRef.current) return;
    holdRef.current = false;
    setHolding(false);
    onPttStop();
  }, [onPttStop]);

  const transcriptText = transcript?.text?.trim() ?? '';
  const showCaret = Boolean(transcript?.isPartial && transcriptText);

  const idleHint = () => {
    if (!isConnected) return 'Daemon offline — voice is unavailable.';
    if (!running) return 'Microphone closed. ECHO cannot hear anything until you enable it.';
    if (mode === 'wake_word') return `Say "${status?.wake_word ?? 'echo'}" to start a turn.`;
    if (mode === 'push_to_talk') return 'Hold the talk pad, then speak.';
    return 'Listening — speak freely. A pause ends the turn.';
  };

  return (
    <section className="border-t border-echo-border bg-[#070A0F] select-none">
      {/* Header rail */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-echo-border/60 bg-[#05070A]">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] tracking-[0.22em] text-echo-muted">VOICE / I-O</span>
          <span className="h-3 w-px bg-echo-border" />
          <span className={`font-mono text-[10px] tracking-wider ${running ? 'text-echo-cyan' : 'text-echo-muted'}`}>
            {running ? 'CHANNEL OPEN' : 'CHANNEL CLOSED'}
          </span>
          <span className="h-3 w-px bg-echo-border" />
          <span className={`font-mono text-[10px] tracking-wider ${muted ? 'text-echo-warning' : running ? 'text-echo-text' : 'text-echo-muted'}`}>
            {muted ? 'MIC MUTED' : running ? 'MIC OPEN' : 'MIC CLOSED'}
          </span>
          {running && mode === 'wake_word' && (
            <>
              <span className="h-3 w-px bg-echo-border" />
              <span className="font-mono text-[10px] tracking-wider text-echo-muted flex items-center gap-1">
                <Radio className="w-3 h-3 text-echo-cyan-dim" />
                WAKE "{status?.wake_word?.toUpperCase()}"
              </span>
            </>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded text-echo-muted hover:text-white hover:bg-echo-border transition-colors"
          title="Hide voice console (does not close the microphone)"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="px-4 py-3 flex items-stretch gap-4">
        {/* Orb */}
        <div className="flex flex-col items-center justify-center w-[104px] flex-shrink-0">
          <VoiceOrb state={state} level={safeLevel} size={80} muted={muted} offline={!isConnected} />
          <span className={`mt-1 font-mono text-[10px] tracking-[0.18em] ${stateAccent(state)}`}>
            {STATE_LABEL[state]}
          </span>
        </div>

        {/* Center readout */}
        <div className="flex-1 min-w-0 flex flex-col justify-center gap-2">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex rounded-md border border-echo-border overflow-hidden">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  onClick={() => onModeChange(m.id)}
                  title={m.hint}
                  className={`px-2.5 py-1 font-mono text-[10px] tracking-wider transition-colors border-r last:border-r-0 border-echo-border ${
                    mode === m.id
                      ? 'bg-echo-cyan/15 text-echo-cyan'
                      : 'text-echo-muted hover:text-gray-200 hover:bg-[#0F1420]'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>

            <LevelMeter level={safeLevel} active={running && !muted} muted={muted} />

            <span className="font-mono text-[10px] text-echo-muted flex items-center gap-1">
              <Timer className="w-3 h-3" />
              {status?.stt_latency_ms != null ? `${Math.round(status.stt_latency_ms)} ms` : '— ms'}
            </span>
            {status?.turns_completed != null && (
              <span className="font-mono text-[10px] text-echo-muted">
                TURNS {status.turns_completed}
              </span>
            )}
          </div>

          {/* Transcript */}
          <div className="min-h-[38px] rounded-md border border-echo-border/70 bg-[#0B0E14] px-3 py-2 flex items-center">
            {transcriptText ? (
              <p className={`text-sm leading-snug break-words ${transcript?.isPartial ? 'text-echo-muted italic' : 'text-echo-text'}`}>
                {transcriptText}
                {showCaret && <span className="voice-caret ml-0.5 text-echo-cyan">▍</span>}
              </p>
            ) : transcript?.dropped ? (
              <p className="text-xs text-echo-warning">No speech recognised. Try again, a little closer to the microphone.</p>
            ) : (
              <p className="text-xs text-echo-muted">{idleHint()}</p>
            )}
          </div>

          {/* Notice / privacy line */}
          <div className="flex items-center justify-between gap-3 text-[10px] font-mono">
            <div className="min-w-0 flex items-center gap-1.5 truncate">
              {notice ? (
                <>
                  {notice.kind === 'error' ? (
                    <AlertTriangle className="w-3 h-3 text-echo-danger flex-shrink-0" />
                  ) : notice.kind === 'wake' ? (
                    <Radio className="w-3 h-3 text-echo-cyan flex-shrink-0" />
                  ) : (
                    <ShieldCheck className="w-3 h-3 text-echo-cyan-dim flex-shrink-0" />
                  )}
                  <span
                    className={
                      notice.kind === 'error'
                        ? 'text-echo-danger truncate'
                        : notice.kind === 'wake'
                        ? 'text-echo-cyan truncate'
                        : 'text-echo-muted truncate'
                    }
                  >
                    {notice.text}
                  </span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-3 h-3 text-echo-cyan-dim flex-shrink-0" />
                  <span className="text-echo-muted truncate">
                    {status?.save_recordings
                      ? `Debug recordings on · ${status.recordings_saved} stored`
                      : 'Raw audio stays in memory · nothing written to disk'}
                  </span>
                </>
              )}
            </div>
            {status?.last_error && !notice && (
              <span className="text-echo-danger truncate max-w-[40%]" title={status.last_error}>
                {status.last_error}
              </span>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="flex flex-col justify-center gap-1.5 w-[150px] flex-shrink-0">
          {!running ? (
            <button
              onClick={onStart}
              disabled={!isConnected}
              className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-echo-cyan/15 border border-echo-cyan/50 text-echo-cyan text-xs font-semibold hover:bg-echo-cyan/25 transition-colors disabled:opacity-40"
            >
              <Power className="w-3.5 h-3.5" />
              Enable mic
            </button>
          ) : muted ? (
            <button
              onClick={onUnmute}
              className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-echo-warning/10 border border-echo-warning/40 text-echo-warning text-xs font-semibold hover:bg-echo-warning/20 transition-colors"
            >
              <Mic className="w-3.5 h-3.5" />
              Unmute mic
            </button>
          ) : (
            <button
              onClick={onMute}
              className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-echo-border bg-[#0F1420] text-gray-300 text-xs hover:border-echo-warning/50 hover:text-echo-warning transition-colors"
            >
              <MicOff className="w-3.5 h-3.5" />
              Mute mic
            </button>
          )}

          <div className="flex gap-1.5">
            <button
              onClick={onStopSpeaking}
              disabled={!speaking}
              className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md border border-echo-border text-[10px] font-mono uppercase tracking-wider text-echo-muted hover:text-echo-danger hover:border-echo-danger/40 transition-colors disabled:opacity-30 disabled:hover:text-echo-muted disabled:hover:border-echo-border"
              title="Stop ECHO speaking"
            >
              <Square className="w-3 h-3" />
              Stop
            </button>
            <button
              onClick={onOpenSettings}
              className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md border border-echo-border text-[10px] font-mono uppercase tracking-wider text-echo-muted hover:text-echo-cyan hover:border-echo-cyan/40 transition-colors"
              title="Voice settings"
            >
              <Settings2 className="w-3 h-3" />
              Setup
            </button>
          </div>

          <div className="flex gap-1.5">
            {mode === 'continuous' && running && (
              <button
                onClick={onDismiss}
                className="flex-1 px-2 py-1.5 rounded-md border border-echo-border text-[10px] font-mono uppercase tracking-wider text-echo-muted hover:text-echo-warning hover:border-echo-warning/40 transition-colors"
                title="End the continuous conversation"
              >
                Dismiss
              </button>
            )}
            {running && (
              <button
                onClick={onStop}
                className="flex-1 px-2 py-1.5 rounded-md border border-echo-border text-[10px] font-mono uppercase tracking-wider text-echo-muted hover:text-echo-danger hover:border-echo-danger/40 transition-colors"
                title="Close the microphone"
              >
                Off
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Push-to-talk pad */}
      {running && mode === 'push_to_talk' && (
        <div className="px-4 pb-3">
          <button
            onPointerDown={(e) => {
              e.currentTarget.setPointerCapture(e.pointerId);
              startHold();
            }}
            onPointerUp={endHold}
            onPointerCancel={endHold}
            onPointerLeave={endHold}
            onKeyDown={(e) => {
              if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                startHold();
              }
            }}
            onKeyUp={(e) => {
              if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                endHold();
              }
            }}
            disabled={!running}
            className={`w-full h-11 rounded-lg border font-mono text-[11px] tracking-[0.2em] transition-all flex items-center justify-center gap-2 ${
              holding
                ? 'bg-echo-cyan text-echo-void border-echo-cyan shadow-[0_0_24px_rgba(0,240,255,0.35)]'
                : 'bg-[#0B0E14] border-echo-border text-echo-muted hover:border-echo-cyan/50 hover:text-echo-cyan'
            }`}
          >
            <Mic className="w-4 h-4" />
            {holding ? 'RECORDING — RELEASE TO SEND' : 'HOLD TO TALK'}
          </button>
        </div>
      )}

      {/* Speaker state strip */}
      {speaking && (
        <div className="px-4 pb-3 flex items-center gap-2 text-[10px] font-mono text-echo-cyan">
          <Volume2 className="w-3.5 h-3.5 animate-pulse" />
          <span className="truncate">
            ECHO SPEAKING{status?.tts_voice ? ` · ${status.tts_voice.split('\\').pop()}` : ''}
          </span>
          <button onClick={onStopSpeaking} className="ml-auto underline underline-offset-2 hover:text-white">
            interrupt
          </button>
        </div>
      )}
    </section>
  );
};
