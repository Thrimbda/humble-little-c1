# humble-little-c1

我的个人 agent skills 仓库。

```text
skills/
  frontend/
    SKILL.md                 # 前端工程默认值与产品气质
    references/              # 架构、视觉基础与组件规范
    assets/                  # 配色情绪板
  environments/
    SKILL.md                 # 个人机器环境指南
    references/              # 机器资料与 SOPS 加密凭据
  domains/
    SKILL.md                 # 域名分工与 Cloudflare DNS 配置
    references/              # 域名资料、操作说明与 SOPS 加密 token
    scripts/                 # 通过加密凭据调用 Cloudflare API
scripts/
  install-skills.sh           # 安装本仓库的全部 skills
```

## 编写 skill

现有的 [environments skill](skills/environments/SKILL.md) 提供个人机器的定位、配置和连接方式。机器资料与加密凭据的用法放在对应的 `references/` 中。

新增 skill 时，在 `skills/<skill-name>/SKILL.md` 中填写 frontmatter 的 `name`、`description` 和正文；安装脚本会自动发现全部 skills。

[前端设计与实现 skill](skills/frontend/SKILL.md) 包含任务组织、视觉基础、组件与数据表达规范；主文件和参考文档均随 skill 目录安装。

## 安装

需要 Node.js **22.20.0 或更新版本**及 npm 提供的 `npx`。首次运行需要联网下载官方 [skills.sh CLI](https://github.com/vercel-labs/skills)。

```bash
# 交互安装：选择软链接或复制方式，确认后安装到全部目标 agents
./scripts/install-skills.sh

# 静默安装：自动确认，成功时没有输出；失败时输出错误并返回非零状态
./scripts/install-skills.sh --quiet

# --yes / -y / --silent / -q 都是静默模式的别名
./scripts/install-skills.sh --yes
```

从其他工作目录调用脚本也可以；安装源始终是脚本所在的仓库。

两种模式都安装到官方 CLI 支持全局安装的全部 **75 个 agent** 的用户级目录，包括未安装的 agent。交互模式选择安装方式并确认，静默模式自动使用默认软链接方式。

软链接模式会把 skill 复制到 `~/.agents/skills/`，供 Codex、Cursor 等使用共享目录的 agent 读取，再为需要独立目录的 agent 建立软链接，例如 Claude Code 的 `~/.claude/skills/`、Pi 的 `~/.pi/agent/skills/` 和 Windsurf 的 `~/.codeium/windsurf/skills/`。具体路径由官方 CLI 处理；软链接不可用时按其规则回退为复制。

脚本固定使用 `skills@1.5.23`。该版本的 `--all --global` 或自动检测会包含不支持全局安装的 agent，因此两种模式都显式传入支持全局安装的全部 agent 标识，排除仅支持项目安装的 Eve 和 PromptScript；升级 CLI 时应同步核对脚本中的名单。

修改仓库中的 skill 后，重新运行安装命令即可更新安装副本；同名的已安装 skill 会被覆盖。仓库文件与安装副本之间不会自动同步。
