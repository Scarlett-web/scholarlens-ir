# 03 统一论文 JSONL 数据格式

## 1. 约定

- 文件格式为 UTF-8，每行一个 JSON 对象；不得把整批数据包装成 JSON 数组。
- 所有字段都可缺失。缺失字符串使用 `""`，缺失数组使用 `[]`，未知数值使用 `null`；不能用猜测值、`N/A` 或虚构内容代替。
- `paper_id` 必须稳定、唯一、可从来源追溯，建议使用规范化来源文件哈希或会议确认的规则。
- `date` 使用 ISO-8601 日期字符串 `YYYY-MM-DD`；只有年份时 `date` 为空、`year` 保留整数年份。

## 2. 字段表

| 字段 | JSON 类型 | 必须 | 说明 | 缺失值 |
|---|---|---|---|---|
| `paper_id` | string | 是（生成后） | 稳定论文 ID | 生成失败时记录错误，不编造 |
| `title` | string | 否 | 论文标题，保留原文 | `""` |
| `authors` | array<string> | 否 | 按论文顺序的作者姓名 | `[]` |
| `date` | string | 否 | 完整发表日期，ISO-8601 | `""` |
| `year` | integer/null | 否 | 发表年份 | `null` |
| `affiliation` | array<string> | 否 | 作者机构 | `[]` |
| `address` | array<string> | 否 | 机构/作者地址 | `[]` |
| `pages` | object/null | 否 | 页码信息，见下方结构 | `null` |
| `abstract` | string | 否 | 摘要纯文本 | `""` |
| `fulltext` | string | 否 | 正文纯文本 | `""` |
| `pdf_path` | string | 否 | 本地 PDF 相对路径或受控 URI；路径基准见对应数据集说明 | `""` |
| `source_file` | string | 否 | 原始 PDF 文件名 | `""` |
| `parse_status` | string | 是 | `success`、`partial` 或 `error` | `"error"` |
| `errors` | array<string> | 否 | 缺失字段或解析失败说明 | `[]` |

`pages` 结构：`{"first": 1, "last": 10, "count": 10}`；未知子字段为 `null`。可选扩展字段必须在 schema 版本中登记，不得改变核心字段语义。

本次 TEI 转换输入为 XML 目录及对应 PDF 目录，输出 UTF-8 JSONL 和质量报告；每个 XML 对应一条记录。`paper_id` 为来源 PDF 文件名和文件内容 SHA-256 的组合哈希，避免同内容不同来源发生 ID 冲突；无法找到 PDF 时使用 XML 内容哈希并在 `errors` 记录。`source_file` 从 XML 文件名映射，无法确认时为空；原始 TEI 转换输出的 `pdf_path` 相对于指定 PDF 根目录。`date` 仅从论文头部明确标记为发表的完整日期提取，不从参考文献猜测；`pages` 仅从论文头部页码提取，未知为 `null`。正文从 TEI `body` 的段落提取，以空行保留段落边界，不包含 `back` 中的参考文献；缺失字段记录于 `errors` 并继续处理。

## 3. Mock 样例（非真实论文）

```json
{"paper_id":"mock-0001","title":"Mock: Information Retrieval Evaluation","authors":["Mock Author A","Mock Author B"],"date":"2026-01-15","year":2026,"affiliation":["Mock University"],"address":["Mock City"],"pages":{"first":1,"last":8,"count":8},"abstract":"This is a Mock record for UI contract testing.","fulltext":"Mock fulltext used only for front-end development.","pdf_path":"data/sample/mock-0001.pdf"}
{"paper_id":"mock-0002","title":"","authors":[],"date":"","year":null,"affiliation":[],"address":[],"pages":null,"abstract":"","fulltext":"","pdf_path":""}
```


## 4. 处理与质量规则

- XML 转换器输入为 TEI XML 和来源文件清单，输出 JSONL、错误 JSONL、字段完整率报告；负责人组员 A。
- 索引器输入为通过 schema 校验的 JSONL，输出索引文档数、跳过记录和映射版本；负责人组长。
- API 输入/输出只暴露允许字段，不能直接返回本地绝对路径或密钥；负责人组长。
- 质量报告至少包含：总记录数、解析成功/失败数、六字段非空率、摘要/正文长度分布、重复候选和无法定位来源的记录数。

