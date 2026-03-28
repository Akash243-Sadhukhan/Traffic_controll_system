import { useState } from 'react';
import './LiveVideoFeed.css';

export default function LiveVideoFeed({ backendUrl = "http://localhost:8001" }) {
  const [hasError, setHasError] = useState(false);
  const streamUrl = `${backendUrl}/video_feed`;

  return (
    <div className="live-feed card">
      <div className="live-feed__header">
        <h3 className="card__title">📡 Live Detection Feed</h3>
        <div className="live-feed__badge">
          <span className="live-feed__dot"></span> LIVE
        </div>
      </div>
      <div className="live-feed__content">
        {hasError ? (
          <div className="live-feed__error">
            <p>Stream not active.</p>
            <small>Start the detection engine to view the feed.</small>
          </div>
        ) : (
          <img
            src={streamUrl}
            alt="AI Live Feed"
            className="live-feed__video"
            onError={() => setHasError(true)}
            onLoad={() => setHasError(false)}
          />
        )}
      </div>
    </div>
  );
}
