#requires -Version 5

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApkPath,

    [string]$Name,

    [string]$OutRoot,

    [switch]$SkipJadx,

    [switch]$SkipApktool,

    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Resolve-ReverseToolSpec {
    param([Parameter(Mandatory = $true)][string]$Name)

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return [pscustomobject]@{
            Available = $true
            Command = $cmd.Source
            PrefixArgs = @()
        }
    }

    $candidates = switch ($Name) {
        'jadx' {
            @(
                (Join-Path $env:USERPROFILE 'Tools\jadx\bin\jadx.bat'),
                (Join-Path $env:USERPROFILE 'Tools\jadx\bin\jadx.cmd'),
                (Join-Path $env:USERPROFILE 'Tools\jadx\bin\jadx.exe')
            )
        }
        'apktool' {
            @(
                (Join-Path $env:USERPROFILE 'Tools\apktool\apktool.bat'),
                (Join-Path $env:USERPROFILE 'Tools\apktool\apktool.cmd')
            )
        }
        default { @() }
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return [pscustomobject]@{
                Available = $true
                Command = $candidate
                PrefixArgs = @()
            }
        }
    }

    if ($Name -eq 'apktool') {
        $jar = Join-Path $env:USERPROFILE 'Tools\apktool\apktool.jar'
        if (Test-Path -LiteralPath $jar) {
            return [pscustomobject]@{
                Available = $true
                Command = 'java'
                PrefixArgs = @('-jar', $jar)
            }
        }
    }

    return [pscustomobject]@{
        Available = $false
        Command = ''
        PrefixArgs = @()
    }
}

function Get-SafeName {
    param([Parameter(Mandatory = $true)][string]$PathValue)

    $raw = [System.IO.Path]::GetFileNameWithoutExtension($PathValue)
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $raw = 'apk'
    }
    return ($raw -replace '[^A-Za-z0-9._-]', '_')
}

function Get-DefaultOutRoot {
    param([Parameter(Mandatory = $true)][string]$ApkFilePath)

    $parent = Split-Path -Path $ApkFilePath -Parent
    if ([string]::IsNullOrWhiteSpace($parent)) {
        return [System.IO.Directory]::GetCurrentDirectory()
    }
    return $parent
}

function Get-ManifestPackage {
    param([Parameter(Mandatory = $true)][string]$ManifestPath)

    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        return ''
    }

    try {
        $xml = [xml](Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8)
        return [string]$xml.manifest.package
    }
    catch {
        return ''
    }
}

if (-not (Test-Path -LiteralPath $ApkPath)) {
    throw "APK not found: $ApkPath"
}

$jadxSpec = $null
$apktoolSpec = $null

if (-not $SkipJadx) {
    $jadxSpec = Resolve-ReverseToolSpec -Name 'jadx'
    if (-not $jadxSpec.Available) {
        throw 'jadx not found. Install from https://github.com/skylot/jadx or place it under %USERPROFILE%\Tools\jadx\'
    }
}
if (-not $SkipApktool) {
    $apktoolSpec = Resolve-ReverseToolSpec -Name 'apktool'
    if (-not $apktoolSpec.Available) {
        throw 'apktool not found. Install from https://apktool.org/ or place it under %USERPROFILE%\Tools\apktool\'
    }
}

$taskName = if ($Name) {
    ($Name -replace '[^A-Za-z0-9._-]', '_')
} else {
    Get-SafeName -PathValue $ApkPath
}
if ([string]::IsNullOrWhiteSpace($taskName) -or $taskName -in @('.', '..')) {
    throw 'Invalid task name.'
}

$resolvedOutRoot = if ([string]::IsNullOrWhiteSpace($OutRoot)) { Get-DefaultOutRoot -ApkFilePath $ApkPath } else { $OutRoot }
$taskRoot = Join-Path $resolvedOutRoot $taskName
$jadxOut = Join-Path $taskRoot 'jadx'
$apktoolOut = Join-Path $taskRoot 'apktool'

if (-not (Test-Path -LiteralPath $resolvedOutRoot)) {
    New-Item -ItemType Directory -Path $resolvedOutRoot -Force | Out-Null
}

$resolvedOutRootFull = [System.IO.Path]::GetFullPath($resolvedOutRoot).TrimEnd('\', '/')
$resolvedTaskRootFull = [System.IO.Path]::GetFullPath($taskRoot)
$expectedPrefix = $resolvedOutRootFull + [System.IO.Path]::DirectorySeparatorChar
if (-not $resolvedTaskRootFull.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Task output must stay inside the selected output root.'
}

if ($Clean -and (Test-Path -LiteralPath $taskRoot)) {
    Remove-Item -LiteralPath $taskRoot -Recurse -Force
}

if (-not (Test-Path -LiteralPath $taskRoot)) {
    New-Item -ItemType Directory -Path $taskRoot -Force | Out-Null
}

$jadxExitCode = $null
if (-not $SkipJadx) {
    if (Test-Path -LiteralPath $jadxOut) {
        Remove-Item -LiteralPath $jadxOut -Recurse -Force
    }
    & $jadxSpec.Command @($jadxSpec.PrefixArgs + @('-d', $jadxOut, $ApkPath))
    $jadxExitCode = $LASTEXITCODE
}

$apktoolExitCode = $null
if (-not $SkipApktool) {
    if (Test-Path -LiteralPath $apktoolOut) {
        Remove-Item -LiteralPath $apktoolOut -Recurse -Force
    }
    & $apktoolSpec.Command @($apktoolSpec.PrefixArgs + @('d', $ApkPath, '-o', $apktoolOut, '-f'))
    $apktoolExitCode = $LASTEXITCODE
}

$manifestPath = Join-Path $apktoolOut 'AndroidManifest.xml'
$packageName = if (-not $SkipApktool) { Get-ManifestPackage -ManifestPath $manifestPath } else { '' }
$javaCount = if ((Test-Path -LiteralPath $jadxOut)) { (Get-ChildItem -LiteralPath $jadxOut -Recurse -File -Filter '*.java' | Measure-Object).Count } else { 0 }
$smaliDirCount = if ((Test-Path -LiteralPath $apktoolOut)) { (Get-ChildItem -LiteralPath $apktoolOut -Directory -Filter 'smali*' | Measure-Object).Count } else { 0 }
$libCount = if ((Test-Path -LiteralPath $apktoolOut)) { (Get-ChildItem -LiteralPath $apktoolOut -Recurse -File -Filter '*.so' | Measure-Object).Count } else { 0 }
$resXmlCount = if ((Test-Path -LiteralPath $apktoolOut)) { (Get-ChildItem -LiteralPath $apktoolOut -Recurse -File -Filter '*.xml' | Measure-Object).Count } else { 0 }

"task_root=$taskRoot"
"jadx_out=$jadxOut"
"apktool_out=$apktoolOut"
"package=$packageName"
"jadx_exit_code=$jadxExitCode"
"apktool_exit_code=$apktoolExitCode"
"java_files=$javaCount"
"smali_dirs=$smaliDirCount"
"so_files=$libCount"
"xml_files=$resXmlCount"

if (($jadxExitCode -ne $null) -and ($jadxExitCode -ne 0)) {
    "warning=jadx returned non-zero exit code; inspect output but treat exported sources as usable if present"
}
