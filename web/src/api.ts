import { API_BASE_URL, MINIO_BUCKET, MINIO_PUBLIC_ENDPOINT } from "./config";
import type {
  AuthUser,
  AvatarPresignResponse,
  CommentsResponse,
  LikeResponse,
  PresignRequest,
  PresignResponse,
  ProfileStats,
  Track,
  TrackListResponse,
  UpdateProfilePayload,
  UpdateTrackPayload,
  UserProfile,
  Visibility
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: {
    method?: "GET" | "POST" | "PATCH" | "DELETE";
    token?: string | null;
    body?: unknown;
  } = {}
): Promise<T> {
  const { method = "GET", token, body } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Unexpected error" }));
    const detail = payload.detail || `Request failed with status ${response.status}`;
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

function encodeQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined) {
      return;
    }
    query.set(key, String(value));
  });
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export function verifyToken(idToken: string): Promise<AuthUser> {
  return request<AuthUser>("/auth/verify", {
    method: "POST",
    body: { id_token: idToken }
  });
}

export function getMe(token: string): Promise<UserProfile> {
  return request<UserProfile>("/me", { token });
}

export function updateMe(token: string, payload: UpdateProfilePayload): Promise<UserProfile> {
  return request<UserProfile>("/me", {
    method: "PATCH",
    token,
    body: payload
  });
}

export function getUser(userId: string): Promise<UserProfile> {
  return request<UserProfile>(`/users/${userId}`);
}

export function listTracks(filters?: {
  ownerId?: string;
  status?: string;
  visibility?: Visibility;
  q?: string;
  sort?: "recent" | "popular";
  limit?: number;
  offset?: number;
  token?: string | null;
}): Promise<TrackListResponse> {
  const suffix = encodeQuery({
    owner_id: filters?.ownerId,
    status: filters?.status,
    visibility: filters?.visibility,
    q: filters?.q,
    sort: filters?.sort,
    limit: filters?.limit,
    offset: filters?.offset
  });

  return request<TrackListResponse>(`/tracks${suffix}`, {
    token: filters?.token
  });
}

export function getTrack(trackId: string, token?: string | null): Promise<Track> {
  return request<Track>(`/tracks/${trackId}`, { token });
}

export function updateTrack(token: string, trackId: string, payload: UpdateTrackPayload): Promise<Track> {
  return request<Track>(`/tracks/${trackId}`, {
    method: "PATCH",
    token,
    body: payload
  });
}

export function deleteTrack(token: string, trackId: string): Promise<{ status: string; track_id: string }> {
  return request<{ status: string; track_id: string }>(`/tracks/${trackId}`, {
    method: "DELETE",
    token
  });
}

export function registerPlay(trackId: string, token?: string | null): Promise<{ plays_count: number }> {
  return request<{ plays_count: number }>(`/tracks/${trackId}/play`, {
    method: "POST",
    token
  });
}

export function presignUpload(token: string, payload: PresignRequest): Promise<PresignResponse> {
  return request<PresignResponse>("/uploads/presign", {
    method: "POST",
    token,
    body: payload
  });
}

export function completeUpload(token: string, trackId: string, objectKey: string): Promise<{ status: string; job_id: string }> {
  return request<{ status: string; job_id: string }>("/uploads/complete", {
    method: "POST",
    token,
    body: { track_id: trackId, object_key: objectKey }
  });
}

export function presignAvatarUpload(
  token: string,
  payload: { filename: string; content_type: string }
): Promise<AvatarPresignResponse> {
  return request<AvatarPresignResponse>("/uploads/avatar/presign", {
    method: "POST",
    token,
    body: payload
  });
}

export function getLikeCount(trackId: string): Promise<LikeResponse> {
  return request<LikeResponse>(`/social/likes/${trackId}/count`);
}

export function likeTrack(token: string, trackId: string): Promise<LikeResponse> {
  return request<LikeResponse>("/social/likes", {
    method: "POST",
    token,
    body: { track_id: trackId }
  });
}

export function unlikeTrack(token: string, trackId: string): Promise<LikeResponse> {
  return request<LikeResponse>(`/social/likes/${trackId}`, {
    method: "DELETE",
    token
  });
}

export function listComments(trackId: string): Promise<CommentsResponse> {
  return request<CommentsResponse>(`/social/comments/${trackId}`);
}

export function addComment(token: string, trackId: string, text: string): Promise<{ comment_id: string }> {
  return request<{ comment_id: string }>("/social/comments", {
    method: "POST",
    token,
    body: { track_id: trackId, text }
  });
}

export function follow(token: string, targetUserId: string): Promise<{ followers: number }> {
  return request<{ followers: number }>("/social/follows", {
    method: "POST",
    token,
    body: { target_user_id: targetUserId }
  });
}

export function unfollow(token: string, targetUserId: string): Promise<{ followers: number }> {
  return request<{ followers: number }>(`/social/follows/${targetUserId}`, {
    method: "DELETE",
    token
  });
}

export function profileStats(userId: string): Promise<ProfileStats> {
  return request<ProfileStats>(`/social/profiles/${userId}/stats`);
}

function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

export function buildTrackAudioUrl(track: Track): string | null {
  if (track.status !== "published" || !track.processed_object_key) {
    return null;
  }

  return joinUrl(joinUrl(MINIO_PUBLIC_ENDPOINT, MINIO_BUCKET), track.processed_object_key);
}
