import React from 'react';
import { AgentOrbState } from '../types';

interface StatusOrbProps {
  state: AgentOrbState;
  size?: 'sm' | 'md' | 'lg';
}

export const StatusOrb: React.FC<StatusOrbProps> = ({ state, size = 'md' }) => {
  const sizeClasses = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-6 h-6',
  }[size];

  const getStateDetails = () => {
    switch (state) {
      case 'thinking':
        return {
          bg: 'bg-echo-cyan',
          glow: 'shadow-[0_0_12px_#00F0FF]',
          animate: 'animate-ping',
          label: 'Reasoning...',
        };
      case 'speaking':
        return {
          bg: 'bg-echo-blue',
          glow: 'shadow-[0_0_15px_#0070F3]',
          animate: 'animate-pulse',
          label: 'Generating response',
        };
      case 'executing':
        return {
          bg: 'bg-echo-purple',
          glow: 'shadow-[0_0_15px_#7928CA]',
          animate: 'animate-pulse',
          label: 'Executing tool',
        };
      case 'error':
        return {
          bg: 'bg-echo-danger',
          glow: 'shadow-[0_0_12px_#FF1744]',
          animate: '',
          label: 'Error state',
        };
      case 'disconnected':
        return {
          bg: 'bg-gray-600',
          glow: '',
          animate: '',
          label: 'Disconnected',
        };
      case 'idle':
      default:
        return {
          bg: 'bg-echo-cyan',
          glow: 'shadow-[0_0_8px_#00F0FF]',
          animate: '',
          label: 'Online / Ready',
        };
    }
  };

  const { bg, glow, animate, label } = getStateDetails();

  return (
    <div className="flex items-center gap-2" title={label}>
      <div className="relative flex items-center justify-center">
        {state === 'thinking' && (
          <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${bg} ${animate}`} />
        )}
        <span className={`relative inline-flex rounded-full ${sizeClasses} ${bg} ${glow} transition-all duration-300`} />
      </div>
    </div>
  );
};

