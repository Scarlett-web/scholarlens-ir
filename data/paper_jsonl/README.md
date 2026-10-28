# 论文 JSONL 数据说明

本目录的 `papers_final.jsonl`是PDF经过解析、筛查、去重、核验、补入等操作后的最终数据，每行一条 UTF-8 JSON 记录，共 **859 条**。
本目录的 `paper_source_manifest.csv` 有 859 行数据，每行对应一条 JSONL 记录。字段约定以 [数据协议](../../docs/03_DATA_SCHEMA.md) 为准；本文件给出这份数据的实测情况。

## 字段与完整率

以下“空值”按字段约定统计：字符串 `""`、数组 `[]` 或 `null`。计数仅表示字段有无内容，不证明内容准确或正文完整。

| 字段 | JSON 类型 | 含义 | 空值条数 | 非空条数 |
| --- | --- | --- | ---: | ---: |
| `paper_id` | string | 稳定来源标识 | 0 | 859 |
| `source_file` | string | 原始 PDF 文件名 | 0 | 859 |
| `title` | string | 标题 | 0 | 859 |
| `authors` | array<string> | 按顺序排列的作者 | 2 | 857 |
| `date` | string | 有证据的完整发表日期，`YYYY-MM-DD` | 628 | 231 |
| `year` | integer/null | 有证据的发表年份 | 381 | 478 |
| `affiliation` | array<string> | 作者机构 | 94 | 765 |
| `address` | array<string> | 作者或机构地址 | 178 | 681 |
| `pages` | object/null | PDF 页数及可能的起止页 | 0 | 859 |
| `abstract` | string | 摘要 | 86 | 773 |
| `fulltext` | string | 保留段落边界的正文文本 | 0 | 859 |
| `pdf_path` | string | 相对项目根目录的 PDF 路径 | 0 | 859 |
| `parse_status` | string | `success` / `partial` / `error` | 0 | 859 |
| `errors` | array<string> | 缺失和异常标记 | 见下文 | 见下文 |

`parse_status` 为 `success` 的有 215 条，`partial` 的有 644 条，`error` 为 0 条。`errors` 为 `[]` 的有 215 条；这表示没有记录到问题，不能视为逐字段人工认证。`errors` 中的 `missing: date`、`missing: year` 等标记用于指出空值，不应当作字段内容。只有年份而无可信完整日期时，`date` 保持 `""`，`year` 可为整数。请勿把正文、参考文献、会议日程或下载时间中的日期自动填为发表日期。

全部 `pages` 均为 `{"first": null, "last": null, "count": 正整数}`；`count` 是原始 PDF 的**物理页数**，不是刊物印刷页码，未知的起止页保持 `null`。`fulltext` 全部非空，但“非空”不等于“完整、无误”。本数据不含历史兼容字段 `affiliations`、`full_text`。

## 正文乱码与索引使用

以下 4 条 `fulltext` 含有 Unicode 替代字符 `�`（U+FFFD），且 `errors` 带有 `unreadable_characters_in_fulltext`：

| 原始 PDF | `�` 个数 |
| --- | ---: |
| `rystalisgsuiucedumapsdatapubisgsquadsapdffilesavabgrept.pdf` | 550 |
| `sppsdpwgscgccaCollectionR71412004E9.pdf` | 489 |
| `wwcsjhueduscottpllpapersmicrokernel05.pdf` | 7 |
| `wwforgovbccahfdpubsDocsRrRr24.pdf` | 3830 |

此前核查中，这 4 份 PDF 的页面可以渲染；替代字符反映文本抽取或字体编码问题，不能据此认定原始 PDF 页面损坏。**建议暂不将这 4 条的 `fulltext` 建立正文索引**，待对照 PDF 重新抽取并核实后再纳入。其余元数据可按字段是否有值及证据情况单独使用。不要直接删除 `�` 或凭上下文猜字；该字符计数也不能衡量其余 855 条正文的全部质量。

对于检索，标题非空 859 条、作者非空 857 条、完整日期非空 231 条、机构非空 765 条、地址非空 681 条。对空字段应跳过相应字段的索引项，避免以空字符串或错误日期参与检索。

## 源文件清单与路径

`paper_source_manifest.csv` 的列顺序为 `paper_id,source_file,pdf_path,pdf_sha256`。`pdf_sha256` 是**原始 PDF 文件字节**的 SHA-256；它与 `paper_id` 中的哈希不是同一个值。每个清单条目的 `paper_id`、`source_file` 和 `pdf_path` 与 JSONL 对应记录一致。核验时 859 个 `paper_id`、PDF 路径和 PDF 哈希均唯一，没有逐字节相同的 PDF 副本。

`pdf_path` 以**项目根目录**为基准，使用正斜杠，例如 `../oriPDFs.rar/oriPDFs/example.pdf`。该路径指向本机项目目录之外的原始 PDF，迁移数据时须保持相同目录关系或显式重映射。
