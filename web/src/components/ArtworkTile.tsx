interface ArtworkTileProps {
  seed: string;
  title?: string;
  size?: "sm" | "md" | "lg";
  imageUrl?: string | null;
}

function hueFromSeed(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return hash % 360;
}

export function ArtworkTile({ seed, title, size = "md", imageUrl }: ArtworkTileProps) {
  const hue = hueFromSeed(seed);
  const hue2 = (hue + 36) % 360;
  const style = {
    background: `linear-gradient(140deg, hsl(${hue}, 88%, 56%), hsl(${hue2}, 72%, 34%))`
  };

  return (
    <div className={`artwork artwork-${size}`} style={style} aria-label={title || "track artwork"}>
      {imageUrl ? <img src={imageUrl} alt={title || "artwork"} className="artwork-image" loading="lazy" /> : null}
      <div className="artwork-fade" />
      <span className="artwork-mark">SC</span>
    </div>
  );
}
