import { KeyRound, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { apiRequest } from "../../core/api";
import { PageHeader } from "../../shared/page_header";

export function SettingsPage({ onCredentialsChanged }: { onCredentialsChanged: (message: string) => void }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const result = await apiRequest<{ message: string }>("/credentials", {
        method: "POST",
        body: {
          current_password: currentPassword,
          username,
          password,
        },
      });
      onCredentialsChanged(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page settings-page">
      <PageHeader
        eyebrow="NEST SETTINGS · 小窝设置"
        title="守护这间记忆小屋"
        description="在这里更换守护者账号与小屋钥匙；保存后，所有现有通行证都会立即失效。"
      />
      <section className="settings-card">
        <div className="settings-card__intro">
          <span><KeyRound size={23} /></span>
          <div><h2>守护者通行证</h2><p>小屋钥匙会使用 Argon2 加密后妥善保存。</p></div>
        </div>
        <form className="settings-form" onSubmit={submit}>
          <label><span>现在的小屋钥匙</span><input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" required /></label>
          <label><span>新的守护者账号</span><input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
          <label><span>新的小屋钥匙</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required /></label>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button" type="submit" disabled={submitting}>
            <ShieldCheck size={18} />{submitting ? "正在更换钥匙…" : "保存新通行证"}
          </button>
        </form>
      </section>
    </div>
  );
}
