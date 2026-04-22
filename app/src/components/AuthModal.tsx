import React, { useState } from 'react';
import { toast } from 'sonner';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

interface Props {
  onClose: () => void;
  onSuccess?: () => void;
  defaultMode?: 'login' | 'register';
}

const AuthModal: React.FC<Props> = ({ onClose, onSuccess, defaultMode = 'login' }) => {
  const [mode, setMode] = useState<'login' | 'register' | 'reset'>(defaultMode);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();

  const switchMode = (next: 'login' | 'register' | 'reset') => {
    setMode(next);
    setError(null);
    setPassword('');
    setShowPassword(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === 'login') {
        await login(email, password);
        toast.success('Welcome back!');
        onSuccess?.();
        onClose();
      } else if (mode === 'register') {
        await register(email, password);
        toast.success('Account created!');
        onSuccess?.();
        onClose();
      } else {
        await api.resetPassword(email, password);
        toast.success('Password updated! You can now sign in.');
        switchMode('login');
      }
    } catch (err: any) {
      const msg = String(err.message || err);
      if (msg.includes('409') || msg.includes('already registered')) {
        setError('Email already registered. Try logging in.');
      } else if (msg.includes('401') || msg.includes('Incorrect')) {
        setError('Incorrect email or password.');
      } else if (msg.includes('min_length') || msg.includes('8')) {
        setError('Password must be at least 8 characters.');
      } else {
        setError('Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const titles = { login: 'Sign in', register: 'Create account', reset: 'Reset password' };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-slate-900">{titles[mode]}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
        </div>

        {mode === 'reset' && (
          <p className="text-sm text-slate-500 mb-4">Enter your email and a new password.</p>
        )}

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
              Email
            </label>
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
              {mode === 'reset' ? 'New password' : 'Password'}
              {(mode === 'register' || mode === 'reset') && (
                <span className="text-slate-400 normal-case font-normal"> (min 8 chars)</span>
              )}
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                required
                minLength={8}
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full border border-slate-200 rounded-xl px-3 py-2.5 pr-16 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs font-medium select-none"
                tabIndex={-1}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          {mode === 'login' && (
            <div className="text-right -mt-1">
              <button
                type="button"
                onClick={() => switchMode('reset')}
                className="text-xs text-indigo-500 hover:text-indigo-700 hover:underline"
              >
                Forgot password?
              </button>
            </div>
          )}

          {error && (
            <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition-colors disabled:opacity-60"
          >
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create account' : 'Reset password'}
          </button>
        </form>

        <p className="text-sm text-center text-slate-500 mt-4">
          {mode === 'login' && (
            <>Don't have an account?{' '}
              <button onClick={() => switchMode('register')} className="text-indigo-600 font-medium hover:underline">Register</button>
            </>
          )}
          {mode === 'register' && (
            <>Already have an account?{' '}
              <button onClick={() => switchMode('login')} className="text-indigo-600 font-medium hover:underline">Sign in</button>
            </>
          )}
          {mode === 'reset' && (
            <>Remember it?{' '}
              <button onClick={() => switchMode('login')} className="text-indigo-600 font-medium hover:underline">Sign in</button>
            </>
          )}
        </p>
      </div>
    </div>
  );
};

export default AuthModal;
