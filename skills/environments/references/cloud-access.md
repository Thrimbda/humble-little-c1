# AWS 与阿里云访问

使用 [cloud_cli.py](../scripts/cloud_cli.py) 从本 skill 的 SOPS 文件读取云凭据，并调用对应 CLI。脚本按自身位置定位密文，仓库与安装副本使用同一套命令。

## 凭据与区域

以下凭据于 **2026-09-14** 从 Charles 的既有配置导入，均为长期 Access Key，不含 STS 临时令牌。

| 云服务 | 本机来源 | Secrets 字段 | 区域 |
| --- | --- | --- | --- |
| AWS | `~/.aws/credentials` 的 `[kops]` | `aws.access_key_id`、`aws.secret_access_key` | 本机没有 `~/.aws/config`，`aws.region` 为 `null`；调用时显式指定 |
| 阿里云 | `~/.aliyun/config.json` 的 `prod` profile，模式 `AK` | `aliyun.access_key_id`、`aliyun.access_key_secret`、`aliyun.mode` | `aliyun.region` 为 `cn-shanghai`；可按任务覆盖 |

`source_profile` 记录来源，脚本不依赖执行机器存在同名 profile。这里的阿里云账号访问使用 OpenAPI；登录 Acorn 仍用机器资料里的 `ssh azar`。凭据导入不会同步后续本机配置变更，轮换后需更新密文并重新验证。

## 执行命令

执行机器需要 Python 3、SOPS、对应的 `aws` 或 `aliyun` CLI，以及匹配 recipient 的私钥，详见[加密凭据](secrets.md)。先在包含 `SKILL.md` 的目录运行：

```bash
export SOPS_AGE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/id_ed25519"

# 工具不在 PATH 时进入临时 Nix 环境；不修改系统或 CLI 配置
nix shell nixpkgs#python3 nixpkgs#sops nixpkgs#awscli2 nixpkgs#aliyun-cli
```

进入 Nix shell 后，在同一 skill 目录运行：

```bash
# AWS：us-east-1 仅用于此身份查询示例，不代表资源所在区域
python3 scripts/cloud_cli.py --region us-east-1 aws sts get-caller-identity

# 阿里云：使用密文记录的 cn-shanghai
python3 scripts/cloud_cli.py aliyun sts GetCallerIdentity

# 其他已获授权的 API 查询：区域参数放在云服务名之前
python3 scripts/cloud_cli.py --region cn-shanghai aliyun ecs DescribeInstances
```

工具已在 PATH 时直接运行以上 Python 命令。从其他目录调用时，用当前 skill 的实际路径替换 `scripts/cloud_cli.py`；不依赖原始仓库路径。

AWS 身份查询应返回 `Account`、`Arn`、`UserId`；阿里云应返回 `AccountId`、`Arn`、`IdentityType` 等身份字段。先核对账号与身份，再操作目标区域内的资源。身份查询成功只证明当前凭据有效，不证明有其他 API 的权限。

上述两条身份查询已于 **2026-09-14** 在 Charles 通过本脚本实测成功，使用 AWS CLI `2.34.24`、阿里云 CLI `3.3.15` 和 SOPS `3.13.3`。凭据权限与有效性会变化，后续任务仍需按需核验。

## 凭据传递与边界

脚本只提取所选云服务分支，将 Access Key 注入单次 CLI 子进程环境。AWS 使用空配置文件路径；阿里云设置 `ALIBABA_CLOUD_IGNORE_PROFILE=TRUE`，避免本机 profile 优先于环境变量。已有云环境变量会从该子进程中清除，包括旧的 session token 和自定义 endpoint；代理等通用网络设置继续继承。

脚本不会写入 `~/.aws`、`~/.aliyun` 或明文临时文件。解密或必填字段校验失败时不启动云 CLI；目前只支持已录入的长期 Access Key。`--profile`、凭据参数和 `--debug` 不用于此入口，不要开启 shell tracing 或打印进程环境。

输出会遮蔽已载入的两项密钥，但 API 结果仍可能包含业务数据；返回新凭据的操作（例如 STS AssumeRole）应另行让结果在内存中进入消费程序，不能直接展示。此脚本提供凭据调用能力，具体资源变更按当前用户任务执行。

官方说明：[AWS 环境变量](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html)、[阿里云环境变量](https://help.aliyun.com/zh/cli/environment-variables)、[阿里云凭据与身份验证](https://help.aliyun.com/zh/cli/configure-credentials)。
