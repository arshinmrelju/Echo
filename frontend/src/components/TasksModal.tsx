import React, { useState, useEffect } from 'react';
import { X, CheckSquare, Plus, Trash2, CheckCircle2, Clock, AlertCircle } from 'lucide-react';
import { TaskItem } from '../types';
import { apiClient } from '../api/client';

interface TasksModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const TasksModal: React.FC<TasksModalProps> = ({ isOpen, onClose }) => {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [newGoal, setNewGoal] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const loadTasks = async () => {
    try {
      const data = await apiClient.listTasks();
      setTasks(data);
    } catch (e) {
      console.error('Failed to load tasks', e);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadTasks();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!newGoal.trim()) return;
    try {
      await apiClient.createTask(newGoal.trim());
      setNewGoal('');
      setIsAdding(false);
      loadTasks();
    } catch (e) {
      alert('Failed to create task: ' + String(e));
    }
  };

  const handleToggleStatus = async (task: TaskItem) => {
    const nextStatus = task.status === 'completed' ? 'in_progress' : 'completed';
    try {
      await apiClient.updateTask(task.id, nextStatus);
      loadTasks();
    } catch (e) {
      alert('Failed to update task: ' + String(e));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiClient.deleteTask(id);
      loadTasks();
    } catch (e) {
      alert('Failed to delete task: ' + String(e));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm select-none p-4">
      <div className="w-full max-w-xl rounded-2xl border border-echo-border bg-[#0B0E14] shadow-2xl flex flex-col overflow-hidden max-h-[85vh]">
        {/* Header */}
        <div className="p-4 border-b border-echo-border flex items-center justify-between bg-[#0F1420]">
          <div className="flex items-center gap-2 text-white font-semibold">
            <CheckSquare className="w-4 h-4 text-echo-cyan" />
            <span>Task Queue & Goals</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-echo-muted hover:text-white rounded hover:bg-echo-border transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="p-4 border-b border-echo-border bg-[#080B10] flex items-center justify-between">
          <span className="text-xs text-echo-muted">
            Track goals and multi-step agent operations.
          </span>
          <button
            onClick={() => setIsAdding(!isAdding)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-echo-cyan/10 border border-echo-cyan/30 text-echo-cyan text-xs font-medium hover:bg-echo-cyan/20 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{isAdding ? 'Cancel' : 'New Task'}</span>
          </button>
        </div>

        {/* Add Input */}
        {isAdding && (
          <div className="p-4 border-b border-echo-border bg-[#0F1420] flex gap-2">
            <input
              type="text"
              placeholder="Enter goal or task objective..."
              value={newGoal}
              onChange={(e) => setNewGoal(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              className="flex-1 px-3 py-1.5 rounded-lg border border-echo-border bg-[#0B0E14] text-xs text-white focus:outline-none focus:border-echo-cyan"
            />
            <button
              onClick={handleCreate}
              className="px-3 py-1.5 rounded-lg bg-echo-cyan text-echo-void text-xs font-semibold hover:bg-echo-cyan/90 transition-all shadow-[0_0_8px_rgba(0,240,255,0.3)]"
            >
              Add
            </button>
          </div>
        )}

        {/* Task List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2 text-xs">
          {tasks.length === 0 ? (
            <div className="py-12 text-center text-echo-muted">
              No tasks currently registered.
            </div>
          ) : (
            tasks.map((task) => (
              <div
                key={task.id}
                className="group flex items-center justify-between p-3 rounded-lg border border-echo-border bg-[#080B10] hover:border-echo-cyan/30 transition-all"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <button
                    onClick={() => handleToggleStatus(task)}
                    className="flex-shrink-0 text-echo-muted hover:text-echo-success transition-colors"
                  >
                    {task.status === 'completed' ? (
                      <CheckCircle2 className="w-4 h-4 text-echo-success" />
                    ) : (
                      <Clock className="w-4 h-4 text-echo-cyan" />
                    )}
                  </button>
                  <div className="min-w-0">
                    <div
                      className={`truncate text-sm font-medium ${
                        task.status === 'completed'
                          ? 'line-through text-echo-muted'
                          : 'text-gray-200'
                      }`}
                    >
                      {task.goal}
                    </div>
                    <div className="text-[10px] text-gray-500 font-mono">
                      Status: <span className="text-echo-cyan uppercase">{task.status}</span> • Created:{' '}
                      {new Date(task.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => handleDelete(task.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-echo-muted hover:text-echo-danger rounded transition-opacity"
                  title="Delete task"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

