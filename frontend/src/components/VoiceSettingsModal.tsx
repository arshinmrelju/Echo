import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Mic,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
  Volume2,
  X,
} from 'lucide-react';
import {
  VoiceDevice,
  VoiceMode,
  VoiceOption,
  VoiceRecording,
  VoiceSettings,
  VoiceStatus,
} from '../types';
import { apiClient } from '../api/client';
import { VoiceOrb } from './VoiceOrb';

interface VoiceSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: (status: VoiceStatus) => void;
}

const MODE_COPY: { id: VoiceMode; name: string; desc: string }[] = [
  { id: 'push_to_talk', name: 'Push to talk', desc: 'Microphone records only while you hold the talk pad.' },
  { id: 'wake_word', name: 'Wake word', desc: 'ECHO waits for its name, then captures one command.' },
  { id: 'continuous', name: 'Continuous', desc: 'An open conversation that ends on silence, dismissal, or timeout.' },
];

const STT_MODELS = ['tiny.en', 'base.en', 'small.en', 'tiny', 'base'];

const Section: React.FC<{ index: string; title: string; children: React.ReactNode }> = ({
  index,
  title,
  children,
}) => (
  <section className="space-y-3">
    <div className="flex items-center gap-2">
      <span className="font-mono text-[10px] text-echo-cyan-dim">{index}</span>
      <span className="font-mono text-[10px] tracking-[0.2em] text-echo-muted uppercase">{title}</span>
      <span className="flex-1 h-px bg-echo-border" />
    </div>
    {children}
  </section>
);

const Row: React.FC<{ label: string; hint?: string; children: React.ReactNode }> = ({
  label,
  hint,
  children,
}) => (
  <div className="space-y-1">
    <div className="flex items-center justify-between">
      <label className="text-[11px] font-medium text-gray-200">{label}</label>
      {hint && <span className="font-mono text-[10px] text-echo-muted">{hint}</span>}
    </div>
    {children}
  </div>
);

const Toggle: React.FC<{ checked: boolean; onChange: (v: boolean) => void; label: string }> = ({
  checked,
  onChange,
  label,
}) => (
  <button
    type="button"
    onClick={() => onChange(!checked)}
    className="flex items-center justify-between w-full px-3 py-2 rounded-md border border-echo-border bg-[#07090E] hover:border-gray-600 transition-colors"
  >
    <span className="text-[11px] text-gray-200">{label}</span>
    <span
      className={`relative w-8 h-4 rounded-full transition-colors ${checked ? 'bg-echo-cyan/70' : 'bg-echo-border'}`}
    >
      <span
        className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${
          checked ? 'left-[18px]' : 'left-0.5'
        }`}
      />
    </span>
  </button>
);

const inputClass =
  'w-full px-2.5 py-1.5 rounded-md border border-echo-border bg-[#07090E] text-white text-xs focus:outline-none focus:border-echo-cyan font-mono';

export const VoiceSettingsModal: React.FC<VoiceSettingsModalProps> = ({ isOpen, onClose, onSaved }) => {
  const [form, setForm] = useState<VoiceSettings | null>(null);
  const [devices, setDevices] = useState<VoiceDevice[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [recordings, setRecordings] = useState<VoiceRecording[]>([]);
  const [diagnostics, setDiagnostics] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [settingsRes, deviceList, voiceList, recordingRes, diag] = await Promise.all([
        apiClient.getVoiceSettings(),
        apiClient.listVoiceDevices().catch(() => []),
        apiClient.listVoiceOptions().catch(() => []),
        apiClient.listVoiceRecordings().catch(() => ({ recordings: [], enabled: false })),
        apiClient.getVoiceDiagnostics().catch(() => null),
      ]);
      setForm(settingsRes.settings);
      setDevices(deviceList);
      setVoices(voiceList);
      setRecordings(recordingRes.recordings);
      setDiagnostics(diag);
    } catch (e) {
      setError('Could not load voice settings from the daemon.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      load();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const update = <K extends keyof VoiceSettings>(key: K, value: VoiceSettings[K]) => {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSaved(false);
  };

  const handleSave = async () => {
    if (!form) return;
    setIsSaving(true);
    setError(null);
    try {
      const res = await apiClient.updateVoiceSettings(form);
      setForm(res.settings);
      setSaved(true);
      setNotice('Voice settings saved.');
      if (onSaved) onSaved(res.status);
      setTimeout(() => setSaved(false), 1500);
    } catch (e: any) {
      setError(`Could not save voice settings: ${e?.message || e}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleTest = async () => {
    if (!form) return;
    setTesting(true);
    setError(null);
    try {
      const res = await apiClient.testVoiceSpeech(
        'Echo voice output is working. This is the selected voice at the current rate.'
      );
      if (!res.success) {
        setError(res.error || 'Speech output did not start. Is the speaker available?');
      } else if (onSaved) {
        onSaved(res.status);
      }
    } catch (e: any) {
      setError(`Speech test failed: ${e?.message || e}`);
    } finally {
      setTesting(false);
    }
  };

  const removeRecordings = async () => {
    try {
      const res = await apiClient.deleteVoiceRecordings();
      setRecordings([]);
      setNotice(`Deleted ${res.removed} debug recording${res.removed === 1 ? '' : 's'}.`);
    } catch (e) {
      setError('Could not delete recordings.');
    }
  };

  const deviceValue = form?.mic_device_index == null ? 'default' : String(form.mic_device_index);
  const voiceValue = form?.tts_voice ?? 'default';
  const sttModels = STT_MODELS.includes(form?.stt_model || '') || !form
    ? STT_MODELS
    : [form.stt_model, ...STT_MODELS];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm select-none p-4">
      <div className="w-full max-w-3xl max-h-[88vh] rounded-xl border border-echo-border bg-[#0B0E14] shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-echo-border bg-[#07090E] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <VoiceOrb
              state={diagnostics?.state ?? 'idle'}
              level={0}
              size={30}
              muted={diagnostics?.state === 'muted'}
            />
            <div>
              <div className="font-semibold text-white text-sm">Voice I/O</div>
              <div className="font-mono text-[10px] tracking-wider text-echo-muted uppercase">
                Local microphone · offline speech · system voice
              </div>
            </div>
          </div>
          <button onClick={onClose} className="p-1 text-echo-muted hover:text-white rounded hover:bg-echo-border transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs">
          {loading && !form && (
            <div className="py-16 text-center text-echo-muted font-mono text-[11px]">Reading voice configuration…</div>
          )}

          {error && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-echo-danger/40 bg-echo-danger/10 text-echo-danger text-[11px]">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {notice && !error && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-md border border-echo-success/30 bg-echo-success/10 text-echo-success text-[11px]">
              <Check className="w-3.5 h-3.5" />
              <span>{notice}</span>
            </div>
          )}

          {form && (
            <div className="grid lg:grid-cols-2 gap-6">
              {/* INPUT */}
              <div className="space-y-4">
                <Section index="01" title="Input · microphone & wake">
                  <div className="grid grid-cols-3 gap-2">
                    {MODE_COPY.map((m) => (
                      <button
                        key={m.id}
                        onClick={() => update('mode', m.id)}
                        className={`p-2 rounded-md border text-left transition-colors ${
                          form.mode === m.id
                            ? 'border-echo-cyan bg-echo-cyan/10'
                            : 'border-echo-border bg-[#07090E] hover:border-gray-600'
                        }`}
                      >
                        <div className={`text-[11px] font-medium ${form.mode === m.id ? 'text-echo-cyan' : 'text-gray-200'}`}>
                          {m.name}
                        </div>
                        <div className="text-[10px] text-echo-muted leading-tight mt-0.5">{m.desc}</div>
                      </button>
                    ))}
                  </div>

                  <Row label="Microphone device" hint="16 kHz mono">
                    <div className="flex gap-1.5">
                      <select
                        value={deviceValue}
                        onChange={(e) =>
                          update(
                            'mic_device_index',
                            e.target.value === 'default' ? null : Number(e.target.value)
                          )
                        }
                        className={inputClass}
                      >
                        <option value="default">System default input</option>
                        {devices.map((d) => (
                          <option key={d.index} value={d.index}>
                            {d.name} · {d.channels}ch · {d.sample_rate} Hz
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={async () => {
                          const list = await apiClient.listVoiceDevices(true).catch(() => []);
                          setDevices(list);
                        }}
                        className="px-2 rounded-md border border-echo-border text-echo-muted hover:text-echo-cyan hover:border-echo-cyan/40 transition-colors"
                        title="Rescan audio inputs"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </Row>

                  <div className="grid grid-cols-2 gap-3">
                    <Row label="Wake word">
                      <input
                        value={form.wake_word}
                        onChange={(e) => update('wake_word', e.target.value)}
                        placeholder="echo"
                        className={inputClass}
                      />
                    </Row>
                    <Row label="Aliases" hint="comma separated">
                      <input
                        value={form.wake_aliases.join(', ')}
                        onChange={(e) =>
                          update(
                            'wake_aliases',
                            e.target.value
                              .split(',')
                              .map((s) => s.trim())
                              .filter(Boolean)
                          )
                        }
                        placeholder="hey echo, ok echo"
                        className={inputClass}
                      />
                    </Row>
                  </div>

                  <Row label="Wake sensitivity" hint={`${Math.round(form.wake_sensitivity * 100)}%`}>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={form.wake_sensitivity}
                      onChange={(e) => update('wake_sensitivity', parseFloat(e.target.value))}
                      className="w-full accent-echo-cyan cursor-pointer"
                    />
                  </Row>

                  <Row label="End-of-speech silence" hint={`${form.silence_threshold_seconds.toFixed(1)} s`}>
                    <input
                      type="range"
                      min="0.6"
                      max="3"
                      step="0.1"
                      value={form.silence_threshold_seconds}
                      onChange={(e) => update('silence_threshold_seconds', parseFloat(e.target.value))}
                      className="w-full accent-echo-cyan cursor-pointer"
                    />
                  </Row>

                  <div className="grid grid-cols-2 gap-2">
                    <Toggle
                      checked={form.partial_transcription}
                      onChange={(v) => update('partial_transcription', v)}
                      label="Live partial transcript"
                    />
                    <Toggle
                      checked={form.barge_in_enabled}
                      onChange={(v) => update('barge_in_enabled', v)}
                      label="Interrupt by speaking"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <Row label="Continuous timeout" hint="seconds">
                      <input
                        type="number"
                        min={5}
                        max={600}
                        value={form.continuous_timeout_seconds}
                        onChange={(e) => update('continuous_timeout_seconds', Number(e.target.value))}
                        className={inputClass}
                      />
                    </Row>
                    <Row label="Wake command timeout" hint="seconds">
                      <input
                        type="number"
                        min={3}
                        max={60}
                        value={form.wake_command_timeout_seconds}
                        onChange={(e) => update('wake_command_timeout_seconds', Number(e.target.value))}
                        className={inputClass}
                      />
                    </Row>
                  </div>
                </Section>
              </div>

              {/* OUTPUT + PRIVACY */}
              <div className="space-y-4">
                <Section index="02" title="Output · speech">
                  <Row label="Recognition model" hint="faster-whisper">
                    <select
                      value={form.stt_model}
                      onChange={(e) => update('stt_model', e.target.value)}
                      className={inputClass}
                    >
                      {sttModels.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </Row>

                  <Row label="System voice" hint={`${voices.length} installed`}>
                    <select
                      value={voiceValue}
                      onChange={(e) => update('tts_voice', e.target.value === 'default' ? null : e.target.value)}
                      className={inputClass}
                    >
                      <option value="default">System default voice</option>
                      {voices.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name} ({v.languages.join(', ')})
                        </option>
                      ))}
                    </select>
                  </Row>

                  <Row label="Speaking rate" hint={`${form.tts_rate} wpm`}>
                    <input
                      type="range"
                      min="100"
                      max="320"
                      step="5"
                      value={form.tts_rate}
                      onChange={(e) => update('tts_rate', Number(e.target.value))}
                      className="w-full accent-echo-cyan cursor-pointer"
                    />
                  </Row>

                  <Row label="Volume" hint={`${Math.round(form.tts_volume * 100)}%`}>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={form.tts_volume}
                      onChange={(e) => update('tts_volume', parseFloat(e.target.value))}
                      className="w-full accent-echo-cyan cursor-pointer"
                    />
                  </Row>

                  <button
                    onClick={handleTest}
                    disabled={testing}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-md border border-echo-border bg-[#07090E] text-gray-200 hover:border-echo-cyan/50 hover:text-echo-cyan transition-colors disabled:opacity-50"
                  >
                    <Volume2 className="w-3.5 h-3.5" />
                    {testing ? 'Speaking…' : 'Test voice'}
                  </button>
                </Section>

                <Section index="03" title="Privacy · retention">
                  <div className="p-3 rounded-md border border-echo-border bg-[#07090E] space-y-2">
                    <div className="flex items-start gap-2 text-[11px] text-echo-muted leading-snug">
                      <ShieldCheck className="w-4 h-4 text-echo-success flex-shrink-0 mt-0.5" />
                      <span>
                        By default ECHO keeps audio in memory only, discards it after each turn, and never
                        stores transcripts as audio. Recording capture is off unless you turn it on here.
                      </span>
                    </div>
                    <Toggle
                      checked={form.save_recordings}
                      onChange={(v) => update('save_recordings', v)}
                      label="Save debug recordings to disk"
                    />
                    {form.save_recordings && (
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[11px] text-echo-muted">Keep newest</span>
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            min={0}
                            max={200}
                            value={form.recording_retention}
                            onChange={(e) => update('recording_retention', Number(e.target.value))}
                            className={`${inputClass} w-20`}
                          />
                          <span className="font-mono text-[10px] text-echo-muted">files</span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="rounded-md border border-echo-border overflow-hidden">
                    <div className="px-3 py-1.5 bg-[#07090E] border-b border-echo-border flex items-center justify-between">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-echo-muted">
                        Stored recordings · {recordings.length}
                      </span>
                      <button
                        onClick={removeRecordings}
                        disabled={recordings.length === 0}
                        className="flex items-center gap-1 text-[10px] font-mono text-echo-muted hover:text-echo-danger disabled:opacity-30 transition-colors"
                      >
                        <Trash2 className="w-3 h-3" /> PURGE
                      </button>
                    </div>
                    {recordings.length === 0 ? (
                      <div className="px-3 py-3 text-[11px] text-echo-muted">No audio files stored.</div>
                    ) : (
                      <div className="max-h-28 overflow-y-auto divide-y divide-echo-border/60">
                        {recordings.map((r) => (
                          <div key={r.name} className="px-3 py-1.5 flex items-center justify-between font-mono text-[10px]">
                            <span className="text-gray-300 truncate">{r.name}</span>
                            <span className="text-echo-muted">{(r.size_bytes / 1024).toFixed(0)} KB</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </Section>

                {diagnostics && (
                  <Section index="04" title="Diagnostics">
                    <div className="grid grid-cols-2 gap-2 font-mono text-[10px]">
                      {[
                        ['STT', diagnostics.stt?.available ? `${diagnostics.stt?.model}` : 'UNAVAILABLE'],
                        ['TTS', diagnostics.tts?.available ? `${diagnostics.tts?.voice_count} voices` : 'UNAVAILABLE'],
                        ['WAKE', `${diagnostics.wake_word?.engine || 'whisper-segment'}`],
                        ['MIC', form.mic_device_index == null ? 'system default' : `device ${form.mic_device_index}`],
                      ].map(([k, v]) => (
                        <div key={k} className="px-2.5 py-1.5 rounded border border-echo-border bg-[#07090E] flex justify-between">
                          <span className="text-echo-muted">{k}</span>
                          <span className="text-gray-300 truncate ml-2">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                    {(diagnostics.stt?.error || diagnostics.tts?.error) && (
                      <div className="text-[10px] text-echo-danger font-mono">
                        {diagnostics.stt?.error || diagnostics.tts?.error}
                      </div>
                    )}
                  </Section>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-echo-border bg-[#07090E] flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-echo-muted">
            <Mic className="w-3 h-3" />
            Saving while active restarts the audio channel.
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded-md border border-echo-border text-gray-300 text-xs hover:bg-echo-border transition-colors"
            >
              Close
            </button>
            <button
              onClick={handleSave}
              disabled={!form || isSaving}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-echo-cyan text-echo-void text-xs font-semibold hover:bg-echo-cyan/90 disabled:opacity-50 transition-colors"
            >
              {saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
              {isSaving ? 'Saving…' : saved ? 'Saved' : 'Save settings'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
