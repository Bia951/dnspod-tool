# DNSPod Tool

CLI and terminal UI for managing DNSPod domains and records.

Chinese documentation: [README.zh-CN.md](README.zh-CN.md).

## Installation

The Python package is named `dnspod-tool`, but the installed command is `dnspod`.
That command is created by the `[project.scripts]` entry in `pyproject.toml`.

Recommended for normal users:

```bash
pipx install git+https://github.com/<your-name>/dnspod-tool.git
dnspod --help
```

After publishing to PyPI:

```bash
pipx install dnspod-tool
dnspod --help
```

If `pipx` is not available, use `uv`:

```bash
uv tool install git+https://github.com/<your-name>/dnspod-tool.git
dnspod --help
```

On a Linux server without `pipx` or `uv`, use a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install git+https://github.com/<your-name>/dnspod-tool.git
dnspod --help
```

## Development install

```bash
python -m pip install -e .
dnspod --help
```

## Credentials

Credential lookup order:

1. Command-line credentials for the current command
2. Environment variables
3. System keyring
4. Local credentials file

For headless Linux servers, environment variables are usually the cleanest option:

```bash
export DNSPOD_TOKEN_ID="12345"
export DNSPOD_TOKEN="your-token"
```

or Tencent Cloud keys:

```bash
export TENCENTCLOUD_SECRET_ID="your-secret-id"
export TENCENTCLOUD_SECRET_KEY="your-secret-key"
```

You can also save credentials:

```bash
dnspod auth token --id 12345 --token your-token --storage auto
dnspod auth key --secret-id your-secret-id --secret-key your-secret-key --storage auto
```

Use `--storage file` on headless Linux if system keyring is unavailable.

Both authentication modes are supported:

- DNSPod token: `--token-id` and `--token`
- Tencent Cloud key: `--secret-id` and `--secret-key`

## Handy workflow

Set a default domain once:

```bash
dnspod use example.com
```

Then use short commands:

```bash
dnspod ls
dnspod add www A 203.0.113.10
dnspod set www A 203.0.113.11
dnspod del www
```

You can still pass a domain when needed:

```bash
dnspod ls example.com
dnspod add example.com api CNAME target.example.com
dnspod set example.com www A 203.0.113.11
dnspod del example.com www A --yes
```

`set` is an upsert command: it updates the matching `name + type` record if one exists, or creates it if none exists. If multiple records match, it prints the matches and asks you to use the record ID through the full command.

Profiles keep credentials and the default domain separate:

```bash
dnspod --profile work auth key --secret-id your-secret-id --secret-key your-secret-key
dnspod --profile work use example.com
dnspod --profile work ls
```

The `--profile` / `-p` option can be placed anywhere:

```bash
dnspod ls -p work
dnspod -p work ls
```

## Full CLI examples

```bash
dnspod domains list
dnspod records list example.com
dnspod records create example.com --name www --type A --value 203.0.113.10
dnspod records update example.com 123456 --value 203.0.113.11
dnspod records delete example.com 123456 --yes
```

You can also pass credentials directly when running a command:

```bash
dnspod records list example.com --token-id 12345 --token your-token
dnspod records list example.com --secret-id your-secret-id --secret-key your-secret-key
```

When command-line credentials are provided in an interactive terminal, the tool asks whether to save them locally. For scripts and CI, it does not prompt unless you pass `--save-credentials`.

```bash
dnspod records list example.com \
  --secret-id your-secret-id \
  --secret-key your-secret-key \
  --save-credentials \
  --auth-storage file
```

JSON output:

```bash
dnspod records list example.com --json
```

## Terminal UI

Run without arguments or use:

```bash
dnspod tui
```
