# ResearchAgent

ResearchAgent 是一个围绕 [Semantic Scholar Paper Data API](https://api.semanticscholar.org/api-docs/#tag/Paper-Data) 构建的学术论文智能检索与相关性分级 MVP。它支持标题、摘要、关键词、DOI、arXiv ID、研究方向描述和 PDF 上传，并输出带有多维解释的论文结果列表。

## 已实现能力

- 多输入查询：标题、摘要、关键词、DOI、arXiv ID、自然语言研究需求、PDF 上传
- 查询画像：自动抽取主题、任务、方法、领域、数据集和关键词
- 多策略召回：`paper/search` 排名召回 + `paper/search/bulk` 扩展召回
- 多维评分：主题、任务、方法、领域、数据集、关键词六个维度
- 相关性分级：A/B/C/D 四级映射，附带置信度
- 解释生成：`reason_tags`、`reason_text`、相似点/差异点
- 结果增强：聚类标签、概览摘要、引用量展示
- 导出能力：JSON / CSV / Markdown
- Web 界面：查询、筛选、排序、导出

## 项目结构

```text
researchAgent/
  run.py
  requirements.txt
  .env.example
  research_agent/
    app.py
    config.py
    constants.py
    models.py
    adapters/
    services/
    templates/
    static/
  tests/
```

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

## API 说明

### `POST /api/search`

- `multipart/form-data` 或 `application/json`
- 支持字段：`title`、`abstract`、`keywords`、`doi`、`arxiv_id`、`topic_text`、`pdf_file`

返回结构包含：

- `query_type`
- `query_summary`
- `results`
- `clusters`
- `overview_summary`
- `warnings`
- `meta`

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

- Semantic Scholar 官方 Paper Data API 并不直接暴露通用向量检索接口，因此这里将“语义召回”落为“结构化查询画像 + 多查询策略 + 本地重排序”。
- 评分逻辑优先考虑任务、方法和领域，不单独依赖关键词重合。
- 所有核心模块都保持可替换，后续可以继续接 OpenAlex、Crossref 或更复杂的向量服务。
