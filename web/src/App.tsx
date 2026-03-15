import { FormEvent, useEffect, useState } from "react";
import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "./auth";
import { FeedPage } from "./pages/FeedPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { TrackPage } from "./pages/TrackPage";
import { UploadPage } from "./pages/UploadPage";

function AppLayout() {
  const { user, profile, loading, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [globalQuery, setGlobalQuery] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    setGlobalQuery(params.get("q") || "");
  }, [location.search]);

  function submitGlobalSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    const normalized = globalQuery.trim();
    if (normalized) {
      params.set("q", normalized);
    }
    navigate({ pathname: "/", search: params.toString() ? `?${params.toString()}` : "" });
  }

  return (
    <div className="shell">
      <header className="topbar sc-topbar">
        <div className="brand">
          <NavLink to="/" className="brand-link">
            <span className="brand-icon">SC</span>
            <span>SoundCloud</span>
          </NavLink>
        </div>

        <nav className="navlinks sc-navlinks">
          <NavLink to="/">Home</NavLink>
          {user ? <NavLink to="/upload">Upload</NavLink> : null}
          {user ? <NavLink to={`/profiles/${user.user_id}`}>Library</NavLink> : null}
          {!user ? <NavLink to="/login">Sign in</NavLink> : null}
        </nav>

        <form className="topbar-search" onSubmit={submitGlobalSearch}>
          <input
            value={globalQuery}
            onChange={(event) => setGlobalQuery(event.target.value)}
            placeholder="Search tracks, artists, genres"
          />
        </form>

        <div className="authbox">
          {loading ? <span className="muted">Session...</span> : null}
          {!loading && user ? (
            <>
              <NavLink className="profile-pill" to={`/profiles/${user.user_id}`}>
                {profile?.picture ? <img src={profile.picture} alt="avatar" /> : <span>{(profile?.username || user.user_id).slice(0, 1).toUpperCase()}</span>}
                <strong>{profile?.username ? `@${profile.username}` : user.user_id}</strong>
              </NavLink>
              <button className="ghost ghost-dark" onClick={logout}>
                Logout
              </button>
            </>
          ) : null}
        </div>
      </header>

      <div className="layout-grid">
        <aside className="rail left-rail">
          <div className="card rail-card">
            <h3>Discover</h3>
            <p className="muted">Fresh uploads and trending tracks from creators.</p>
            <NavLink to="/">Go to stream</NavLink>
          </div>

          {user ? (
            <div className="card rail-card">
              <h3>Your Space</h3>
              <p className="muted">Manage profile, avatar and your tracks.</p>
              <NavLink to={`/profiles/${user.user_id}`}>Open profile</NavLink>
            </div>
          ) : (
            <div className="card rail-card">
              <h3>Join Creators</h3>
              <p className="muted">Sign in and upload your first track.</p>
              <NavLink to="/login">Sign in now</NavLink>
            </div>
          )}
        </aside>

        <main className="content main-column">
          <Outlet />
        </main>

        <aside className="rail right-rail">
          <div className="card rail-card">
            <h3>Now Building</h3>
            <p className="muted">FastAPI microservices + React client with real upload pipeline.</p>
          </div>
          <div className="card rail-card">
            <h3>Tips</h3>
            <p className="muted">Open a track page to like, comment, and edit if you own it.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="page-loading">Loading session...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function MyProfileRedirect() {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="page-loading">Loading session...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Navigate to={`/profiles/${user.user_id}`} replace />;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<FeedPage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="tracks/:trackId" element={<TrackPage />} />
          <Route path="profiles/:userId" element={<ProfilePage />} />
          <Route
            path="upload"
            element={
              <RequireAuth>
                <UploadPage />
              </RequireAuth>
            }
          />
          <Route path="me" element={<MyProfileRedirect />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
