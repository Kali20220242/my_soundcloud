import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listTracks } from "../api";
import { useAuth } from "../auth";
import { ArtworkTile } from "../components/ArtworkTile";
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
        <h1>Stream</h1>
        <p className="muted">Listen to the latest public uploads. Open any track for full player and social actions.</p>
      </div>

      <div className="card filters stream-filters">
        <label>
          Find in stream
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

      <div className="stream-list">
        {tracks.map((track) => (
          <article key={track.id} className="card stream-item">
            <ArtworkTile seed={track.id} title={track.title} size="md" />

            <div className="stream-body">
              <div className="inline split">
                <div>
                  <p className="stream-owner">
                    <Link to={`/profiles/${track.owner_id}`}>@{track.owner_id}</Link>
                  </p>
                  <h3>{track.title}</h3>
                  <p className="muted">{track.artist}</p>
                </div>
                <span className={`badge ${statusClass(track.status)}`}>{track.status}</span>
              </div>

              <div className="inline">
                <span className="badge">{track.visibility}</span>
                <span className="badge">plays: {track.plays_count}</span>
                {track.genre ? <span className="badge">{track.genre}</span> : null}
              </div>

              {track.description ? <p>{track.description}</p> : null}

              <div className="inline">
                <Link to={`/tracks/${track.id}`}>Play track</Link>
                <Link to={`/profiles/${track.owner_id}`}>Visit artist</Link>
              </div>
            </div>
          </article>
        ))}
      </div>

      {!loading && tracks.length === 0 ? <p className="muted">No tracks found.</p> : null}
    </section>
  );
}
