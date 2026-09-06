# 加密凭据

凭据文件是本目录的 [secrets.enc.yaml](secrets.enc.yaml)，采用 SOPS 加密 YAML。命名沿用 `~/Work/blog/secrets` 的 `*.enc.<格式>` 习惯；[.sops.yaml](.sops.yaml) 使用与 blog 相同的 Ed25519 SSH 公钥作为 age recipient。

## 文件与密钥

- 非空值由 SOPS 加密，字段名仍可见；SOPS 元数据包含解密所需的 recipient 和加密数据密钥。
- Charlie 上对应私钥是 `~/.ssh/id_ed25519`。SOPS 原生支持这个 SSH key，不需要转换或创建另一把 age key。
- 私钥留在 `~/.ssh`，不放进 skill。这个 recipient 只允许持有匹配私钥的环境解密，不能假设五台机器各自的 SSH key 都能解密。
- `axiom`、`acorn`、`charlie` 的 `ssh_user` 已按实测填为 `c1`。每台机器都预留了 `sudo_password: null`；**尚未录入任何真实密码**。`null` 是待填写标记，不是空密码，也不是可用凭据。

SSH 本身继续使用现有 SSH 配置和密钥认证。若任务只需普通用户权限，无需解密密码。

## 后续编辑

下面命令在这个 skill 的根目录（包含 `SKILL.md` 的目录）执行。安装副本中也保留相同的 `references/` 布局。

```bash
# SOPS 不在 PATH 时，用 Nix 提供它；无需修改系统配置
nix shell nixpkgs#sops -c sops --version

# 由用户在本地编辑器中填入密码，保存后由 SOPS 重新加密
SOPS_AGE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/id_ed25519" \
  nix shell nixpkgs#sops -c sops edit references/secrets.enc.yaml

# 只检查加密状态，不显示明文
nix shell nixpkgs#sops -c sops filestatus references/secrets.enc.yaml
```

已安装 `sops` 时可以直接调用，省去 `nix shell nixpkgs#sops -c`。SOPS 默认也会查找 `~/.ssh/id_ed25519`；显式指定 `SOPS_AGE_SSH_PRIVATE_KEY_FILE` 可以固定本次使用的私钥路径。

用户编辑会在本地编辑器中显示明文，agent 执行时不要打开该编辑器、读取完整解密文件或把密码写进 shell 命令参数。应编辑仓库内的文件，再重新运行仓库安装脚本更新副本。

## 通过 stdin 使用单个字段

密码填好后，使用如下 Bash 管道；这里用 Axiom 的只读服务查询演示 sudo。`skill_dir` 应是当前读取到的 skill 所在目录，不依赖原始仓库的固定绝对路径。

```bash
set -o pipefail
skill_dir="$PWD"  # 在包含 SKILL.md 的目录运行

SOPS_AGE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/id_ed25519" \
  nix shell nixpkgs#sops -c sops decrypt \
    --extract '["axiom"]' --output-type json \
    "$skill_dir/references/secrets.enc.yaml" \
  | python3 -c '
import json, sys
try:
    value = json.load(sys.stdin)["sudo_password"]
except Exception:
    sys.exit("无法读取密码字段")
if not isinstance(value, str) or not value or any(c in value for c in "\n\r\0"):
    sys.exit("密码字段尚未填写或不是单行字符串")
sys.stdout.write(value + "\n")
' \
  | ssh -T -o BatchMode=yes -o ConnectTimeout=8 axiom-tunnel \
      'IFS= read -r credential || exit 1; printf "%s\n" "$credential" | sudo -S -p "" -- systemctl status sshd.service --no-pager'
```

这条管道只输出目标命令的结果，密码不会出现在工具返回内容或命令行参数里。空值、解密失败或格式不符时不产生密码行，远端也不会执行 sudo。不要开启 `set -x`，不要插入 `tee`、`cat` 或调试输出；消费命令本身也不能回显输入。

其他机器替换字段名与目标即可：`acorn.sudo_password` 对应 `ssh azar`，`charlie.sudo_password` 在 Charlie 本机消费。Atlas 和 Charles 的凭据与连接方法留待补充。非交互自动化不要使用 `ssh -t`，它可能让终端回显密码。

密文与加密规则会随 skill 一起安装。运行时只在内存和管道里传递选中的字段，不把解密后的 YAML 写回磁盘或提交到 Git。
