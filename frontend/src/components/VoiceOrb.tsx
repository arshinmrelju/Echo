import React from 'react';
import { VoiceState } from '../types';

interface VoiceOrbProps {
  state: VoiceState;
  level?: number;
  size?: number;
  muted?: boolean;
  offline?: boolean;
}

const STATE_COLOR: Record<VoiceState, string> = {
  idle: '#008B99',
  listening: '#00F0FF',
  processing: '#0070F3',
  speaking: '#00F0FF',
  muted: '#8B949E',
  error: '#FF1744',
};

const STATE_DURATION: Record<VoiceState, string> = {
  idle: '22s',
  listening: '18s',
  processing: '7s',
  speaking: '12s',
  muted: '22s',
  error: '22s',
};

const TICKS = Array.from({ length: 48 }, (_, i) => i);

export const VoiceOrb: React.FC<VoiceOrbProps> = ({
  state,
  level = 0,
  size = 72,
  muted = false,
  offline = false,
}) => {
  const effectiveState: VoiceState = offline ? 'muted' : state;
  const color = STATE_COLOR[effectiveState];
  const clampedLevel = Math.max(0, Math.min(1, level));
  const isActive = effectiveState === 'listening' || effectiveState === 'processing' || effectiveState === 'speaking';

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 200 200"
      role="img"
      aria-label={`Voice ${offline ? 'unavailable' : effectiveState}`}
      className="select-none"
    >
      <defs>
        <filter id="voice-orb-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Outer calibration ticks */}
      <g className="voice-orb-rotor" style={{ animationDuration: STATE_DURATION[effectiveState] }}>
        {TICKS.map((i) => {
          const angle = (i / TICKS.length) * Math.PI * 2;
          const major = i % 4 === 0;
          const inner = major ? 74 : 80;
          const outer = 88;
          return (
            <line
              key={i}
              x1={100 + Math.cos(angle) * inner}
              y1={100 + Math.sin(angle) * inner}
              x2={100 + Math.cos(angle) * outer}
              y2={100 + Math.sin(angle) * outer}
              stroke={color}
              strokeWidth={major ? 1.6 : 0.8}
              opacity={isActive ? (major ? 0.85 : 0.4) : major ? 0.5 : 0.22}
            />
          );
        })}
      </g>

      {/* Counter-rotating arc segments */}
      <g
        className="voice-orb-rotor-reverse"
        style={{
          animationDuration: '9s',
          animationPlayState: isActive ? 'running' : 'paused',
          opacity: isActive ? 1 : 0.55,
        }}
      >
        <circle
          cx="100"
          cy="100"
          r="68"
          fill="none"
          stroke={color}
          strokeWidth="1.4"
          strokeDasharray="46 26 12 26"
          strokeLinecap="round"
          opacity={effectiveState === 'error' ? 0.9 : 0.6}
        />
      </g>

      {/* Level-reactive ring */}
      <circle
        cx="100"
        cy="100"
        r={48 + clampedLevel * 9}
        fill="none"
        stroke={color}
        strokeWidth={1 + clampedLevel * 2.4}
        opacity={effectiveState === 'muted' ? 0.15 : 0.35 + clampedLevel * 0.5}
        style={{ transition: 'r 90ms linear, opacity 90ms linear, stroke-width 90ms linear' }}
      />

      {/* Inner containment ring */}
      <circle cx="100" cy="100" r="42" fill="none" stroke={color} strokeWidth="0.8" opacity="0.35" />

      {/* Core */}
      <circle
        cx="100"
        cy="100"
        r={13 + clampedLevel * 3}
        fill={color}
        opacity={effectiveState === 'muted' ? 0.28 : 0.9}
        filter={isActive ? 'url(#voice-orb-glow)' : undefined}
        style={{ transition: 'r 90ms linear, opacity 200ms linear' }}
      />
      <circle cx="100" cy="100" r="4" fill="#05070A" opacity={effectiveState === 'muted' ? 0.6 : 1} />

      {/* Processing crosshair */}
      {effectiveState === 'processing' && (
        <g opacity="0.8">
          <line x1="100" y1="84" x2="100" y2="116" stroke={color} strokeWidth="1" />
          <line x1="84" y1="100" x2="116" y2="100" stroke={color} strokeWidth="1" />
        </g>
      )}

      {/* Mute slash */}
      {(muted || effectiveState === 'muted') && (
        <line
          x1="66"
          y1="134"
          x2="134"
          y2="66"
          stroke="#FF1744"
          strokeWidth="3"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
};
