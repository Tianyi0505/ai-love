import { ArrowLeft, Search, UsersRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import {
  apiRequest,
  formatDate,
  qqAvatarUrl,
  type People,
  type PersonMemory,
} from "../../core/api";
import { ContactCard } from "../../shared/contact_card";
import { MemoryDocument } from "../../shared/memory_document";
import { PageHeader } from "../../shared/page_header";
import { PageError, PageLoading } from "../../shared/page_state";

export function PeopleMemoryPage() {
  const [query, setQuery] = useState("");
  const [data, setData] = useState<People | null>(null);
  const [error, setError] = useState("");

  function load(search: string) {
    setError("");
    const params = new URLSearchParams();
    if (search.trim()) params.set("q", search.trim());
    apiRequest<People>(`/people${params.size > 0 ? `?${params.toString()}` : ""}`)
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }

  useEffect(() => load(""), []);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    load(query);
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="BOND ALBUM · 羁绊图鉴"
        title="被她认真记住的人"
        description="每一张小卡片，都是一段已经形成长期记忆的 QQ 羁绊。"
      />
      <form className="search-bar" onSubmit={search} role="search">
        <Search size={19} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="寻找一个名字，或输入 QQ 号"
          aria-label="搜索人物"
        />
        <button type="submit">找一找</button>
      </form>
      {error ? <PageError message={error} /> : data === null ? <PageLoading /> : data.people.length > 0 ? (
        <section className="contact-grid" aria-label="人物长期记忆">
          {data.people.map((person) => <ContactCard key={person.person_id} person={person} />)}
        </section>
      ) : (
        <section className="empty-memory">
          <span><UsersRound size={30} /></span>
          <h2>图鉴里还没有这段羁绊</h2>
          <p>这里仅收藏真实存在的 QQ 联系人与长期记忆文档。</p>
        </section>
      )}
    </div>
  );
}

export function PersonMemoryPage() {
  const { personId } = useParams<{ personId: string }>();
  const [data, setData] = useState<PersonMemory | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest<PersonMemory>(`/people/${personId}/memory`)
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, [personId]);

  if (error) return <PageError message={error} />;
  if (data === null) return <PageLoading label="正在展开这张羁绊卡片" />;

  return (
    <div className="page person-detail-page">
      <Link className="back-button" to="/memory/people"><ArrowLeft size={18} />回到羁绊图鉴</Link>
      <header className="person-header">
        <img src={qqAvatarUrl(data.person.qq)} alt={`${data.person.display_name} 的 QQ 头像`} />
        <div>
          <span className="eyebrow">A PRECIOUS BOND · 羁绊档案</span>
          <h1>{data.person.display_name}</h1>
          <p>QQ {data.person.qq}</p>
        </div>
        <dl>
          <div><dt>记忆页码</dt><dd>v{data.person.version}</dd></div>
          <div><dt>最近落笔</dt><dd>{formatDate(data.person.updated_at)}</dd></div>
        </dl>
      </header>
      <MemoryDocument markdown={data.memory.markdown} />
    </div>
  );
}
