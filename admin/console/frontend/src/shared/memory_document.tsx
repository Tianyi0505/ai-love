import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MemoryDocument({ markdown }: { markdown: string }) {
  return (
    <article className="markdown-document">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
    </article>
  );
}
