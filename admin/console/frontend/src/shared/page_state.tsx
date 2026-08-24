import { AlertCircle, LoaderCircle } from "lucide-react";

export function PageLoading({ label = "正在读取真实数据" }: { label?: string }) {
  return (
    <div className="page-state" role="status">
      <LoaderCircle className="spin" size={26} />
      <span>{label}</span>
    </div>
  );
}

export function PageError({ message }: { message: string }) {
  return (
    <div className="page-state page-state--error" role="alert">
      <AlertCircle size={24} />
      <div>
        <strong>读取失败</strong>
        <span>{message}</span>
      </div>
    </div>
  );
}
