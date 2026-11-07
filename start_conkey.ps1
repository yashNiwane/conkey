# ConKey Windows PowerShell Launcher
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
python host\run_host.py $args
