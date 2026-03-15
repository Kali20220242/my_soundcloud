import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  follow,
  getUser,
  listTracks,
  presignAvatarUpload,
  profileStats,
  unfollow,
  updateMe
} from "../api";
import { useAuth } from "../auth";
import { ArtworkTile } from "../components/ArtworkTile";
import type { Track, UserProfile } from "../types";

export function ProfilePage() {
  const { userId } = useParams<{ userId: string }>();
  const { token, user, profile: myProfile, setProfile } = useAuth();

  const [profile, setLoadedProfile] = useState<UserProfile | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [followers, setFollowers] = useState(0);
  const [following, setFollowing] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [bio, setBio] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [avatarBusy, setAvatarBusy] = useState(false);

  const isOwner = useMemo(() => {
    if (!profile || !user) return false;
    return profile.user_id === user.user_id;
  }, [profile, user]);

  useEffect(() => {
    if (!userId) {
      setError("Profile id is missing");
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);

    void Promise.all([
      getUser(userId),
      profileStats(userId),
      listTracks({ ownerId: userId, token, sort: "recent", limit: 100 })
    ])
      .then(([profileResponse, statsResponse, tracksResponse]) => {
        if (!active) return;

        setLoadedProfile(profileResponse);
        setFollowers(statsResponse.followers);
        setFollowing(statsResponse.following);
        setTracks(tracksResponse.items);

        setName(profileResponse.name || "");
        setUsername(profileResponse.username || "");
        setBio(profileResponse.bio || "");
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Cannot load profile");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [userId, token]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !isOwner || !profile) return;

    const payload: { name?: string; username?: string; bio?: string } = {};
    if (name !== (profile.name || "")) payload.name = name;
    if (username !== (profile.username || "")) payload.username = username;
    if (bio !== (profile.bio || "")) payload.bio = bio;

    if (Object.keys(payload).length === 0) {
      setMessage("No changes");
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateMe(token, payload);
      setLoadedProfile(updated);
      setProfile(updated);
      setMessage("Profile saved");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Cannot save profile");
    } finally {
      setSaving(false);
    }
  }

  async function uploadAvatar(file: File) {
    if (!token || !isOwner) return;

    setAvatarBusy(true);
    setMessage(null);
    try {
      const presign = await presignAvatarUpload(token, {
        filename: file.name,
        content_type: file.type || "image/jpeg"
      });

      const upload = await fetch(presign.upload_url, {
        method: "PUT",
        headers: {
          "Content-Type": file.type || "image/jpeg"
        },
        body: file
      });
      if (!upload.ok) {
        throw new Error(`Avatar upload failed (${upload.status})`);
      }

      const updated = await updateMe(token, { picture: presign.public_url });
      setLoadedProfile(updated);
      setProfile(updated);
      setMessage("Avatar updated");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Cannot upload avatar");
    } finally {
      setAvatarBusy(false);
    }
  }

  async function handleFollow() {
    if (!token || !profile) return;
    const response = await follow(token, profile.user_id);
    setFollowers(response.followers);
  }

  async function handleUnfollow() {
    if (!token || !profile) return;
    const response = await unfollow(token, profile.user_id);
    setFollowers(response.followers);
  }

  if (loading) {
    return <div className="page-loading">Loading profile...</div>;
  }

  if (error || !profile) {
    return (
      <section className="page card narrow">
        <h1>Profile</h1>
        <p className="error">{error || "Profile not found"}</p>
      </section>
    );
  }

  return (
    <section className="page profile-page">
      <article className="card profile-hero">
        <div className="inline split">
          <h1>{profile.name || profile.username || profile.user_id}</h1>
          <span className="muted">@{profile.username || profile.user_id}</span>
        </div>

        <div className="profile-head">
          <div className="avatar-wrap">
            {profile.picture ? <img className="avatar" src={profile.picture} alt={`${profile.user_id} avatar`} /> : <div className="avatar placeholder">No avatar</div>}
          </div>
          <div className="stack">
            <div className="inline">
              <span className="badge ok">Followers: {followers}</span>
              <span className="badge ok">Following: {following}</span>
            </div>
            {profile.bio ? <p>{profile.bio}</p> : <p className="muted">No bio yet.</p>}
            {!isOwner && token ? (
              <div className="inline">
                <button onClick={() => void handleFollow()}>Follow</button>
                <button className="ghost" onClick={() => void handleUnfollow()}>
                  Unfollow
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </article>

      {isOwner ? (
        <article className="card">
          <h2>Edit profile</h2>
          <form className="form" onSubmit={saveProfile}>
            <label>
              Display name
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label>
              Username
              <input value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <label>
              Bio
              <textarea value={bio} onChange={(event) => setBio(event.target.value)} />
            </label>
            <button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save profile"}
            </button>
          </form>

          <div className="form">
            <label>
              Avatar image
              <input
                type="file"
                accept="image/*"
                disabled={avatarBusy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    void uploadAvatar(file);
                  }
                }}
              />
            </label>
            <p className="muted">Upload updates your profile picture immediately.</p>
          </div>

          {message ? <p className="muted">{message}</p> : null}
        </article>
      ) : null}

      <article className="card">
        <div className="inline split">
          <h2>Tracks</h2>
          {isOwner ? <Link to="/upload">Upload new track</Link> : null}
        </div>
        <div className="stream-list">
          {tracks.map((track) => (
            <article key={track.id} className="card stream-item stream-item-compact">
              <ArtworkTile seed={track.id} title={track.title} size="sm" />
              <div className="stream-body">
                <h3>{track.title}</h3>
                <p className="muted">{track.artist}</p>
                <div className="inline">
                  <span className="badge">{track.status}</span>
                  <span className="badge">{track.visibility}</span>
                  <span className="badge">plays: {track.plays_count}</span>
                </div>
                {track.genre ? <p className="muted">{track.genre}</p> : null}
                <Link to={`/tracks/${track.id}`}>Open track</Link>
              </div>
            </article>
          ))}
        </div>
        {tracks.length === 0 ? <p className="muted">No tracks yet.</p> : null}
      </article>

      {myProfile && isOwner ? <p className="muted">Logged in as @{myProfile.username || myProfile.user_id}</p> : null}
    </section>
  );
}
