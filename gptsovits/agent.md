# 语音合成运行边界


现有入口为 `python -m gptsovits.gpt_sovits_service`。GPTSoVITSService 承载 FastAPI HTTP 与 NATS 请求，共用 SynthesisService。

## 合成结果

- HTTP /synthesize 和 NATS ai.speech.request 适用同一 SynthesisRequestPolicy。
- 合法 ai_id 与文本长度满足 request_limits。
- synthesize() 返回可消费音频，preview() 提供预合成结果。
- provider 对应 ai_love.gptsovits entry point 中的 SpeechEngine；GPTSoVITSEngine 和 MimoEngine 各自提供供应商协议适配。
- 声音引用按 ai_id 隔离，文件名、目录、扩展名及 PCM 时长由 output 配置确定。
- 服务停止结果包含 SynthesisService、引擎与 HTTP client 资源释放。

service.gptsovits 包含 http、request_limits、engine、voices 和 output。敏感连接参数由部署环境提供。
