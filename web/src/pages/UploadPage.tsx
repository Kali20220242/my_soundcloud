import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { completeUpload, presignUpload } from "../api";
import { useAuth } from "../auth";
import type { Visibility } from "../types";

export function UploadPage() {
  const navigate = useNavigate();
  const { token } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("private");
  const [genre, setGenre] = useState("");
  const [description, setDescription] = useState("");

  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;

    setError(null);
    setMessage(null);

    if (!file) {
      setError("Choose an audio file");
      return;
    }
    if (!title.trim() || !artist.trim()) {
      setError("Title and artist are required");
      return;
    }

    setBusy(true);
    try {
      const presigned = await presignUpload(token, {
        filename: file.name,
        content_type: file.type || "audio/mpeg",
        title: title.trim(),
        artist: artist.trim(),
        visibility,
        genre: genre.trim() || undefined,
        description: description.trim() || undefined
      });

      const uploadResponse = await fetch(presigned.upload_url, {
        method: "PUT",
        headers: {
          "Content-Type": file.type || "audio/mpeg"
        },
        body: file
      });
      if (!uploadResponse.ok) {
        throw new Error(`Upload failed (${uploadResponse.status})`);
      }

      await completeUpload(token, presigned.track_id, presigned.object_key);
      setMessage("Track uploaded and queued for processing");
      navigate(`/tracks/${presigned.track_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot upload track");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page card narrow">
      <h1>Upload Track</h1>
      <p className="muted">Create new track and publish it into the feed after processing.</p>

      <form className="form" onSubmit={submitUpload}>
        <label>
          Audio file
          <input type="file" accept="audio/*" onChange={(event) => setFile(event.target.files?.[0] || null)} />
        </label>
        <label>
          Title
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label>
          Artist
          <input value={artist} onChange={(event) => setArtist(event.target.value)} />
        </label>
        <label>
          Genre
          <input value={genre} onChange={(event) => setGenre(event.target.value)} placeholder="lofi, techno, rap" />
        </label>
        <label>
          Description
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>
        <label>
          Visibility
          <select value={visibility} onChange={(event) => setVisibility(event.target.value as Visibility)}>
            <option value="private">private</option>
            <option value="public">public</option>
            <option value="unlisted">unlisted</option>
          </select>
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Uploading..." : "Upload"}
        </button>
      </form>

      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
