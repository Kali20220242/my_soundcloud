import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { firebaseEnabled } from "../firebaseAuth";
import { useAuth } from "../auth";

export function LoginPage() {
  const navigate = useNavigate();
  const { user, loginWithGoogle, loginWithToken } = useAuth();

  const [devToken, setDevToken] = useState("dev:alice:alice@example.com:Alice");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      navigate("/", { replace: true });
    }
  }, [user, navigate]);

  async function submitDevToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await loginWithToken(devToken.trim());
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  async function signInGoogle() {
    setBusy(true);
    setError(null);
    try {
      await loginWithGoogle();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page card narrow">
      <h1>Login</h1>
      <p className="muted">Use Firebase Google auth or development token.</p>

      <form className="form" onSubmit={submitDevToken}>
        <label>
          Dev ID token
          <input
            value={devToken}
            onChange={(event) => setDevToken(event.target.value)}
            placeholder="dev:alice:alice@example.com:Alice"
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Signing in..." : "Login with dev token"}
        </button>
      </form>

      <button className="secondary" onClick={() => void signInGoogle()} disabled={busy || !firebaseEnabled()}>
        Continue with Google
      </button>

      {!firebaseEnabled() ? <p className="muted">Firebase config is missing, Google login is disabled.</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
