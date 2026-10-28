param([switch]$Replace, [string]$BinDir = "$env:LOCALAPPDATA\AgentFleet\bin")
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$Source = Join-Path $Root 'target\release\agent-fleet.exe'
$Destination = Join-Path $BinDir 'agent-fleet.exe'
if (!(Test-Path $Source -PathType Leaf)) { throw 'Build first: cargo build -p fleet-cli --release --locked' }
if ((Test-Path $Destination) -and !$Replace) { throw "Already installed: $Destination. Inspect it, then use -Replace to keep a backup." }
New-Item -ItemType Directory -Force $BinDir | Out-Null
if (Test-Path $Destination) { Move-Item $Destination "$Destination.backup-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))" }
Copy-Item $Source $Destination
& $Destination --version
Write-Output "Installed native CLI: $Destination"
Write-Output 'Add this directory to your user PATH. The Tauri desktop installer is in target\release\bundle. Existing AgentPool data remains in place.'
