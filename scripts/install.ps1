# Install the Agentic Discipline CLIs, agentic-discipline.exe and agentic.exe, for this user.
#
#   irm https://raw.githubusercontent.com/lreyesm1999/agentic-discipline-kit/main/scripts/install.ps1 | iex
#
# Downloads the Windows x64 standalone build from the GitHub release, checks it against the
# release's SHA256SUMS, copies both executables to %LOCALAPPDATA%\Programs\agentic-discipline\bin
# and adds that folder to your user PATH. No administrator rights, no Python.
# Nothing is installed when a download fails or a checksum does not match.
# Works in Windows PowerShell 5.1 and PowerShell 7.
#
# Options are environment variables, because a piped script takes no arguments:
#   $env:AGENTIC_DISCIPLINE_VERSION = '2.1.0'      a specific release instead of the latest
#   $env:AGENTIC_DISCIPLINE_INSTALL_DIR = 'D:\bin' where the executables go
#   $env:AGENTIC_DISCIPLINE_NO_MODIFY_PATH = '1'   leave the user PATH alone
#   $env:AGENTIC_DISCIPLINE_RELEASES_URL = '...'   a mirror laid out like .../releases
#
# Uninstall:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/lreyesm1999/agentic-discipline-kit/main/scripts/install.ps1))) -Uninstall
#   .\scripts\install.ps1 -Uninstall          (from a checkout)
param([switch]$Uninstall)

# Everything lives in a function: piped into Invoke-Expression, an `exit` would close the
# user's own PowerShell window, while a thrown error only ends this script.
function Install-AgenticDiscipline {
    param([switch]$Uninstall)

    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # Windows PowerShell's progress bar slows downloads tenfold
    $repo = 'lreyesm1999/agentic-discipline-kit'
    $asset = 'agentic-discipline-Windows-X64.zip'
    $commands = @('agentic-discipline.exe', 'agentic.exe')

    $version = "$env:AGENTIC_DISCIPLINE_VERSION".TrimStart('v')
    $bindir = $env:AGENTIC_DISCIPLINE_INSTALL_DIR
    if (-not $bindir) { $bindir = Join-Path $env:LOCALAPPDATA 'Programs\agentic-discipline\bin' }
    $bindir = [IO.Path]::GetFullPath($bindir)
    $releases = $env:AGENTIC_DISCIPLINE_RELEASES_URL
    if (-not $releases) { $releases = "https://github.com/$repo/releases" }
    $releases = $releases.TrimEnd('/')
    $modifyPath = -not $env:AGENTIC_DISCIPLINE_NO_MODIFY_PATH

    function Get-UserPathEntries {
        # Read the raw value: expanding %VARIABLES% and writing them back would freeze them.
        $key = Get-Item -Path 'HKCU:\Environment'
        $raw = $key.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
        return @("$raw" -split ';' | Where-Object { $_ })
    }

    function Set-UserPathEntries([string[]]$entries) {
        Set-ItemProperty -Path 'HKCU:\Environment' -Name 'Path' -Value ($entries -join ';') -Type ExpandString
        # Setting any user variable broadcasts WM_SETTINGCHANGE, so new terminals see the PATH.
        [Environment]::SetEnvironmentVariable('AGENTIC_DISCIPLINE_PATH_REFRESH', '1', 'User')
        [Environment]::SetEnvironmentVariable('AGENTIC_DISCIPLINE_PATH_REFRESH', $null, 'User')
    }

    function Test-SamePath([string]$a, [string]$b) {
        return [string]::Equals($a.TrimEnd('\'), $b.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
    }

    if ($Uninstall) {
        $removed = $false
        foreach ($command in $commands) {
            $target = Join-Path $bindir $command
            if (Test-Path -LiteralPath $target) {
                Remove-Item -LiteralPath $target -Force
                Write-Host "Removed $target"
                $removed = $true
            }
        }
        if (-not $removed) { Write-Host "Nothing to remove in $bindir." }
        if ((Test-Path -LiteralPath $bindir) -and -not (Get-ChildItem -LiteralPath $bindir -Force)) {
            Remove-Item -LiteralPath $bindir -Force
        }
        if ($modifyPath) {
            $entries = Get-UserPathEntries
            $kept = @($entries | Where-Object { -not (Test-SamePath $_ $bindir) })
            if ($kept.Count -ne $entries.Count) {
                Set-UserPathEntries $kept
                Write-Host "Removed $bindir from your user PATH."
            }
        }
        Write-Host 'A copy installed with pip, pipx or uv is left alone: remove it with the same tool.'
        return
    }

    $arch = $env:PROCESSOR_ARCHITEW6432
    if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
    if ($arch -notin @('AMD64', 'ARM64')) {
        throw "There is no standalone build for $arch Windows. Install Python 3.11+ and run: pipx install agentic-discipline-kit"
    }
    if ($arch -eq 'ARM64') { Write-Host 'Windows on ARM: installing the x64 build, which runs under emulation.' }

    if ($version) { $base = "$releases/download/v$version" } else { $base = "$releases/latest/download" }

    # Windows PowerShell 5.1 does not offer TLS 1.2 by default, and GitHub requires it.
    if ($PSVersionTable.PSVersion.Major -lt 6) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    }

    $work = Join-Path ([IO.Path]::GetTempPath()) ("agentic-discipline-install-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work | Out-Null
    try {
        $archive = Join-Path $work $asset
        $sums = Join-Path $work 'SHA256SUMS'
        Write-Host "Downloading $base/$asset"
        try {
            Invoke-WebRequest -Uri "$base/$asset" -OutFile $archive -UseBasicParsing
        } catch {
            throw "Could not download $base/$asset ($($_.Exception.Message))"
        }
        try {
            Invoke-WebRequest -Uri "$base/SHA256SUMS" -OutFile $sums -UseBasicParsing
        } catch {
            throw "Could not download $base/SHA256SUMS; without it the download cannot be verified, so nothing was installed."
        }

        $expected = $null
        foreach ($line in Get-Content -LiteralPath $sums) {
            $fields = $line.Trim() -split '\s+', 2
            if ($fields.Count -eq 2 -and $fields[1].TrimStart('*') -eq $asset) {
                $expected = $fields[0].ToLowerInvariant()
                break
            }
        }
        if (-not $expected) { throw "SHA256SUMS has no line for $asset; nothing was installed." }
        $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "Checksum mismatch for ${asset}: expected $expected, got $actual; nothing was installed."
        }
        Write-Host "Checksum verified (SHA-256 $($actual.Substring(0, 16))...)."

        $unpacked = Join-Path $work 'unpacked'
        Expand-Archive -LiteralPath $archive -DestinationPath $unpacked
        foreach ($command in $commands) {
            if (-not (Test-Path -LiteralPath (Join-Path $unpacked $command))) {
                throw "$asset does not contain $command; nothing was installed."
            }
        }

        New-Item -ItemType Directory -Path $bindir -Force | Out-Null
        foreach ($command in $commands) {
            $target = Join-Path $bindir $command
            try {
                Copy-Item -LiteralPath (Join-Path $unpacked $command) -Destination $target -Force
            } catch {
                throw "Could not replace $target. Close any terminal or agent running it and try again."
            }
        }
        foreach ($command in $commands) {
            $target = Join-Path $bindir $command
            & $target --version *> $null
            if ($LASTEXITCODE -ne 0) { throw "$target was installed but does not run." }
        }
        $installed = (& (Join-Path $bindir 'agentic-discipline.exe') --version 2>&1 | Select-Object -First 1)
        Write-Host "Installed $installed to $bindir"
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }

    if ($modifyPath) {
        $entries = Get-UserPathEntries
        if (-not ($entries | Where-Object { Test-SamePath $_ $bindir })) {
            Set-UserPathEntries (@($entries) + $bindir)
            Write-Host "Added $bindir to your user PATH (new terminals pick it up)."
        }
        if (-not (($env:Path -split ';') | Where-Object { $_ -and (Test-SamePath $_ $bindir) })) {
            $env:Path = "$bindir;$env:Path"
        }
    } elseif (-not (($env:Path -split ';') | Where-Object { $_ -and (Test-SamePath $_ $bindir) })) {
        Write-Host "$bindir is not on your PATH; add it to run agentic-discipline by name."
    }
    $found = Get-Command 'agentic-discipline' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found -and -not (Test-SamePath (Split-Path -Parent $found.Source) $bindir)) {
        Write-Host "Note: $($found.Source) comes first on your PATH and will be used instead."
    }
    Write-Host 'Next: cd your-repository; agentic-discipline init'
}

Install-AgenticDiscipline -Uninstall:$Uninstall
