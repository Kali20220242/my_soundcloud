export type TrackStatus = "processing" | "published" | "failed";
export type Visibility = "public" | "private" | "unlisted";

export interface AuthUser {
  user_id: string;
  email: string | null;
}

export interface UserProfile {
  user_id: string;
  email: string | null;
  name: string | null;
  picture: string | null;
  username: string | null;
  bio: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Track {
  id: string;
  owner_id: string;
  title: string;
  artist: string;
  visibility: Visibility;
  status: TrackStatus;
  raw_object_key: string;
  processed_object_key: string | null;
  description: string | null;
  genre: string | null;
  plays_count: number;
  source: "local" | "soundcloud";
  source_track_id: string | null;
  source_url: string | null;
  artwork_url: string | null;
  duration_seconds: number | null;
  loudness_lufs: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

export interface TrackListResponse {
  items: Track[];
  total: number;
}

export interface PresignRequest {
  filename: string;
  content_type: string;
  title: string;
  artist: string;
  visibility: Visibility;
  description?: string;
  genre?: string;
}

export interface PresignResponse {
  track_id: string;
  object_key: string;
  bucket: string;
  upload_url: string;
  expires_in_seconds: number;
}

export interface AvatarPresignResponse {
  object_key: string;
  bucket: string;
  upload_url: string;
  public_url: string;
  expires_in_seconds: number;
}

export interface SoundCloudImportResponse {
  fetched: number;
  imported: number;
  created: number;
  updated: number;
  skipped: number;
}

export interface LikeResponse {
  track_likes: number;
}

export interface Comment {
  id: string;
  user_id: string;
  text: string;
  created_at: string;
}

export interface CommentsResponse {
  items: Comment[];
}

export interface ProfileStats {
  followers: number;
  following: number;
}

export interface UpdateProfilePayload {
  name?: string;
  username?: string;
  bio?: string;
  picture?: string;
}

export interface UpdateTrackPayload {
  title?: string;
  artist?: string;
  visibility?: Visibility;
  description?: string;
  genre?: string;
}
