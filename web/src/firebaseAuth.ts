import { initializeApp, getApps } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup } from "firebase/auth";

import { FIREBASE_CONFIG, FIREBASE_ENABLED } from "./config";

let initialized = false;

function ensureFirebaseInitialized() {
  if (!FIREBASE_ENABLED) {
    throw new Error("Firebase env vars are not configured for web app");
  }

  if (!initialized && getApps().length === 0) {
    initializeApp(FIREBASE_CONFIG);
    initialized = true;
  }
}

export async function signInWithGoogle(): Promise<string> {
  ensureFirebaseInitialized();

  const auth = getAuth();
  const provider = new GoogleAuthProvider();
  const credentials = await signInWithPopup(auth, provider);
  const idToken = await credentials.user.getIdToken();

  if (!idToken) {
    throw new Error("Cannot get Firebase ID token");
  }

  return idToken;
}

export function firebaseEnabled(): boolean {
  return FIREBASE_ENABLED;
}
