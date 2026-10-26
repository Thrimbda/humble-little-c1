# 验证记录

2026-10-26，本机 NixOS，实际 pi 为 `@earendil-works/pi-coding-agent` 1.3.0。

## Runner

在仓库根目录执行：

```bash
python3 -m unittest discover -s skills/pi-supervision/scripts -p 'test_*.py' -v
```

11 项测试通过，覆盖：完整文字和 Unicode JSONL、多个 assistant 消息、工具失败记录、中间错误恢复、零退出的假成功、截断/缺少终态、固定 session、轮次防覆盖、并发 session 锁、STOP/SIGINT/超时、所属子进程清理且无关进程存活、遗留 stdout 管道、启动失败留档，以及拒绝无效时间预算和相对 session 路径。

通过本机真实 `deepseek/deepseek-flash` 做两轮无工具 smoke：第一轮记住口令，第二轮不给出口令、要求回忆。第二轮准确返回；两轮实际消息模型、session ID、最终 `stop`、未 aborted 的 `agent_settled` 及退出状态均核对通过。完整记录保存于监督任务的本机私有目录，不提交原始会话日志。

## Skill

`evals.json` 的三个离线情景各运行一次 with-skill 和 without-skill，共六份回答。按 12 条行为断言人工核对证据：with-skill 12/12，without-skill 11/12。差异在于 baseline 只安排轮次结束后回传，没有安排运行中及时向用户更新。

这些题目已提供较充分的现场证据，多数断言两组均通过。结果说明流程在这组情景中可理解，不能据此推断普遍性能提升。未测量 token 和耗时；离线回答不能替代 runner 实测。详细回答、评分和静态 review 页面保留在本地 `pi-supervision-workspace/iteration-1/`，由 Git 忽略。

skill-creator 的 frontmatter 校验通过；校验器依赖 PyYAML，本机用临时 Nix shell 提供，不给 runner 增加运行依赖。已检查相对文档链接、Python 语法及 Git whitespace。

## 边界

真实执行只验证了上述 pi 版本和 NixOS 宿主。macOS 使用场景仅做流程评估，未在 macOS 上运行脚本；原生 Windows 不受 runner 支持。进程组不能限制内存或保证终止脱离该组的进程；需要硬限制时必须另选并验证宿主的作业隔离机制。
