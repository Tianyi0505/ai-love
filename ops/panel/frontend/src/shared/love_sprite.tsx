import { Heart, Sparkles } from "lucide-react";

export function LoveSprite({ size = "medium" }: { size?: "small" | "medium" | "large" }) {
  return (
    <div className={`love-sprite love-sprite--${size}`} aria-hidden="true">
      <span className="love-sprite__antenna"><Sparkles /></span>
      <span className="love-sprite__ear love-sprite__ear--left" />
      <span className="love-sprite__ear love-sprite__ear--right" />
      <span className="love-sprite__face">
        <i className="love-sprite__eye love-sprite__eye--left" />
        <i className="love-sprite__eye love-sprite__eye--right" />
        <i className="love-sprite__smile" />
      </span>
      <span className="love-sprite__heart"><Heart fill="currentColor" /></span>
    </div>
  );
}
