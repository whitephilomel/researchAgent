# ResearchAgent

ResearchAgent 是一个围绕 [Semantic Scholar Paper Data API](https://api.semanticscholar.org/api-docs/#tag/Paper-Data) 构建的学术论文智能检索与相关性分级 MVP。它支持标题、摘要、关键词、DOI、arXiv ID、研究方向描述和 PDF 上传，并输出带有多维解释的论文结果列表。

## 已实现能力

- 多输入查询：标题、摘要、关键词、DOI、arXiv ID、自然语言研究需求、PDF 上传
- 查询画像：自动抽取主题、任务、方法、领域、数据集和关键词
- 多策略召回：`paper/search` 排名召回 + `paper/search/bulk` 扩展召回
- 全量检索开关：开启后通过 `paper/search/bulk` 的 token 分页尽量抓取全部相关文献
- 服务端分页：首次检索生成 `search_session_id`，后续翻页直接走本地缓存，不重复扫描 API
- 多维评分：主题、任务、方法、领域、数据集、关键词六个维度
- 相关性分级：A/B/C/D 四级映射，附带置信度
- 解释生成：`reason_tags`、`reason_text`、相似点/差异点
- 结果增强：聚类标签、概览摘要、引用量展示
- 导出能力：JSON / CSV / Markdown
- Web 界面：查询、筛选、排序、导出、翻页

## 运行方式

1. 安装依赖

   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量

   复制 `.env.example`，按需填写 `SEMANTIC_SCHOLAR_API_KEY`。
   不填也能调用公开接口，但更容易受到速率限制。

3. 启动服务

   ```bash
   python run.py
   ```

4. 浏览器打开

   ```text
   http://127.0.0.1:8000
   ```

## 全量检索与分页说明

- 查询表单里的“全量检索开关”默认关闭。
- 关闭时，系统采用受控召回，适合快速查看高相关结果。
- 开启时，系统会通过 Semantic Scholar `paper/search/bulk` 的 token 连续翻页抓取更多结果，再进行统一打分排序。
- 首次全量检索结束后，服务端会生成 `search_session_id` 并缓存结果；点击上一页/下一页时不会重新请求整个学术库。
- 由于当前使用的是公共 API，全量检索在宽主题下可能比较慢，也更容易遇到 429 限流。

## API 说明

### `POST /api/search`

支持 `multipart/form-data` 或 `application/json`。

常用字段：

- `title`
- `abstract`
- `keywords`
- `doi`
- `arxiv_id`
- `topic_text`
- `pdf_file`
- `result_limit`
- `page`
- `exhaustive_search`
- `search_session_id`

返回结构除了原有字段，还会在 `meta` 中包含：

- `search_session_id`
- `page`
- `page_size`
- `total_results`
- `total_pages`
- `has_next_page`
- `has_prev_page`
- `search_mode`
- `bulk_pages_fetched`
- `exhaustive_completed`
- `cache_hit`

### `POST /api/export`

请求体：

```json
{
  "format": "csv",
  "search_response": {}
}
```

## PDF 支持说明

- 当前代码已经实现 PDF 上传、大小/类型校验、DOI/arXiv 抽取和标题回退。
- 如果环境安装了 `pypdf`，会进一步尝试抽取正文前几页内容。
- 如果未安装或解析失败，系统不会中断，而是退回到文件名/标识级检索。

## 测试

```bash
python -m unittest discover -s tests
```

## 设计取舍

- Semantic Scholar 官方 Paper Data API 不直接提供通用向量召回，因此这里将“语义召回”落为“结构化查询画像 + 多查询策略 + 本地重排序”。
- 开启全量检索后，系统优先使用 bulk 分页抓取，避免翻页时反复打外部 API。
- 评分逻辑优先考虑任务、方法和领域，不单独依赖关键词重合。
- 所有核心模块都保持可替换，后续可以继续接 OpenAlex、Crossref 或更复杂的向量服务。
