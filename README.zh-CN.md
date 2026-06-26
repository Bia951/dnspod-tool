# DNSPod Tool

用于管理 DNSPod 域名和解析记录的 CLI 与终端交互工具。

## 安装方式

Python 包名可以叫 `dnspod-tool`，安装后的命令名可以叫 `dnspod`。这两者不需要一样。
标准做法是在 `pyproject.toml` 里配置 `[project.scripts]`：

```toml
[project.scripts]
dnspod = "dnspod_tool.main:main"
```

这样别人安装包以后，终端里直接运行：

```bash
dnspod --help
```

推荐给普通用户的安装方式：

```bash
pipx install git+https://github.com/<your-name>/dnspod-tool.git
dnspod --help
```

发布到 PyPI 之后：

```bash
pipx install dnspod-tool
dnspod --help
```

如果用户习惯 `uv`：

```bash
uv tool install git+https://github.com/<your-name>/dnspod-tool.git
dnspod --help
```

Linux 服务器上没有 `pipx` 或 `uv` 时，可以用虚拟环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install git+https://github.com/<your-name>/dnspod-tool.git
dnspod --help
```

不推荐让普通用户运行：

```bash
python3 "dnspod apitool.py"
```

这个长文件名入口只适合作为开发期或兼容旧习惯的 launcher。

## 开发安装

```bash
python -m pip install -e .
dnspod --help
```

## 凭据来源

凭据读取优先级：

1. 当前命令传入的参数
2. 环境变量
3. 系统 keyring
4. 本地凭据文件

Linux 服务器或 CI 环境推荐使用环境变量：

```bash
export DNSPOD_TOKEN_ID="12345"
export DNSPOD_TOKEN="your-token"
```

或者使用腾讯云密钥：

```bash
export TENCENTCLOUD_SECRET_ID="your-secret-id"
export TENCENTCLOUD_SECRET_KEY="your-secret-key"
```

也可以保存凭据：

```bash
dnspod auth token --id 12345 --token your-token --storage auto
dnspod auth key --secret-id your-secret-id --secret-key your-secret-key --storage auto
```

在无桌面的 Linux 服务器上，如果 keyring 不可用，可以使用文件存储：

```bash
dnspod auth token --id 12345 --token your-token --storage file
```

## 两种认证方式

DNSPod Token：

```bash
dnspod records list example.com --token-id 12345 --token your-token
```

Tencent Cloud SecretId/SecretKey：

```bash
dnspod records list example.com --secret-id your-secret-id --secret-key your-secret-key
```

交互终端里，如果执行命令时传入了凭据，工具会询问是否保存到本地。脚本或 CI 环境中不会自动弹出询问；需要保存时显式加上 `--save-credentials`。

```bash
dnspod records list example.com \
  --secret-id your-secret-id \
  --secret-key your-secret-key \
  --save-credentials \
  --auth-storage file
```

不想询问或保存时：

```bash
dnspod records list example.com \
  --token-id 12345 \
  --token your-token \
  --no-save-credentials
```

## 常用命令

先设置默认域名：

```bash
dnspod use example.com
```

之后就可以少敲很多字：

```bash
dnspod ls
dnspod add www A 203.0.113.10
dnspod set www A 203.0.113.11
dnspod del www
```

临时指定域名也可以：

```bash
dnspod ls example.com
dnspod add example.com api CNAME target.example.com
dnspod set example.com www A 203.0.113.11
dnspod del example.com www A --yes
```

`set` 是 upsert：如果同一个 `name + type` 的记录存在，就更新；不存在就创建。如果匹配到多条记录，工具会列出它们并要求你用完整命令按记录 ID 修改。

多账号或多环境可以用 profile 隔离凭据和默认域名：

```bash
dnspod --profile work auth key --secret-id your-secret-id --secret-key your-secret-key
dnspod --profile work use example.com
dnspod --profile work ls
```

`--profile` / `-p` 可以放在命令任意位置：

```bash
dnspod ls -p work
dnspod -p work ls
```

## 完整命令

查看凭据状态：

```bash
dnspod auth status
```

列出域名：

```bash
dnspod domains list
```

列出解析记录：

```bash
dnspod records list example.com
```

创建解析记录：

```bash
dnspod records create example.com --name www --type A --value 203.0.113.10
```

修改解析记录：

```bash
dnspod records update example.com 123456 --value 203.0.113.11
```

删除解析记录：

```bash
dnspod records delete example.com 123456 --yes
```

输出 JSON：

```bash
dnspod records list example.com --json
```

## 终端交互界面

无参数运行会进入交互模式：

```bash
dnspod
```

也可以显式打开：

```bash
dnspod tui
```

## 不完整命令提示

如果只输入了不完整命令，例如：

```bash
dnspod records
```

工具会打印该命令下的完整帮助、可用子命令和示例，而不是只输出一行简短的 `usage`。
