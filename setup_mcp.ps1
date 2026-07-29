#Requires -Version 5.1
<#
  Hack the SDGs 2026 -- mineai-toolkit MCP server setup
  Run as administrator:
  powershell -ExecutionPolicy Bypass -File .\setup_mcp.ps1

  Companion to setup.ps1. Gets the Minecraft MCP server onto a student machine:
  clone the repo, let uv provision Python 3.14 and the dependencies, wire the
  server into opencode, and drop a launcher on the Desktop.

  ASCII only. PowerShell 5.1 mis-decodes UTF-8 files without a BOM, so any
  non-ASCII literal in this file would come out garbled on a student machine.

  Safe to run after setup.ps1 (git / uv / opencode are then already present) or
  on its own -- every install step skips work that is already done.
#>

$ErrorActionPreference = 'Continue'  # each step handles its own failure; never abort the whole run
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---------- Config ----------
$RepoUrl    = 'https://github.com/Hack-the-SDGs/Mineai-toolkit'
$NoDDrive   = -not (Test-Path 'D:\')
$ProjectDir = if ($NoDDrive) { Join-Path ([Environment]::GetFolderPath('Desktop')) 'Mineai-toolkit' } else { 'D:\Mineai-toolkit' }
$ShareDir   = Join-Path $env:PUBLIC 'Hack-the-SDGs'   # cross-account: readable by the de-elevated user task
$McpUrl     = 'http://127.0.0.1:8765/mcp'             # where mineai-control listens; opencode connects here
$McpName    = 'mine-ai-toolkit-mcp-server'            # key used in opencode config

# ---------- Helpers ----------
function Write-Step { param([string]$Msg) Write-Host "`n========== $Msg ==========" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Note { param([string]$Msg) Write-Host "[!]  $Msg" -ForegroundColor Yellow }

# Always write files without a BOM: Windows / opencode fail to parse .json files that have one
function Set-TextNoBom {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($false)))
}

# Reload PATH from the registry so git / uv installed by winget work in this same session
function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable('Path','Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = @($machine, $user) -join ';'
}

function Install-WithWinget {
    param([string]$Id)
    # Already installed -> skip quietly (winget list -e returns 0 on a hit), so re-runs do not reinstall
    winget list -e --id $Id --accept-source-agreements *> $null
    if ($LASTEXITCODE -eq 0) { Write-Ok "$Id already installed, skipping"; return }

    Write-Step "Installing $Id"
    winget install -e --id $Id --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) { Write-Ok "$Id installed" }
    else { Write-Note "$Id winget exit code $LASTEXITCODE (usually a user cancel, safe to ignore)" }
}

# Run a .ps1 as the currently logged-in desktop user, even when this script is elevated.
# Why: uv must create .venv and the uv cache (including the managed Python 3.14) under that
# user's account, otherwise opencode running as the student cannot see the environment. Same
# reason the opencode config has to land in the student's profile, not the administrator's.
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

# ---------- Preflight ----------
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Note 'winget not found. Install "App Installer" from the Microsoft Store first, then re-run this script.'
    return
}

# ---------- Step 1: install prerequisites (skip whatever setup.ps1 already did) ----------
Install-WithWinget 'Git.Git'
Install-WithWinget 'astral-sh.uv'
Install-WithWinget 'SST.opencode'
Install-WithWinget 'SST.OpenCodeDesktop'

# ---------- Step 2: refresh PATH for this session ----------
Write-Step 'Reloading the PATH environment variable'
Update-SessionPath
Write-Ok 'PATH updated (git / uv should now be callable)'

# ---------- Step 3: user-privilege init script ----------
# clone, uv sync, opencode config and the launcher all run as the desktop user, so that
# .venv, the uv cache and the opencode config are created under the student account, not admin.
Write-Step 'Preparing the user-privilege init script'
New-Item -ItemType Directory -Path $ShareDir -Force | Out-Null
$userInit = Join-Path $ShareDir 'mcp-user-init.ps1'

# Header carries the few settings in; body is a single-quoted here-string (no interpolation)
$userInitContent = @"
`$ProjectDir = '$ProjectDir'
`$RepoUrl    = '$RepoUrl'
`$McpUrl     = '$McpUrl'
`$McpName    = '$McpName'
"@ + @'

function Set-TextNoBom { param([string]$Path,[string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($false))) }

# --- clone or update the toolkit ---
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
}

# --- uv sync: provisions Python 3.14 and installs dependencies into .venv ---
# No .env is written: camp bots use an account shorthand (e.g. create_bot("g_swim")),
# which ignores .env entirely. Students who want a personal account copy .env.example
# to .env themselves.
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

# --- register the MCP server in the user's global opencode config ---
# The repo also ships opencode.jsonc, so opencode picks the server up when opened inside the
# project; this global entry makes it available from any folder as well. Merge, do not clobber.
$cfgDir  = Join-Path $env:USERPROFILE '.config\opencode'
$cfgFile = Join-Path $cfgDir 'opencode.json'
New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null
$cfg = $null
if (Test-Path $cfgFile) {
    try { $cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json } catch { Write-Host '[!] existing opencode.json is unreadable, recreating it'; $cfg = $null }
}
if (-not $cfg) { $cfg = [pscustomobject]@{ '$schema' = 'https://opencode.ai/config.json' } }
if (-not ($cfg.PSObject.Properties.Name -contains 'mcp')) {
    $cfg | Add-Member -NotePropertyName 'mcp' -NotePropertyValue ([pscustomobject]@{}) -Force
}
$server = [pscustomobject]@{ type = 'remote'; url = $McpUrl; enabled = $true }
$cfg.mcp | Add-Member -NotePropertyName $McpName -NotePropertyValue $server -Force
Set-TextNoBom -Path $cfgFile -Content ($cfg | ConvertTo-Json -Depth 10)
Write-Host "[OK] Registered '$McpName' -> $McpUrl in $cfgFile"

# --- Desktop launcher: starts the MCP server (uv run mineai-control) ---
if (Test-Path $ProjectDir) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $lnkPath = Join-Path $desktop 'Start MineAI MCP.lnk'
    try {
        $wsh = New-Object -ComObject WScript.Shell
        $lnk = $wsh.CreateShortcut($lnkPath)
        $lnk.TargetPath       = "$env:SystemRoot\System32\cmd.exe"
        $lnk.Arguments        = "/k uv run mineai-control"
        $lnk.WorkingDirectory = $ProjectDir
        $lnk.IconLocation     = "$env:SystemRoot\System32\shell32.dll,25"
        $lnk.Description       = 'Start the mineai-toolkit MCP server (http://127.0.0.1:8765)'
        $lnk.Save()
        Write-Host "[OK] Desktop launcher created: $lnkPath"
    } catch {
        Write-Host "[!] Could not create the Desktop launcher: $($_.Exception.Message)"
    }
}

Write-Host ''
Write-Host 'mineai-toolkit is ready. To start the MCP server:'
Write-Host '  double-click "Start MineAI MCP" on the Desktop, or run:'
Write-Host "    cd `"$ProjectDir`"  &&  uv run mineai-control"
Write-Host 'Then it serves the web UI + /mcp endpoint on http://127.0.0.1:8765'
'@
Set-TextNoBom -Path $userInit -Content $userInitContent

# ---------- Step 4: run the init script as the desktop user ----------
Write-Step 'Running clone / uv sync / opencode config / launcher as the desktop user'
Invoke-AsInteractiveUser -File $userInit
Write-Ok 'User-privilege init finished'

# ---------- Done ----------
Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '  mineai-toolkit MCP setup complete' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host "  Project : $ProjectDir" -ForegroundColor Cyan
Write-Host "  Start   : Desktop shortcut 'Start MineAI MCP', or 'uv run mineai-control'" -ForegroundColor Cyan
Write-Host "  Serves  : http://127.0.0.1:8765  (web UI + $McpUrl)" -ForegroundColor Cyan
Write-Host '  Client  : opencode connects automatically (remote MCP)' -ForegroundColor Cyan

if ($NoDDrive) {
    Write-Host ''
    Write-Host '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!' -ForegroundColor Red
    Write-Host '  WARNING: D:\ drive was not found!' -ForegroundColor Red
    Write-Host "  The toolkit was placed on the Desktop instead:" -ForegroundColor Red
    Write-Host "    $ProjectDir" -ForegroundColor Red
    Write-Host '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!' -ForegroundColor Red
}

Write-Host "`nAll steps complete." -ForegroundColor Green
