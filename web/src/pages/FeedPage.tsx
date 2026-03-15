import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listTracks } from "../api";
import { useAuth } from "../auth";
import type { Track } from "../types";

function statusClass(status: Track["status"]) {
  if (status === "published") return "ok";
  if (status === "processing") return "warn";
  return "err";
}

export function FeedPage() {
  const { token } = useAuth();

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"recent" | "popular">("recent");
  const [tracks, setTracks] = useState<Track[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    void listTracks({
      q: query.trim() || undefined,
      sort,
      limit: 60,
      token
    })
      .then((response) => {
        if (!active) return;
        setTracks(response.items);
        setTotal(response.total || response.items.length);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Cannot load feed");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [query, sort, token]);

  return (
    <section className="page">
      <div className="page-header">
        <h1>Feed</h1>
        <p className="muted">Public tracks from creators. Open track page for player and social activity.</p>
      </div>

      <div className="card filters">
        <label>
          Search tracks
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="title, artist, genre" />
        </label>
        <label>
          Sort
          <select value={sort} onChange={(event) => setSort(event.target.value as "recent" | "popular")}>
            <option value="recent">recent</option>
            <option value="popular">popular</option>
          </select>
        </label>
        <div className="muted">Found: {total}</div>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {loading ? <p className="muted">Loading feed...</p> : null}

      <div className="track-grid">
        {tracks.map((track) => (
          <article key={track.id} className="card track-card">
            <div className="inline split">
              <h3>{track.title}</h3>
              <span className={`badge ${statusClass(track.status)}`}>{track.status}</span>
            </div>
            <p className="muted">{track.artist}</p>
            <div className="inline">
              <span className="badge">{track.visibility}</span>
              <span className="badge">plays: {track.plays_count}</span>
              {track.genre ? <span className="badge">{track.genre}</span> : null}
            </div>
            {track.description ? <p>{track.description}</p> : null}
            <div className="inline">
              <Link to={`/tracks/${track.id}`}>Open track</Link>
              <Link to={`/profiles/${track.owner_id}`}>@{track.owner_id}</Link>
            </div>
          </article>
        ))}
      </div>

      {!loading && tracks.length === 0 ? <p className="muted">No tracks found.</p> : null}
    </section>
  );
}
