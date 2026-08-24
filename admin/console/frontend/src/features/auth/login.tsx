import { Heart, LockKeyhole, Sparkles, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import { apiRequest, type Session } from "../../core/api";
import { LoveSprite } from "../../shared/love_sprite";

type LoginPageProps = {
  notice: string;
  onLogin: (session: Session) => void;
};

export function LoginPage({ notice, onLogin }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const session = await apiRequest<Session>("/login", {
        method: "POST",
        body: { username, password },
      });
      onLogin(session);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-decoration login-decoration--one" />
      <div className="login-decoration login-decoration--two" />
      <section className="login-card">
        <div className="login-card__story">
          <span className="login-card__logo"><Heart size={15} fill="currentColor" /> ai-love</span>
          <div className="login-card__sprite">
            <LoveSprite size="large" />
            <span className="login-speech">等你回来很久啦</span>
          </div>
          <div className="login-card__story-copy">
            <span className="eyebrow">WELCOME HOME</span>
            <h1>回到她的<br />小宇宙</h1>
            <p>人格、心事和每一段羁绊，都被温柔地收藏在这里。</p>
          </div>
          <div className="login-stickers" aria-hidden="true">
            <span><Sparkles size={14} /> 灵魂底色</span>
            <span><Heart size={14} /> 羁绊记忆</span>
          </div>
        </div>
        <div className="login-card__form-side">
          <div className="login-card__heading">
            <span className="eyebrow">守护者通行证</span>
            <h2>欢迎回来呀</h2>
            <p>用你的专属钥匙，打开这间记忆小屋。</p>
          </div>
          <form className="login-form" onSubmit={submit}>
            <label>
              <span>守护者账号</span>
              <div className="field">
                <UserRound size={18} />
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  required
                />
              </div>
            </label>
            <label>
              <span>小屋钥匙</span>
              <div className="field">
                <LockKeyhole size={18} />
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
            </label>
            {notice && <p className="form-notice">{notice}</p>}
            {error && <p className="form-error">{error}</p>}
            <button className="primary-button login-button" type="submit" disabled={submitting}>
              {submitting ? "正在打开小屋…" : "回到 ai-love"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
