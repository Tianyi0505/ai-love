import { Fingerprint, MessageCircleHeart, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest, type Personality } from "../../core/api";
import { PageHeader } from "../../shared/page_header";
import { PageError, PageLoading } from "../../shared/page_state";
import { LoveSprite } from "../../shared/love_sprite";

export function PersonalityPage() {
  const [personality, setPersonality] = useState<Personality | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest<Personality>("/personality")
      .then(setPersonality)
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, []);

  if (error) return <PageError message={error} />;
  if (personality === null) return <PageLoading label="正在调出她的灵魂底色" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="SOUL COLORS · 灵魂底色"
        title="她之所以是她"
        description="把生效人格轻轻摊开：她如何认识自己、如何表达，也如何守住重要的边界。"
        action={<span className="version-badge">v{personality.version}</span>}
      />
      <section className="identity-card">
        <div className="identity-card__avatar"><LoveSprite size="medium" /></div>
        <div><span>灵魂编号 · {personality.ai_id}</span><h2>{personality.name}</h2><p>{personality.identity}</p></div>
        <span className="identity-card__tape" aria-hidden="true">PERSONA</span>
      </section>
      <div className="detail-grid">
        <section className="detail-card">
          <div className="detail-card__title"><Sparkles size={20} /><h2>灵魂关键词</h2></div>
          <div className="tag-list">{personality.traits.map((trait) => <span key={trait}>{trait}</span>)}</div>
        </section>
        <section className="detail-card">
          <div className="detail-card__title"><MessageCircleHeart size={20} /><h2>她说话的样子</h2></div>
          <p>{personality.speaking_style}</p>
          <h3>藏在话里的小习惯</h3>
          {personality.catchphrases.length > 0 ? (
            <div className="tag-list">{personality.catchphrases.map((item) => <span key={item}>{item}</span>)}</div>
          ) : <p className="muted">她还没有留下固定的口头禅。</p>}
        </section>
        <section className="detail-card detail-card--wide">
          <div className="detail-card__title"><ShieldCheck size={20} /><h2>她认真守护的边界</h2></div>
          <ul className="soft-list">{personality.taboos.map((taboo) => <li key={taboo}>{taboo}</li>)}</ul>
        </section>
        <section className="fingerprint-card detail-card--wide">
          <Fingerprint size={19} />
          <div><span>这份灵魂底色的唯一指纹</span><code>{personality.fingerprint}</code></div>
        </section>
      </div>
    </div>
  );
}
