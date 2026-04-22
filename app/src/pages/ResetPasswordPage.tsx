import React, { useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../services/api';

const ResetPasswordPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.resetPasswordWithToken(token, password);
      setDone(true);
      toast.success('Password reset! You can now sign in.');
      setTimeout(() => navigate('/'), 2000);
    } catch (err: any) {
      const msg = String(err.message || err);
      if (msg.includes('400')) {
        toast.error('This reset link is invalid or has expired. Please request a new one.');
      } else {
        toast.error('Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-lg max-w-sm w-full p-8 text-center">
          <p className="text-slate-600 mb-4">Invalid reset link. Please request a new one.</p>
          <Link to="/" className="text-indigo-600 hover:underline text-sm">Back to listings</Link>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-lg max-w-sm w-full p-8 text-center">
          <p className="text-emerald-600 font-semibold mb-2">Password updated!</p>
          <p className="text-slate-500 text-sm">Redirecting you to sign in…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg max-w-sm w-full p-8">
        <h1 className="text-xl font-bold text-slate-900 mb-2">Choose a new password</h1>
        <p className="text-sm text-slate-500 mb-6">Must be at least 8 characters.</p>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
              New password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                required
                minLength={8}
                maxLength={128}
                autoFocus
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

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition-colors disabled:opacity-60"
          >
            {loading ? 'Please wait…' : 'Set new password'}
          </button>
        </form>

        <p className="text-sm text-center text-slate-500 mt-4">
          <Link to="/" className="text-indigo-600 hover:underline">Back to listings</Link>
        </p>
      </div>
    </div>
  );
};

export default ResetPasswordPage;
