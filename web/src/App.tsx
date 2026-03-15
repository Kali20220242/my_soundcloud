import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import { FeedPage } from "./pages/FeedPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { TrackPage } from "./pages/TrackPage";
import { UploadPage } from "./pages/UploadPage";

function AppLayout() {
  const { user, profile, loading, logout } = useAuth();

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <NavLink to="/">SoundCloud Clone</NavLink>
        </div>
        <nav className="navlinks">
          <NavLink to="/">Feed</NavLink>
          {user ? <NavLink to="/upload">Upload</NavLink> : null}
          {user ? <NavLink to={`/profiles/${user.user_id}`}>My Profile</NavLink> : null}
          {!user ? <NavLink to="/login">Login</NavLink> : null}
        </nav>
        <div className="authbox">
          {loading ? <span className="muted">Session...</span> : null}
          {!loading && user ? (
            <>
              <span className="muted">{profile?.username ? `@${profile.username}` : user.user_id}</span>
              <button className="ghost" onClick={logout}>
                Logout
              </button>
            </>
          ) : null}
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
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
