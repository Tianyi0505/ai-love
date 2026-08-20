import {
  BookHeart,
  Brain,
  ExternalLink,
  Fingerprint,
  HeartHandshake,
  Sparkles,
  UsersRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  apiRequest,
  type People,
  type Personality,
  type QuickEntry,
  type SelfMemory,
} from "../../core/api";
import { PageHeader } from "../../shared/page_header";
import { PageError, PageLoading } from "../../shared/page_state";
import { LoveSprite } from "../../shared/love_sprite";

type OverviewData = {
  personality: Personality;
  selfMemory: SelfMemory;
  people: People;
  entries: QuickEntry[];
};

export function OverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiRequest<Personality>("/personality"),
      apiRequest<SelfMemory>("/self-memory"),
      apiRequest<People>("/people"),
      apiRequest<{ entries: QuickEntry[] }>("/entries"),
    ])
      .then(([personality, selfMemory, people, entries]) =>
        setData({ personality, selfMemory, people, entries: entries.entries }),
      )
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, []);

  if (error) return <PageError message={error} />;
  if (data === null) return <PageLoading />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="WELCOME BACK · 心动首页"
        title={`欢迎回来，${data.personality.name} 在这里`}
        description="推开门，就能看见她的灵魂底色、心事手账和珍藏的每一段羁绊。"
      />

      <section className="hero-card">
        <div className="hero-card__scene">
          <LoveSprite size="large" />
          <span className="hero-card__speech">这里住着一颗会记住你的心</span>
          <span className="hero-card__star hero-card__star--one"><Sparkles size={18} /></span>
          <span className="hero-card__star hero-card__star--two"><Sparkles size={13} /></span>
        </div>
        <div className="hero-card__copy">
          <span className="hero-card__status"><span /> 人格已载入</span>
          <span className="eyebrow">CURRENT SOUL</span>
          <h2>{data.personality.name} 的心灵小屋</h2>
          <p>{data.personality.identity}</p>
        </div>
        <dl className="hero-card__facts">
          <div><span><Fingerprint size={17} /></span><dt>灵魂编号</dt><dd>{data.personality.ai_id}</dd></div>
          <div><span><BookHeart size={17} /></span><dt>底色版本</dt><dd>v{data.personality.version}</dd></div>
          <div><span><HeartHandshake size={17} /></span><dt>珍藏羁绊</dt><dd>{data.people.people.length} 份</dd></div>
        </dl>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div><span className="eyebrow">HEART MAP</span><h2>她的内心宇宙</h2></div>
          <span className="section-heading__note">三颗星星，拼成完整的她</span>
        </div>
        <div className="summary-grid">
          <Link className="summary-card summary-card--soul" to="/personality">
            <span className="summary-card__icon"><Sparkles size={21} /></span><small>01 · 她是谁</small><strong>灵魂底色</strong>
            <span>{data.personality.traits.join(" · ")}</span><b>轻轻翻开 →</b>
          </Link>
          <Link className="summary-card summary-card--diary" to="/memory/self">
            <span className="summary-card__icon"><Brain size={21} /></span><small>02 · 她记得自己</small><strong>心事手账</strong>
            <span>{data.selfMemory.memory ? `已经写到第 v${data.selfMemory.memory.version} 版` : "等待写下第一页"}</span><b>读一读她 →</b>
          </Link>
          <Link className="summary-card summary-card--bond" to="/memory/people">
            <span className="summary-card__icon"><UsersRound size={21} /></span><small>03 · 她记得你们</small><strong>羁绊图鉴</strong>
            <span>珍藏了 {data.people.people.length} 个人的故事</span><b>寻找羁绊 →</b>
          </Link>
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div><span className="eyebrow">ANYWHERE DOOR</span><h2>通往外面的任意门</h2></div>
          <span className="section-heading__note">登录后才会出现的秘密通道</span>
        </div>
        <div className="entry-grid">
          {data.entries.map((entry) => {
            return (
              <a key={entry.key} className="entry-card" href={entry.url} target="_blank" rel="noreferrer">
                <span className={`entry-card__icon entry-card__icon--${entry.key}`}><ExternalLink size={22} /></span>
                <div><strong>{entry.name}</strong><span>{entry.description}</span></div>
                <ExternalLink size={17} />
              </a>
            );
          })}
        </div>
      </section>
    </div>
  );
}
