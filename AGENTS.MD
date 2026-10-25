## Windows 11 Terminal Compatibility

- The development environment is Windows 11 using PowerShell. Always generate commands compatible with PowerShell.
- Never use Unix/Linux-specific commands such as `tail`, `head`, `grep`, `sed`, `awk`, or `cat` when executing commands in PowerShell.
- Use PowerShell equivalents instead: `Select-Object -Last N` for `tail -N`, `Select-Object -First N` for `head -N`, `Select-String` for `grep`, and `Get-Content` for `cat`.
- When chaining commands, use PowerShell-compatible syntax and operators.
- Before executing a command, verify that its syntax and utilities are compatible with the current shell.
- Do not assume Bash, Unix utilities, or WSL are available unless explicitly confirmed.
- If a command requires a Linux environment, explicitly use an available WSL or Docker shell instead of executing it directly in PowerShell.
- When using Docker commands with PowerShell pipelines, avoid interactive flags such as `-it` when they interfere with piped output.
- If a command fails because of shell incompatibility, rewrite it for the current environment instead of retrying the same command.
