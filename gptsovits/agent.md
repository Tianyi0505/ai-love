### Agent System

**GPT-SoVITS Service** (`gptsovits/gpt_sovits_service.py`):

- 进程入口是 `python -m gptsovits.gpt_sovits_service`；`GPTSoVITSService` 继承 `BaseService`，以 `gptsovits` 注册到 Nacos，同时承载 FastAPI HTTP 接口和 NATS 语音请求订阅。
- 引擎按 `ai_love.gptsovits` entry point 动态加载。`provider` 决定具体引擎，语音引用按 `ai_id` 注入；新增引擎应实现 `SpeechEngine`，不要修改服务编排入口。
- `serve()` 由 Uvicorn 驱动，退出时必须调用 `stop()`，由 `SynthesisService.close()` 继续关闭引擎和它持有的 HTTP client。

**Synthesis Boundary** (`gptsovits/synthesis_service.py`, `gptsovits/synthesis_api.py`):

- `SynthesisRequestPolicy` 统一限制 `ai_id` 和文本长度；HTTP `/synthesize` 与 NATS `ai.speech.request` 共享同一个 `SynthesisService`。
- `synthesize()` 生成音频文件并返回可消费的结果；`preview()` 用于直播语音预合成/播放链路。文件名、目录、扩展名和 PCM 时长换算由 output 配置控制。
- `GPTSoVITSEngine` 调用外部 GPT-SoVITS HTTP 服务；`MimoEngine` 是另一 entry point 实现。引擎负责 provider 协议，服务层只负责编排和策略。

**Runtime Configuration** (`service.gptsovits`):

- `http`：绑定地址、端口和日志级别。
- `request_limits`：AI ID 与合成文本的长度边界。
- `engine`：provider、请求超时及 provider 专属参数。
- `voices`：按 `ai_id` 保存参考音频等声音参数；`output` 控制本地音频目录与格式。
