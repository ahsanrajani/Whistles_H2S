# Packs the repository for upload to Google Cloud Shell, leaving out node_modules, build output, caches and uploads.
# Run from the repository root in PowerShell:   powershell -ExecutionPolicy Bypass -File deploy\gcp\make-zip.ps1
$root = (Get-Location).Path
$stage = Join-Path $env:TEMP "guru-gcp-stage"
$zip = Join-Path $root "guru-gcp.zip"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
if (Test-Path $zip) { Remove-Item $zip -Force }
New-Item -ItemType Directory $stage | Out-Null
$stage = (Get-Item $stage).FullName     # long-path form: $env:TEMP can be an 8.3 short path
# robocopy exit codes below 8 mean success
robocopy $root $stage /E /XD node_modules .next __pycache__ .git preview uploads /XF *.zip *.pyc guru.db .env /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
# Write entries by hand with forward slashes: Compress-Archive and CreateFromDirectory both use backslashes on
# Windows PowerShell 5.1, which Linux / Cloud Shell extracts as odd file names.
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Create)
Get-ChildItem $stage -Recurse -File | ForEach-Object {
    $name = $_.FullName.Substring($stage.Length + 1).Replace("\", "/")
    [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $_.FullName, $name, [IO.Compression.CompressionLevel]::Optimal)
}
$archive.Dispose()
Remove-Item $stage -Recurse -Force
"{0}  ({1:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB)
