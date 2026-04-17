import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';

type Variant = 'one' | 'all';
type Status = 'loading' | 'success' | 'not_found' | 'error';

const UnsubscribePage: React.FC<{ variant: Variant }> = ({ variant }) => {
  const { token } = useParams<{ token: string }>();
  const [status, setStatus] = useState<Status>('loading');

  useEffect(() => {
    if (!token) { setStatus('error'); return; }

    const url = variant === 'all'
      ? `/unsubscribe/all/${token}`
      : `/unsubscribe/${token}`;

    fetch(url, { headers: { Accept: 'application/json' } })
      .then(async (res) => {
        if (res.ok) setStatus('success');
        else if (res.status === 404) setStatus('not_found');
        else setStatus('error');
      })
      .catch(() => setStatus('error'));
  }, [token, variant]);

  if (status === 'loading') {
    return (
      <div className="max-w-md mx-auto mt-24 px-4 text-center text-slate-500">
        Unsubscribing…
      </div>
    );
  }

  if (status === 'not_found') {
    return (
      <div className="max-w-md mx-auto mt-24 px-4">
        <h1 className="text-xl font-semibold text-slate-800 mb-2">Link not found</h1>
        <p className="text-slate-500 mb-6">
          This unsubscribe link is invalid or has already been used.
        </p>
        <Link
          to="/alerts"
          className="inline-block bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          Manage alerts
        </Link>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="max-w-md mx-auto mt-24 px-4">
        <h1 className="text-xl font-semibold text-slate-800 mb-2">Something went wrong</h1>
        <p className="text-slate-500 mb-6">
          We couldn't process your request. Please try again or manage your alerts directly.
        </p>
        <Link
          to="/alerts"
          className="inline-block bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          Manage alerts
        </Link>
      </div>
    );
  }

  // success
  const title = variant === 'all' ? 'All price alerts paused' : 'You\'ve been unsubscribed';
  const body = variant === 'all'
    ? "You won't receive any more price-drop notifications from AptTrack. You can re-enable individual alerts any time."
    : "This price alert has been paused. You won't receive any more notifications for it. You can re-enable it any time.";

  return (
    <div className="max-w-md mx-auto mt-24 px-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-emerald-500 text-2xl">✓</span>
        <h1 className="text-xl font-semibold text-slate-800">{title}</h1>
      </div>
      <p className="text-slate-500 mb-6 leading-relaxed">{body}</p>
      <div className="flex gap-3">
        <Link
          to="/alerts"
          className="inline-block bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          Manage alerts
        </Link>
        <Link
          to="/"
          className="inline-block bg-slate-100 hover:bg-slate-200 text-slate-600 px-4 py-2 rounded-lg text-sm font-medium"
        >
          Back to AptTrack
        </Link>
      </div>
    </div>
  );
};

export default UnsubscribePage;
