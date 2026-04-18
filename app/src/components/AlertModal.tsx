import React, { useState } from 'react';
import { toast } from 'sonner';
import api, { SubscriptionCreate } from '../services/api';
import { useAuth } from '../context/AuthContext';

interface Props {
  apartmentId: number;
  apartmentTitle: string;
  currentPrice?: number;
  planId?: number;
  planName?: string;
  onClose: () => void;
  onCreated: () => void;
}

const AlertModal: React.FC<Props> = ({ apartmentId, apartmentTitle, currentPrice, planId, planName, onClose, onCreated }) => {
  const { token, activeAlertsCount, updateAlertCount } = useAuth();
  const [type, setType] = useState<'price' | 'pct'>('price');
  const [targetPrice, setTargetPrice] = useState(currentPrice != null ? String(Math.floor(currentPrice * 0.95)) : '');
  const [pctDrop, setPctDrop] = useState('5');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setLoading(true);
    try {
      const payload: SubscriptionCreate = {
        apartment_id: apartmentId,
        ...(planId !== undefined && { plan_id: planId }),
        notify_email: true,
      };
      if (type === 'price') {
        payload.target_price = parseFloat(targetPrice);
      } else {
        payload.price_drop_pct = parseFloat(pctDrop);
      }
      await api.createSubscription(token, payload);
      updateAlertCount(activeAlertsCount + 1);
      toast.success('Alert created! We\'ll email you when the price drops.');
      onCreated();
      onClose();
    } catch (err: any) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-xl font-bold text-slate-900">Set Price Alert</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
        </div>

        {/* Property */}
        <div className="bg-indigo-50 rounded-xl px-4 py-3 mb-5">
          <p className="text-xs text-indigo-400 font-semibold uppercase tracking-wider mb-0.5">Watching</p>
          <p className="font-semibold text-indigo-900 text-sm leading-snug">{apartmentTitle}</p>
          {planName && (
            <p className="text-xs text-indigo-700 font-medium mt-0.5">Plan: {planName}</p>
          )}
          {currentPrice != null && <p className="text-xs text-indigo-500 mt-0.5">Current ${currentPrice.toLocaleString()}/mo</p>}
        </div>

        <form onSubmit={submit} className="space-y-4">
            {/* Alert type */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Alert when</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setType('price')}
                  className={`flex-1 py-2 rounded-xl text-sm font-medium border transition-colors ${type === 'price' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}
                >
                  Price drops below
                </button>
                <button
                  type="button"
                  onClick={() => setType('pct')}
                  className={`flex-1 py-2 rounded-xl text-sm font-medium border transition-colors ${type === 'pct' ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}
                >
                  Price drops by %
                </button>
              </div>
            </div>

            {/* Threshold */}
            {type === 'price' ? (
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                  Target price ($/mo)
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-2.5 text-slate-400 font-semibold">$</span>
                  <input
                    type="number"
                    required
                    min={500}
                    value={targetPrice}
                    onChange={e => setTargetPrice(e.target.value)}
                    className="w-full border border-slate-200 rounded-xl pl-7 pr-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400"
                  />
                </div>
                {currentPrice != null && parseFloat(targetPrice) >= currentPrice && (
                  <p className="text-amber-600 text-xs mt-1">Target price is higher than current — alert will fire immediately.</p>
                )}
              </div>
            ) : (
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                  Drop percentage
                </label>
                <div className="relative">
                  <input
                    type="number"
                    required
                    min={1}
                    max={50}
                    value={pctDrop}
                    onChange={e => setPctDrop(e.target.value)}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 pr-10"
                  />
                  <span className="absolute right-3 top-2.5 text-slate-400 font-semibold">%</span>
                </div>
                <p className="text-slate-400 text-xs mt-1">
                  Alert when price drops by {pctDrop}%{currentPrice != null ? ` (≈$${Math.floor(currentPrice * (1 - parseFloat(pctDrop || '0') / 100)).toLocaleString()}/mo)` : ''}
                </p>
              </div>
            )}

            {/* Notification */}
            <div className="flex items-center gap-2 text-sm text-slate-500 bg-slate-50 rounded-xl px-3 py-2.5">
              <span>📧</span>
              <span>Email notification to your account</span>
            </div>

            {error && (
              <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition-colors disabled:opacity-60"
            >
              {loading ? 'Creating…' : 'Create alert'}
            </button>
          </form>
      </div>
    </div>
  );
};

export default AlertModal;
