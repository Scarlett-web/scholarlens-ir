# JSONL 数据处理脚本说明

最终交付文件为 [`data/paper_jsonl/papers_final.jsonl`](../data/paper_jsonl/papers_final.jsonl)，与本目录的 `papers_verified.jsonl` 逐字节相同，共 859 条。对应的[数据说明](../data/paper_jsonl/README.md)列出字段完整率、正文乱码和索引注意事项；[数据协议](../docs/03_DATA_SCHEMA.md)定义字段类型及缺失值。以下说明现有脚本的作用和这份数据的实际形成过程，不表示重新运行脚本即可自动重现全部人工核查结果。

## 数据形成过程

1. `tei_to_jsonl.py` 将 GROBID TEI XML 逐个转为 UTF-8 JSONL。它读取标题、作者、发表日期/年份、机构、地址、摘要和 TEI `body` 段落；清理字段空白、保留正文段落边界，坏 XML 或字段缺失写入 `errors` 后继续处理其他文件。可选报告统计数量、字段完整率、重复和失败。最初的 `papers.jsonl` 有 994 条。
2. `deduplicate_jsonl.py` 按原始 PDF **全部字节**的 SHA-256 去重；同一哈希组中按元数据完整度、错误数、正文长度和来源文件名决定保留记录。初次去重删除 129 条重复来源记录，涉及 92 组相同 PDF；另有 1 条无效来源记录移除后，历史去重文件为 864 条。脚本还包含补 PDF 物理页数、按 PDF 证据修正或补入字段等历史处理模式。
3. 标题、作者、日期等后续改动部分直接在 JSONL 中依据 PDF 核实完成；因此现有两个脚本和中间文件**不能单独、完整地重新生成**这份最终文件。需要重建时，应保存原始输入、逐条证据及每次修订的可复现流程，再与交付文件逐字节或逐字段比较。
4. 最终交付副本与源文件清单位于 `data/paper_jsonl/`。清单的 `pdf_sha256` 由各原始 PDF 字节重新计算，并逐行校验了 PDF 文件名、`paper_id` 和项目相对路径。此步骤没有修改 PDF、XML 或最终 JSONL 的字段内容。

## `paper_id`、来源与路径

对有 PDF 的记录，先计算原始 PDF 字节的 SHA-256，得到十六进制小写字符串 `pdf_sha256_hex`，然后按下式生成：

```text
paper_id = "source-sha256:" + SHA256_UTF8(source_file + "\0" + pdf_sha256_hex)
```

这里 `\0` 是一个 NUL 分隔字节；`source_file` 是原始 PDF 文件名。该 ID 在**文件名和 PDF 内容不变**时稳定，并可借清单追溯来源；即使两个来源文件字节相同，文件名不同仍可得到不同 ID。重命名 PDF 会改变 ID。TEI 转换找不到 PDF 时，脚本改用 XML 内容哈希并记录错误；最终 859 条均已找到原始 PDF，且 ID 全部符合上式。最终集合的 ID、来源文件名和 PDF SHA-256 均各有 859 个唯一值。

最终数据的 `pdf_path` 是相对于**项目根目录**的正斜杠路径，例如 `../oriPDFs.rar/oriPDFs/example.pdf`，不是相对于 `data/paper_jsonl/` 或 PDF 根目录。`deduplicate_jsonl.py` 的来源校验还要求解析后的路径落在指定 `--pdf-root` 下，且文件名等于 `source_file`。最终 JSONL 只保留 `affiliation`、`fulltext`，不写入历史兼容字段 `affiliations`、`full_text`。

## 脚本接口与适用范围

| 文件 | 主要用途 | 输入与输出 |
| --- | --- | --- |
| `tei_to_jsonl.py` | TEI XML 转 JSONL；缺失/坏 XML 标记；可选质量报告 | `--xml-dir`、`--pdf-dir`、`--output`；可选 `--source-map`、`--report` |
| `deduplicate_jsonl.py` | PDF SHA-256 去重与历史修订操作 | 去重用 `--input`、`--pdf-root`、`--output`、`--report`；其他模式见 `python scripts/deduplicate_jsonl.py --help` |

两脚本使用 Python 3.11+。页数补入模式还调用外部 `pdfinfo`。`deduplicate_jsonl.py` 的 `--fill-pages`、`--remove-source` 及若干修订模式会**原位修改指定 JSONL**；`--recover-missing`、`--supplement-confirmed` 使用新的输出路径。两个历史 PDF 修订模式明确要求 864 条前驱记录，不能用于当前 859 条最终文件。即使其他模式能够运行，也不应以最终文件为输入直接重跑，以免覆盖后续人工核实结果。

缺失字段遵守协议：字符串 `""`、列表 `[]`、整数可空值 `null`；`date` 仅存有证据的完整 `YYYY-MM-DD` 发表日期，只有年份时使用 `year` 整数。正文非空不保证完整或无乱码；4 条带 `unreadable_characters_in_fulltext` 的正文暂不建议建立索引，详见数据说明。

## 只读复核

在项目根目录的 PowerShell 中运行以下命令，预期两个 JSONL 的 SHA-256 相同，两个文件均为 859 行，清单为 860 行（含表头）：

```powershell
Get-FileHash scripts/papers_verified.jsonl -Algorithm SHA256
Get-FileHash data/paper_jsonl/papers_final.jsonl -Algorithm SHA256
(Get-Content scripts/papers_verified.jsonl | Measure-Object -Line).Lines
(Get-Content data/paper_jsonl/papers_final.jsonl | Measure-Object -Line).Lines
(Get-Content data/paper_jsonl/paper_source_manifest.csv | Measure-Object -Line).Lines
```

两文件预期 SHA-256 为 `1d37b56454e30ec4f7381164626b3c8c8874a7560f47025ea45eb126d5054f94`。源文件清单可与本地 PDF 重新计算的哈希比较；不要仅凭文件名或扩展名判断 PDF 内容一致。
