# Build only: no downloads, installation, device access or release packaging.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Output,
    [string]$Zig = 'zig'
)
$ErrorActionPreference = 'Stop'
$version = & $Zig version
if ($LASTEXITCODE -ne 0 -or "$version".Trim() -ne '0.14.1') {
    throw 'This build requires an independently installed Zig 0.14.1.'
}
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..')).TrimEnd([IO.Path]::DirectorySeparatorChar)
$out = [IO.Path]::GetFullPath($Output)
if ($out.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or
    $out.StartsWith($repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose an output path outside the repository; do not add binaries to source control.'
}
if (-not (Test-Path -LiteralPath (Split-Path -Parent $out) -PathType Container)) {
    throw 'The output directory must already exist.'
}
# Do not simplify this feature list: cortex_a5 defaults retain NEON/VFPv4.
$cpu = '-mcpu=cortex_a5-d32-neon-fp16-vfp4-vfp4d16-vfp4d16sp-vfp4sp-vfp3-vfp3sp+vfp3d16+vfp3d16sp'
& $Zig cc -target arm-linux-musleabihf $cpu -static -Os -Wall -Wextra -Werror (Join-Path $PSScriptRoot 'continuous_diag.c') -o $out
if ($LASTEXITCODE -ne 0) { throw "Zig build failed: $LASTEXITCODE" }
$artifact = Get-Item -LiteralPath $out
$hash = Get-FileHash -LiteralPath $out -Algorithm SHA256
Write-Output "output=$($artifact.FullName)"
Write-Output "bytes=$($artifact.Length)"
Write-Output "sha256=$($hash.Hash.ToLowerInvariant())"
