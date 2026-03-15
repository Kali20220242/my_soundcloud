import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { importSoundCloudTracks } from "../api";
import { useAuth } from "../auth";

export function SoundCloudImportPage() {
  const { token, user } = useAuth();
  const navigate = useNavigate();

  const [accessToken, setAccessToken] = useState("");
  const [limit, setLimit] = useState("200");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;

    setMessage(null);
    setError(null);

    if (!accessToken.trim()) {
      setError("SoundCloud access token is required");
      return;
    }

    setBusy(true);
    try {
      const parsedLimit = Math.max(1, Math.min(2000, Number(limit) || 200));
      const result = await importSoundCloudTracks(token, {
        access_token: accessToken.trim(),
        limit: parsedLimit,
      });

      setMessage(
        `Imported ${result.imported} tracks (created ${result.created}, updated ${result.updated}, skipped ${result.skipped}).`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page card narrow">
      <h1>Import from SoundCloud</h1>
      <p className="muted">
        Metadata-only import. We do not copy audio files, only track data and links.
      </p>

      <form className="form" onSubmit={submitImport}>
        <label>
          SoundCloud OAuth access token
          <textarea
            value={accessToken}
            onChange={(event) => setAccessToken(event.target.value)}
            placeholder="Paste your SoundCloud OAuth access token"
          />
        </label>

        <label>
          Max tracks to import
          <input value={limit} onChange={(event) => setLimit(event.target.value)} inputMode="numeric" />
        </label>

        <button type="submit" disabled={busy}>
          {busy ? "Importing..." : "Import tracks"}
        </button>
      </form>

      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      {user ? (
        <div className="inline">
          <button className="ghost" onClick={() => navigate(`/profiles/${user.user_id}`)}>
            Open profile
          </button>
          <Link to="/?scope=mine&sort=recent">Open my tracks</Link>
        </div>
      ) : null}
    </section>
  );
}
