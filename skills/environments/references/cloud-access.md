# AWS 与阿里云访问

使用 [cloud_cli.py](../scripts/cloud_cli.py) 从本 skill 的 SOPS 文件读取云凭据，并调用对应 CLI。脚本按自身位置定位密文，仓库与安装副本使用同一套命令。

## 账号与区域

阿里云有两个不同的所属账号，调用时必须在 `aliyun` 之前传入 `--account prod` 或 `--account humble-little-c1`，不设默认账号。这里的账号标识用于选择密文记录，不是本机 CLI profile。

| 云服务 / 账号标识 | 凭据来源与身份 | Secrets 分支 | 区域 |
| --- | --- | --- | --- |
| AWS | Charles 的 `~/.aws/credentials`，`[kops]` | `aws` | `region` 为 `null`；调用时显式指定 |
| 阿里云 `prod` | Charles 的 `~/.aliyun/config.json`，`prod` profile；原账号（ID 尾号 `2946`）下的 RAM 用户 `stock-ops-cli` | `aliyun.accounts.prod` | 保留 `cn-shanghai`；可按任务覆盖 |
| 阿里云 `humble-little-c1` | Charles 的 `~/Downloads/AccessKey.csv`；**Humble Little C1 主账号**（ID 尾号 `7601`），身份为 `Account` | `aliyun.accounts.humble-little-c1` | CSV 未提供区域，`region` 为 `null`；调用时显式指定 |

AWS 与原 `prod` 凭据于 **2026-09-14** 导入；Humble Little C1 于 **2026-09-15** 导入，名称由用户提供。三组均为长期 Access Key，不含 STS 临时令牌。`prod` 沿用原 profile 名称。

AWS 使用 `access_key_id`、`secret_access_key`；每组阿里云记录使用 `access_key_id`、`access_key_secret`、`mode: AK`，并保存实测的完整 `account_id` 和 `identity_type`。`source_profile` 或 `source_file` 记录导入来源，脚本只读密文，不依赖原 profile 或 CSV。凭据导入不会同步后续来源变更，轮换后需更新密文并重新验证。

这里的阿里云账号访问使用 OpenAPI；SSH 登录按机器资料操作：[Acorn](acorn.md) 使用 `ssh azar`，[Ant](ant.md) 使用 `ssh c1@106.15.156.143`。Ant 属于 `humble-little-c1` 账号、位于 `cn-shanghai`，产品为轻量应用服务器（Simple Application Server / `swas-open`），应使用该产品的 API 查询，而不是 ECS 实例列表。

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

# 阿里云原账号：使用密文记录的 cn-shanghai，密钥属于 RAM 用户
python3 scripts/cloud_cli.py --account prod aliyun sts GetCallerIdentity

# Humble Little C1 主账号：cn-shanghai 仅作为本次身份查询的区域
python3 scripts/cloud_cli.py --account humble-little-c1 --region cn-shanghai aliyun sts GetCallerIdentity

# 其他已获授权的 API 查询：账号与区域参数都放在云服务名之前
python3 scripts/cloud_cli.py --account prod --region cn-shanghai aliyun ecs DescribeInstances
```

工具已在 PATH 时直接运行以上 Python 命令。从其他目录调用时，用当前 skill 的实际路径替换 `scripts/cloud_cli.py`；不依赖原始仓库路径。

AWS 身份查询应返回 `Account`、`Arn`、`UserId`；阿里云应返回 `AccountId`、`Arn`、`IdentityType` 等身份字段。阿里云查询结果应与所选密文记录的 `account_id`、`identity_type` 一致：`prod` 是 `RAMUser`，Humble Little C1 是 `Account`（主账号）。先核对账号与身份，再操作目标区域内的资源；新账号的查询示例区域不代表资源所在区域。身份查询成功只证明当前凭据有效，不证明有其他 API 的权限。

两个阿里云账号已于 **2026-09-15** 在 Charles 通过本脚本分别实测成功，确认所属账号不同，使用阿里云 CLI `3.3.15` 和 SOPS `3.13.3`。AWS 身份查询上次实测于 **2026-09-14**，使用 AWS CLI `2.34.24`。凭据权限与有效性会变化，后续任务仍需按需核验。

## 凭据传递与边界

脚本从 SOPS 解密结果中只提取所选云服务的凭据；阿里云按 `--account` 提取指定账号分支，将其 Access Key 注入单次 CLI 子进程环境。AWS 使用空配置文件路径；阿里云设置 `ALIBABA_CLOUD_IGNORE_PROFILE=TRUE`，避免本机 profile 优先于环境变量。已有云环境变量会从该子进程中清除，包括旧的 session token 和自定义 endpoint；代理等通用网络设置继续继承。

脚本不会写入 `~/.aws`、`~/.aliyun` 或明文临时文件。解密或必填字段校验失败时不启动云 CLI；目前只支持已录入的长期 Access Key。`--profile`、凭据参数和 `--debug` 不用于此入口，不要开启 shell tracing 或打印进程环境。

输出会遮蔽已载入的两项密钥，但 API 结果仍可能包含业务数据；返回新凭据的操作（例如 STS AssumeRole）应另行让结果在内存中进入消费程序，不能直接展示。此脚本提供凭据调用能力，具体资源变更按当前用户任务执行。

官方说明：[AWS 环境变量](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html)、[阿里云环境变量](https://help.aliyun.com/zh/cli/environment-variables)、[阿里云凭据与身份验证](https://help.aliyun.com/zh/cli/configure-credentials)、[GetCallerIdentity 身份字段](https://help.aliyun.com/zh/ram/developer-reference/api-sts-2015-04-01-getcalleridentity)。
