#Requires -Version 5.1
<#
  Hack the SDGs 2026 -- mineai-toolkit MCP server setup
  Run as administrator:
  powershell -ExecutionPolicy Bypass -File .\setup_mcp.ps1

  Companion to setup.ps1, which already installs git / uv / opencode / PyCharm.
  This script only does the two things specific to the MCP server:
    1. clone the Mineai-toolkit repo
    2. uv sync  (uv provisions Python 3.14 and installs the dependencies)

  After that a student starts it with the PyCharm Run button on main.py, or
  `uv run mineai-control`; opencode picks it up via the repo's opencode.jsonc.

  ASCII only. PowerShell 5.1 mis-decodes UTF-8 files without a BOM, so any
  non-ASCII literal in this file would come out garbled on a student machine.
#>

$ErrorActionPreference = 'Continue'  # each step handles its own failure; never abort the whole run
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---------- Config ----------
$RepoUrl    = 'https://github.com/Hack-the-SDGs/Mineai-toolkit'
$TempDir    = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Hack-the-SDGs'  # same folder as setup.ps1
$ProjectDir = Join-Path $TempDir 'Mineai-toolkit'                                   # clone lives inside it
$ShareDir   = Join-Path $env:PUBLIC 'Hack-the-SDGs'   # cross-account: readable by the de-elevated user task

# ---------- Helpers ----------
function Write-Step { param([string]$Msg) Write-Host "`n========== $Msg ==========" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Note { param([string]$Msg) Write-Host "[!]  $Msg" -ForegroundColor Yellow }

# Reload PATH from the registry so git / uv installed by setup.ps1 work in this same session
function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable('Path','Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = @($machine, $user) -join ';'
}

# Run a .ps1 as the currently logged-in desktop user, even when this script is elevated.
# Why: uv sync must create .venv and the uv cache under that user's account, otherwise
# PyCharm (running as the student) cannot see the environment.
function Invoke-AsInteractiveUser {
    param([Parameter(Mandatory)][string]$File)
    $user = (Get-CimInstance Win32_ComputerSystem).UserName  # current interactive desktop user
    if (-not $user) { Write-Note 'No interactive user found, running with the current privileges instead'; & $File; return }

    $log  = Join-Path $ShareDir 'mcp-user-init.log'
    $task = 'HackSDGs-McpUserInit'
    $action    = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"& '$File' *> '$log'`""
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Force | Out-Null
    Start-ScheduledTask -TaskName $task

    # naive poll until it finishes; uv sync can take a while on first run (it fetches Python 3.14). 15 min ceiling
    Start-Sleep -Seconds 2
    $waited = 0
    while ((Get-ScheduledTask -TaskName $task).State -eq 'Running' -and $waited -lt 900) {
        Start-Sleep -Seconds 3; $waited += 3
    }
    Unregister-ScheduledTask -TaskName $task -Confirm:$false
    if (Test-Path $log) { Get-Content $log | Write-Host }
}

# ---------- Step 0: working directory ----------
Write-Step "Ensuring working directory: $TempDir"
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
Write-Ok $TempDir

# ---------- Step 1: refresh PATH for this session ----------
Write-Step 'Reloading the PATH environment variable'
Update-SessionPath
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Note 'git not found -- run setup.ps1 first (it installs git / uv).' }
if (-not (Get-Command uv  -ErrorAction SilentlyContinue)) { Write-Note 'uv not found -- run setup.ps1 first (it installs git / uv).' }
Write-Ok 'PATH updated'

# ---------- Step 2: user-privilege init script (clone + uv sync) ----------
Write-Step 'Preparing the user-privilege init script'
New-Item -ItemType Directory -Path $ShareDir -Force | Out-Null
$userInit = Join-Path $ShareDir 'mcp-user-init.ps1'
# Header carries the settings in; body is a single-quoted here-string (no interpolation)
$userInitContent = @"
`$ProjectDir = '$ProjectDir'
`$RepoUrl    = '$RepoUrl'
"@ + @'

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host '[!] git is not ready yet (PowerShell may need a restart), skipping clone'
} else {
    if (Test-Path (Join-Path $ProjectDir '.git')) {
        Write-Host "$ProjectDir already exists, running git pull instead"
        git -C $ProjectDir pull
    } elseif (Test-Path $ProjectDir) {
        Write-Host "[!] $ProjectDir exists but is not a git repository, skipping clone"
    } else {
        git clone $RepoUrl $ProjectDir
    }

    if ((Test-Path $ProjectDir) -and (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host 'Running uv sync (fetches Python 3.14 on first run, this takes a few minutes)...'
        Push-Location $ProjectDir
        uv sync
        if ($LASTEXITCODE -eq 0) { Write-Host '[OK] uv sync finished' }
        else { Write-Host "[!] uv sync exited with code $LASTEXITCODE (re-run to retry)" }
        Pop-Location
    } else {
        Write-Host '[!] uv is not ready or the project is missing, skipping uv sync'
    }
}
'@
[System.IO.File]::WriteAllText($userInit, $userInitContent, (New-Object System.Text.UTF8Encoding($false)))

# ---------- Step 3: run the init script as the desktop user ----------
Write-Step 'Running clone / uv sync as the desktop user'
Invoke-AsInteractiveUser -File $userInit
Write-Ok 'User-privilege init finished'

# ---------- Done ----------
Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '  mineai-toolkit MCP setup complete' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host "  Project : $ProjectDir" -ForegroundColor Cyan
Write-Host "  Start   : double-click start_mcp.cmd in the project folder" -ForegroundColor Cyan
Write-Host "            (or open main.py in PyCharm and Run, or 'uv run mineai-control')" -ForegroundColor Cyan
Write-Host '  Serves  : http://127.0.0.1:8765  (web UI + /mcp endpoint)' -ForegroundColor Cyan

Write-Host "`nAll steps complete." -ForegroundColor Green
