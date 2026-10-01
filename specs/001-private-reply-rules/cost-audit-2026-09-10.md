# 2026-09-10 DeepSeek 记忆输出预算与费用依据

## 计数结果

DeepSeek 官方离线 tokenizer 对生产联系人文档给出以下结果：

| 材料 | 字符数 | token 数 |
| --- | ---: | ---: |
| Markdown 文档 | 6103 | 4004 |
| 完整结构化参数 | 6302 | 4341 |
| 含 8 个 Episode、13 个 Atom 的输入 | — | 4898 |

完整输出需求至少 4341 token，模型预算的有效条件为覆盖完整结果及新增内容。

当日数据库记录 107 次成功 Episode 提取、28 次成功长期文档合并，最晚成功合并为 23:34。37 份长期文档和 11 份聚合文档均通过标题及章节校验。模型请求的 thinking.type 值为 disabled。

## 配置结果

- 记忆输出预算为 16384 token，请求超时为 240 秒。
- 完整 Markdown 长度上限为 12000 字符。
- 记忆提取及聚合恢复间隔为 3600 秒。
- 普通聊天输出预算为 4096 token。

上述预算对应完整文档契约，调用节奏具有明确资源范围。

## 费用口径

按 2026-09-10 Flash 单价，4096 个输出 token 的费用为闲时约 0.018432 元、高峰约 0.036864 元；输入费用依据实际 4898 token 与缓存单价。精确历史费用的有效来源为提供方历史账单及逐请求 usage，量级估算采用该价格条件。

## 官方依据

- [DeepSeek V4 价格](https://api-docs.deepseek.com/zh-cn/news/news260813/)
- [模型与计价](https://api-docs.deepseek.com/quick_start/pricing/)
- [Token 与官方 tokenizer](https://api-docs.deepseek.com/quick_start/token_usage/)
- [余额字段](https://api-docs.deepseek.com/api/get-user-balance/)
