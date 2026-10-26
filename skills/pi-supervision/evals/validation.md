# 验证记录

2026-10-27，本机 NixOS，实际 pi 为 `@earendil-works/pi-coding-agent` 1.3.0。

## Runner

在仓库根目录执行：

```bash
python3 -m unittest discover -s skills/pi-supervision/scripts -p 'test_*.py' -v
```

25 项测试：11 项单轮备用路径回归，14 项持久 RPC 测试。RPC 覆盖同进程多轮、prompt 文件及 Unicode、流式输入输出、steer/follow_up 留档、clear_queue 确认后 abort、取消后复用进程、快速完成先于 prompt 确认、handled/rejected/error 区分、恢复后成功、排队与 settled 竞争、EOF/信号/超时、异常退出和坏流留档、部分 JSON 尾部保留、长提示管道背压、并发 session 锁、防覆盖和子进程清理。

新增关闭测试曾发现 pi 退出后子进程仍持有 stdout 管道会造成关闭超时。已修复为正常退出后先定向清理所属进程组，再排空管道，且不影响无关进程。

## 真实 pi 验证

以 `deepseek/deepseek-flash`、无工具模式，验证最终 runner 的两种宿主接入方式：

- Codex `exec_command(tty=true)` + `write_stdin`：同一个 pi PID 连续两轮，第一轮记住口令，第二轮准确回忆；正常 shutdown，退出 0。
- 原生 subprocess PIPE：初始任务运行中发 steer，接着排入 follow_up，收到 `STEER_OK` 和 `FOLLOWUP_OK`，整轮完整结束。
- 同一个 PIPE 会话下一轮开始输出长序列后发 abort，核对先 clear_queue 后 abort，状态为 cancelled；再开新轮准确回忆 steer 中给定的标记，PID 不变，最后正常关闭。

总计两个真实会话、五轮，核对实际消息模型、终态、追加输入留档和进程身份。原始输入、完整事件、文字结果、stderr 与元数据保留在本机私有目录，不提交会话日志。进程组清理修复以可重复子进程测试覆盖；真实 smoke 未启动项目工具。

## Skill

初版三个离线情景各做一次 with-skill/without-skill，共六份回答，断言为 12/12 与 11/12。RPC 更新增加 `rpc-evals.json` 两个情景，对照新 skill 与更新前快照，各题各跑一次；新版本 8/8，旧版本 7/8。旧版本能提出适配思路，但示例 prompt JSON 含未转义换行，且尚无可直接运行的持久适配器。

题目已提供较充分的现场信息，多数断言两组均通过；小样本离线回答不支持普遍性能提升结论。未测量 token 和耗时。详细回答、评分和静态 review 页面留在本地 `pi-supervision-workspace/`，由 Git 忽略，并在清理 worktree 前归档。

skill-creator 的 frontmatter 校验、相对文档链接、Python 语法及 Git whitespace 检查通过。校验器依赖 PyYAML，本机用临时 Nix shell 提供，不给 runner 增加依赖。

## 边界

真实执行只覆盖上述 pi 版本和 NixOS。macOS 仅做流程评估，未实机验证；原生 Windows 不受 runner 支持。进程组不能限制内存或保证终止脱离该组的进程。stdout 消费者必须持续读取；如果消费者停止读取，背压会暂停整个链路，需要宿主恢复读取或作业隔离机制处理。
