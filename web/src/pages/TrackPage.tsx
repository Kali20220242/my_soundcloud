import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  addComment,
  buildTrackAudioUrl,
  buildSoundCloudEmbedUrl,
  deleteTrack,
  getLikeCount,
  getTrack,
  likeTrack,
  listComments,
  registerPlay,
  unlikeTrack,
  updateTrack
} from "../api";
import { useAuth } from "../auth";
import { ArtworkTile } from "../components/ArtworkTile";
import type { Comment, Track, Visibility } from "../types";

export function TrackPage() {
  const { trackId } = useParams<{ trackId: string }>();
  const navigate = useNavigate();
  const { token, user } = useAuth();

  const [track, setTrack] = useState<Track | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [likes, setLikes] = useState(0);
  const [likedByMe, setLikedByMe] = useState(false);
  const [comments, setComments] = useState<Comment[]>([]);
  const [commentText, setCommentText] = useState("");

  const [editTitle, setEditTitle] = useState("");
  const [editArtist, setEditArtist] = useState("");
  const [editVisibility, setEditVisibility] = useState<Visibility>("private");
  const [editGenre, setEditGenre] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editBusy, setEditBusy] = useState(false);
  const [editMessage, setEditMessage] = useState<string | null>(null);

  const isOwner = useMemo(() => {
    if (!track || !user) return false;
    return track.owner_id === user.user_id;
  }, [track, user]);

  useEffect(() => {
    if (!trackId) {
      setError("Track id is missing");
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);

    void getTrack(trackId, token)
      .then((response) => {
        if (!active) return;
        setTrack(response);
        setEditTitle(response.title);
        setEditArtist(response.artist);
        setEditVisibility(response.visibility);
        setEditGenre(response.genre || "");
        setEditDescription(response.description || "");
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Cannot load track");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [trackId, token]);

  useEffect(() => {
    if (!trackId) return;

    let active = true;
    void Promise.all([getLikeCount(trackId), listComments(trackId)])
      .then(([likesResponse, commentsResponse]) => {
        if (!active) return;
        setLikes(likesResponse.track_likes);
        setComments(commentsResponse.items);
      })
      .catch(() => {
        if (!active) return;
        setLikes(0);
        setComments([]);
      });

    return () => {
      active = false;
    };
  }, [trackId]);

  async function handlePlay() {
    if (!track) return;
    try {
      const response = await registerPlay(track.id, token);
      setTrack({ ...track, plays_count: response.plays_count });
    } catch {
      // do not block playback on metrics error
    }
  }

  async function handleLike() {
    if (!token || !track) return;
    const response = await likeTrack(token, track.id);
    setLikes(response.track_likes);
    setLikedByMe(true);
  }

  async function handleUnlike() {
    if (!token || !track) return;
    const response = await unlikeTrack(token, track.id);
    setLikes(response.track_likes);
    setLikedByMe(false);
  }

  async function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !track || !commentText.trim()) return;

    await addComment(token, track.id, commentText.trim());
    const commentsResponse = await listComments(track.id);
    setComments(commentsResponse.items);
    setCommentText("");
  }

  async function saveTrack(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !track || !isOwner) return;

    const payload: {
      title?: string;
      artist?: string;
      visibility?: Visibility;
      genre?: string;
      description?: string;
    } = {};

    if (editTitle !== track.title) payload.title = editTitle;
    if (editArtist !== track.artist) payload.artist = editArtist;
    if (editVisibility !== track.visibility) payload.visibility = editVisibility;
    if (editGenre !== (track.genre || "")) payload.genre = editGenre;
    if (editDescription !== (track.description || "")) payload.description = editDescription;

    if (Object.keys(payload).length === 0) {
      setEditMessage("No changes");
      return;
    }

    setEditBusy(true);
    setEditMessage(null);
    try {
      const updated = await updateTrack(token, track.id, payload);
      setTrack(updated);
      setEditTitle(updated.title);
      setEditArtist(updated.artist);
      setEditVisibility(updated.visibility);
      setEditGenre(updated.genre || "");
      setEditDescription(updated.description || "");
      setEditMessage("Track updated");
    } catch (err) {
      setEditMessage(err instanceof Error ? err.message : "Cannot update track");
    } finally {
      setEditBusy(false);
    }
  }

  async function removeTrack() {
    if (!token || !track || !isOwner) return;
    if (!window.confirm("Delete this track?")) return;

    await deleteTrack(token, track.id);
    navigate(`/profiles/${user?.user_id || ""}`, { replace: true });
  }

  if (loading) {
    return <div className="page-loading">Loading track...</div>;
  }

  if (error || !track) {
    return (
      <section className="page card narrow">
        <h1>Track</h1>
        <p className="error">{error || "Track not found"}</p>
      </section>
    );
  }

  return (
    <section className="page track-page">
      <article className="card hero-track">
        <ArtworkTile seed={track.id} title={track.title} size="lg" imageUrl={track.artwork_url} />
        <div className="hero-track-body">
          <h1>{track.title}</h1>
          <p className="muted">
            {track.artist} • <Link to={`/profiles/${track.owner_id}`}>@{track.owner_id}</Link>
          </p>
          <div className="inline">
            <span className="badge">{track.visibility}</span>
            <span className="badge">{track.status}</span>
            <span className="badge">plays: {track.plays_count}</span>
            {track.genre ? <span className="badge">{track.genre}</span> : null}
          </div>
          {track.description ? <p>{track.description}</p> : null}
          <div className="inline">
            <span className="badge ok">Likes: {likes}</span>
            <button disabled={!token} onClick={() => void handleLike()}>
              Like
            </button>
            <button className="ghost" disabled={!token || !likedByMe} onClick={() => void handleUnlike()}>
              Unlike
            </button>
          </div>
        </div>
      </article>

      <article className="card player-card">
        {buildSoundCloudEmbedUrl(track) ? (
          <iframe
            title={`soundcloud-${track.id}`}
            className="soundcloud-embed"
            src={buildSoundCloudEmbedUrl(track) || undefined}
            allow="autoplay"
          />
        ) : buildTrackAudioUrl(track) ? (
          <audio className="audio" controls preload="none" src={buildTrackAudioUrl(track) || undefined} onPlay={() => void handlePlay()} />
        ) : (
          <p className="muted">Track is not published yet.</p>
        )}
      </article>

      <article className="card">
        <h2>Comments</h2>
        <form className="form" onSubmit={submitComment}>
          <textarea value={commentText} onChange={(event) => setCommentText(event.target.value)} placeholder="Write a comment" />
          <button type="submit" disabled={!token || !commentText.trim()}>
            Add comment
          </button>
        </form>
        <div className="comments">
          {comments.map((comment) => (
            <article className="comment" key={comment.id}>
              <p className="muted">@{comment.user_id}</p>
              <p>{comment.text}</p>
            </article>
          ))}
          {comments.length === 0 ? <p className="muted">No comments yet.</p> : null}
        </div>
      </article>

      {isOwner ? (
        <article className="card">
          <h2>Edit Track</h2>
          <form className="form" onSubmit={saveTrack}>
            <label>
              Title
              <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
            </label>
            <label>
              Artist
              <input value={editArtist} onChange={(event) => setEditArtist(event.target.value)} />
            </label>
            <label>
              Genre
              <input value={editGenre} onChange={(event) => setEditGenre(event.target.value)} />
            </label>
            <label>
              Description
              <textarea value={editDescription} onChange={(event) => setEditDescription(event.target.value)} />
            </label>
            <label>
              Visibility
              <select value={editVisibility} onChange={(event) => setEditVisibility(event.target.value as Visibility)}>
                <option value="private">private</option>
                <option value="public">public</option>
                <option value="unlisted">unlisted</option>
              </select>
            </label>
            <div className="inline">
              <button type="submit" disabled={editBusy}>
                {editBusy ? "Saving..." : "Save"}
              </button>
              <button className="ghost" type="button" disabled={editBusy} onClick={() => void removeTrack()}>
                Delete
              </button>
            </div>
            {editMessage ? <p className="muted">{editMessage}</p> : null}
          </form>
        </article>
      ) : null}
    </section>
  );
}
