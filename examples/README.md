# Examples

Everything here is fictional.

## sample-life-kb

A small life library as it looks after a few intakes: settings, spec, status card, file index, change log, open items, glossary, two topic files, two entity pages and a quick note. sample-materials/ holds a new document to file into it.

To try it in Claude Code:

1. Create an empty private repository and put the skills into it ([docs/setup.md](../docs/setup.md), step 1).
2. Copy the contents of sample-life-kb/ (not the folder itself) into the repository root, keeping the Entities and Quick-Notes subfolders.
3. Add the registry to the repository's CLAUDE.md by hand, with your repository as the root (init sets up new libraries only, so a ready-made library is registered this way):

   ````text
   I keep knowledge bases: Life (me and my family: IDs, health, insurance, money, home). For questions about these, use kb-query before searching code or answering from memory; to save something, use kb-note.

   Knowledge base registry (kb-libraries.json):

   ```json
   {"schema": 1, "preferences": {"language": "en"},
    "libraries": [{"id": "life", "label": "Life", "scope": "me and my family: IDs, health, insurance, money, home",
                   "backend": {"type": "github", "root": "<you>/<sample-repo>"}}]}
   ```
   ````

4. Commit, push, and start a new session on the repository. Try, in order:
   1. "What is my cholesterol trend?" (kb-query reads the status card and the 2025 checkup)
   2. "Note this: the boiler service is due in March." (kb-note writes to Quick-Notes/ and commits)
   3. "File this" with the text of sample-materials/checkup_2026.txt (kb-ingest: new material in partition 02, a value change for consolidation)
   4. "Consolidate" (the status card update, proposed as a numbered list)
   5. "What did the status card say before?" (an earlier version from git history, with its commit)
   6. "File my quick notes"
   7. "Health check"

The repository checks validate sample-life-kb/_kb.json.

---

# 示例（中文说明）

这里的内容全部是虚构的。

sample-life-kb 是入库几次之后的小型生活库：配置、规范、状态卡、文件索引、变更轨迹、到期与待办、术语表、两份议题文件、两个实体页和一条随手记。sample-materials/ 里有一份可以入库的新文档。

在 Claude Code 里试用：新建一个私有空仓并放入 skill（见 [docs/setup.zh-CN.md](../docs/setup.zh-CN.md) 第 1 步）；把 sample-life-kb/ 里的内容（不是文件夹本身）复制到仓库根目录，保留 Entities 和 Quick-Notes 子文件夹；按上面英文部分第 3 步的样子在仓库的 CLAUDE.md 里手工写入注册表，root 填你的仓库（初始化只新建库，现成的库这样登记）；提交、推送，在该仓库上开新会话。然后依次试：问「我的胆固醇趋势如何？」；「记一下：锅炉三月该保养了」；贴上 sample-materials/checkup_2026.txt 的内容说「入库」；「整合」；「状态卡以前怎么写的？」；「整理随手记」；「体检」。
