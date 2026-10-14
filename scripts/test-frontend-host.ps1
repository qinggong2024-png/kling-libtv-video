param(
    [string]$HostScript = (Join-Path $PSScriptRoot 'manage-frontend-host.ps1'),
    [string]$NodePath = 'D:\New Folder\node.exe'
)

$ErrorActionPreference = 'Stop'
$HostScript = (Resolve-Path -LiteralPath $HostScript).Path
$parseErrors = $null
$tokens = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($HostScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$resolver = $ast.Find({
    param($item)
    $item -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $item.Name -eq 'Resolve-NodeExecutable'
}, $true)
if (-not $resolver) { throw 'Node resolver is missing.' }
. ([scriptblock]::Create($resolver.Extent.Text))

$originalPath = $env:PATH
try {
    $env:PATH = '; ;' + (Split-Path -Parent $NodePath) + ';;'
    $expected = (Resolve-Path -LiteralPath $NodePath).Path
    foreach ($explicit in @($NodePath, '')) {
        $resolved = Resolve-NodeExecutable -Explicit $explicit
        if (-not $resolved -or -not $resolved.Version) { throw 'Node resolution failed with empty PATH entries.' }
        if ($explicit -and $resolved.Path -ne $expected) { throw 'Explicit Node path was not selected.' }
    }
    Write-Output 'PASS: explicit and discovered Node tolerate empty PATH entries.'
}
finally { $env:PATH = $originalPath }

# A root without frontend must fail before any Node/server process is launched.
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$probeRoot = Join-Path $tempRoot ('libtv-frontend-regression-' + [Guid]::NewGuid().ToString('N'))
$originalLocation = Get-Location
New-Item -ItemType Directory -Path $probeRoot | Out-Null
try {
    $failed = $false
    try { & $HostScript -Action Serve -ProjectRoot $probeRoot -NodePath $NodePath }
    catch { $failed = $true }
    if (-not $failed) { throw 'Expected missing-frontend startup failure.' }
    $log = Join-Path $probeRoot 'var\logs\frontend.host.log'
    if (-not (Test-Path -LiteralPath $log)) { throw 'Startup failure was not logged.' }
    if (-not (Select-String -LiteralPath $log -Pattern 'UNHANDLED:')) { throw 'Unhandled failure detail is missing.' }
    Write-Output 'PASS: early startup failure is recorded in the host log.'
}
finally {
    Set-Location -LiteralPath $originalLocation.Path
    $resolvedProbe = [IO.Path]::GetFullPath($probeRoot)
    $prefix = $tempRoot.TrimEnd('\') + '\libtv-frontend-regression-'
    if (-not $resolvedProbe.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to remove a regression directory outside the temporary root.'
    }
    Remove-Item -LiteralPath $resolvedProbe -Recurse -Force
}
