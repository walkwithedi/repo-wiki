# 设置

怎样在一个 GitHub 仓库里建知识库、每一步写了什么，以及怎样更新 skill、试用示例。[English](setup.md)

## 你需要

开始前逐项核对；缺了哪一项，往往到后面才表现为 skill 没反应或凭记忆作答。

- [ ] Claude Code：终端、桌面应用，或网页与 Claude 手机应用里的 claude.ai/code。
- [ ] 会话运行处有 git 和 Python 3.9 及以上。claude.ai/code 的云端会话两者都有；脚本只用 Python 标准库。
- [ ] 一个 GitHub 账号；用云端会话时，claude.ai 已连接 GitHub 并能访问知识库仓库。
- [ ] 每个库一个空的**私有**仓库。里面已有 README 或许可证文件没关系。

仓库必须保持私有。里面会放你的文档、随手记和状态卡；能读这个仓库的人就能读这个库。

## 1. 把 skill 放进仓库

从 [Releases](../../../releases) 页面下载三个 zip：`kb-note-<版本>.zip`、`kb-query-<版本>.zip`、`kb-ingest-<版本>.zip`。想用中文口令就改下 `-zh` 版；同一个 skill 不要两种语言都装，否则会抢同样的请求。

把每个 zip 解压到知识库仓库检出目录的 `.claude/skills/` 下，解压后应是：

```text
.claude/skills/kb-ingest/SKILL.md
.claude/skills/kb-note/SKILL.md
.claude/skills/kb-query/SKILL.md
```

提交并推送。Claude Code 从仓库的 `.claude/skills/` 加载 skill，所以在这个仓库上开的每个会话，本地或云端，都带着它们。

```bash
git clone https://github.com/<你>/<知识库仓库>.git && cd <知识库仓库>
mkdir -p .claude/skills
unzip ~/Downloads/kb-note-<版本>-zh.zip -d .claude/skills
unzip ~/Downloads/kb-query-<版本>-zh.zip -d .claude/skills
unzip ~/Downloads/kb-ingest-<版本>-zh.zip -d .claude/skills
git add .claude/skills && git commit -m "加入知识库 skill" && git push
```

## 2. 建库

在这个仓库上开一个 Claude Code 会话（在检出目录里运行 `claude`，或在 claude.ai/code 上为这个仓库开会话），说「开始使用知识库」。kb-ingest 会：

1. 从检出目录的 origin 远程认出仓库，不用你指定文件夹。
2. 逐个问两个问题：预设（生活或工作），以及一句话说明哪些内容归这个库（范围）。
3. 自行确定其余各项：名称与 id、语言、时区、敏感分级（生活库开启）、上传材料先转 Markdown（开启）。
4. 给出将要写入的全部内容的预览，并提醒仓库必须是私有的。回复「确认」之前什么都不写；任何一项都可以先改。
5. 在仓库根目录写入：`_kb.json`、`_kb-params.md`、规范（`00_Spec.md`）和空的汇总文件。此时不建文件夹：git 不保留空文件夹，Quick-Notes、Entities 由 skill 第一次往里写时创建。
6. 把注册表连同告诉 Claude 这个库存在的那一行写进仓库的 `CLAUDE.md`，CLAUDE.md 的其他行保持不变。
7. 全部作为一个提交（「Init: <名称>」）推送。推送成功才算设置完成。

检查设置：在这个仓库上开一个新会话（Claude Code 在会话开始时读 CLAUDE.md），问「我有哪些知识库？」。Claude 应说出库名和范围；说不出时见[排障](troubleshooting.zh-CN.md)。

## 3. 试一试

1. 给 Claude 一份文档并说「入库」：本地会话里指明磁盘上的文件或文件夹；任何会话里都可以贴文字，或在 Claude Code 应用允许时附上文件。入库会给它分区、命名、查重、判定版本，预览后写入、提交并推送，用一行报告结果和提交号。写入后立刻可查。
2. 问一个这份文档能回答的问题。kb-query 先读状态卡，再读文件，回答里注明是哪个文件。
3. 说「整合」。kb-ingest 给文件补关键结论，并把状态卡改动编号列出，由你逐条决定。

其他请求：「记一下：……」（kb-note）、「整理随手记」、「体检」。全部口令及之后会发生什么：[daily-use.zh-CN.md](daily-use.zh-CN.md)。

## 更多的库

一个仓库放一个库。要第二个库（比如在生活库之外再建工作库），就另建一个私有仓库，放入 skill，在那里做第 2 步。每个库在自己仓库的会话里使用；CLAUDE.md 已登记别的库时，初始化会拒绝。

## 更新 skill

下载新版 zip，把 `.claude/skills/` 下的三个文件夹换成新解压的（先删旧文件夹，免得新版去掉的文件残留），提交并推送。除非变更记录另有说明，库文件不用改。

```bash
rm -rf .claude/skills/kb-note .claude/skills/kb-query .claude/skills/kb-ingest
unzip ~/Downloads/kb-note-<版本>-zh.zip -d .claude/skills    # 另外两个同样
git add -A .claude/skills && git commit -m "知识库 skill 升级到 <版本>" && git push
```

## 注册表

初始化把注册表作为下面这样一块写进 `CLAUDE.md`（中文库）：

````text
我有知识库：生活（我和家人：证件、健康、保险、财务、住房）。相关问题先用 kb-query 查知识库，再查代码或凭记忆回答；要记录用 kb-note。新对话开始时，如知识库有未完成的分批入库，先提醒是否继续。

知识库注册表（kb-libraries.json）：

```json
{
  "schema": 1,
  "preferences": {"language": "zh"},
  "libraries": [
    {"id": "life", "label": "生活", "scope": "我和家人：证件、健康、保险、财务、住房",
     "backend": {"type": "github", "root": "<你>/<知识库仓库>"}}
  ]
}
```
````

- `scope` 决定哪些内容归这个库，写成清楚的一句话。
- `backend.root` 是「<owner>/<repo>」形式的仓库名；skill 只在 origin 指向这个仓库的检出目录里工作。
- 可以加上 `preferences.output`：`markdown`，或 `plain`（回复不用 Markdown 标记）。
- 可以加上 `preferences.citations`：`always`（默认，每条事实注明依据文件），或 `on_request`（回答只陈述事实，追问出处时再列出依据文件）。
- 要改范围或名称，手工改这一块再提交，或者说「初始化」，让初始化模式先把改动列给你看。

## 库的配置

`_kb.json` 和 `_kb-params.md` 在仓库根目录，skill 每次都读。`_kb.json` 的各个键（语言、时区、文件名、敏感分级、分区、转换、入库方式）见 [skills/kb-ingest/references/config.md](../skills/kb-ingest/references/config.md)（英文）。

## 提交

skill 只提交每一轮写入的文件，提交说明首行写模式和数量（如「Intake: 3 files」「Quick note: <文件名>」），推送到默认分支；从不建分支、开 PR 或强推。作者身份和提交说明规则取自 git 配置和仓库自己的 CLAUDE.md，想让提交说明用中文或用某个身份，就在 CLAUDE.md 里加一行写明。

## Codex

在私有知识库仓库的检出目录中使用 Codex，执行环境需有 Python 3.9+ 和 Git。适用于具备文件与命令执行能力的 Codex 会话，包括 ChatGPT 中的 Codex；没有仓库执行环境的普通聊天无法运行这些流程。

把相同的三个发行版 zip 解压到 `.agents/skills/`，而非 `.claude/skills/`。两个助手都使用时，在两个目录安装同一版本，每次更新同时替换两套目录，解压前删除各自的旧 skill 文件夹。SKILL.md、脚本和 references 必须完整保留，脚本使用本次加载入口下的副本。发行版 skill 不含 Claude 专属的 `allowed-tools` 声明。

在知识库的 AGENTS.md 中加入以下入口，保留已有指令：

```markdown
先读取 CLAUDE.md，遵守其中的知识库注册表、输出偏好和项目规则。注册表只保留在 CLAUDE.md。
查询与涉及本库事实的写作，读取 .agents/skills/kb-query/SKILL.md。
记录随手记，读取 .agents/skills/kb-note/SKILL.md。
入库、整合、体检与初始化，读取 .agents/skills/kb-ingest/SKILL.md。
继续读取 skill 要求的 references，遵守预览和确认节点。无法自动发现 skill 时，按以上路径显式加载。
```

提交并推送安装目录和入口。新库对 Codex 说「开始使用知识库」，按上文第 2 步初始化，注册表仍写在 CLAUDE.md，AGENTS.md 指向它。已有库只补入口，不重新初始化、不替换知识文件。新开会话问「我有哪些知识库？」验证。

定位到已有库后，每个对话运行一次：

```bash
python3 .agents/skills/kb-query/scripts/kbdoctor.py .
```

这是只读的本地诊断。PDF 转换需要 Poppler（`pdftotext`、`pdfimages`、`pdfinfo`），缺少 PDF 工具不影响查询和随手记。依赖与 Git 凭据通过执行环境配置；诊断不验证网络、认证、推送权限、skill 自动发现或读图能力。Claude 的设置和 hooks 不会自动在 Codex 生效，不得伪造审批标记；skill 的校验与确认节点仍须执行，没有提问工具时在对话中列出选项并等待答复。脚本报告 `pushed:` 后才算写入交付。同一库的入库、整合、随手记整理须顺序执行。定时整合需要单独配置调度并明确授权，安装 skill 不会创建定时任务。
