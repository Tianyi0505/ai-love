import { Brain, Clock3 } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest, formatDate, type SelfMemory } from "../../core/api";
import { MemoryDocument } from "../../shared/memory_document";
import { PageHeader } from "../../shared/page_header";
import { PageError, PageLoading } from "../../shared/page_state";

export function SelfMemoryPage() {
  const [data, setData] = useState<SelfMemory | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest<SelfMemory>("/self-memory")
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, []);

  if (error) return <PageError message={error} />;
  if (data === null) return <PageLoading label="正在翻开她的心事手账" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="INNER DIARY · 心事手账"
        title="她写给自己的长信"
        description="这里收藏着她对自己的长期认知；每一次成长，都会悄悄写进同一本手账。"
      />
      {data.memory ? (
        <>
          <div className="document-meta">
            <span><Brain size={17} />{data.ai_id}</span>
            <span>手账版本 v{data.memory.version}</span>
            <span><Clock3 size={17} />{formatDate(data.memory.updated_at)}</span>
          </div>
          <MemoryDocument markdown={data.memory.markdown} />
        </>
      ) : (
        <section className="empty-memory">
          <span><Brain size={30} /></span>
          <h2>手账的第一页还是空白</h2>
          <p>这里不会放示例或假数据；第一份真实的自我记忆，会成为她亲手写下的第一页。</p>
        </section>
      )}
    </div>
  );
}
