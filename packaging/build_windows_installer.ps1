$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$AppName = "KiCadComponentImporter"
$InnoCompiler = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
$BuildStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) (Join-Path "KiCadComponentImporterBuild" $BuildStamp)
$FinalArtifactRoot = Join-Path (Join-Path $Root "release_builds") $BuildStamp
$InstallerDir = Join-Path $TempRoot "installer"
$DistDir = Join-Path $TempRoot "dist"
$BuildDir = Join-Path $TempRoot "build"
$SpecDir = Join-Path $FinalArtifactRoot "spec"
$SourceDir = Join-Path $DistDir $AppName
$InnoScript = Join-Path $PSScriptRoot "KiCadComponentImporter.iss"
$GuiAssetsDir = Join-Path $Root "gui_assets"
$AppIconPath = Join-Path $GuiAssetsDir "app_icon.ico"

if (-not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "Inno Setup compiler not found: $InnoCompiler"
}

New-Item -ItemType Directory -Force -Path $InstallerDir | Out-Null
New-Item -ItemType Directory -Force -Path $SpecDir | Out-Null
New-Item -ItemType Directory -Force -Path $FinalArtifactRoot | Out-Null

Push-Location $Root
try {
    python -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --name $AppName `
        --distpath $DistDir `
        --workpath $BuildDir `
        --specpath $SpecDir `
        --icon $AppIconPath `
        --add-data "$GuiAssetsDir;gui_assets" `
        gui_main.pyw

    if (-not (Test-Path -LiteralPath (Join-Path $SourceDir "$AppName.exe"))) {
        throw "PyInstaller build did not create $AppName.exe"
    }

    & $InnoCompiler `
        "/DSourceDir=$SourceDir" `
        "/DOutputDir=$InstallerDir" `
        $InnoScript

    $SetupPath = Join-Path $InstallerDir "KiCadComponentImporter_Setup.exe"

    if (-not (Test-Path -LiteralPath $SetupPath)) {
        throw "Inno Setup did not create installer: $SetupPath"
    }

    $FinalSetupPath = Join-Path $FinalArtifactRoot "KiCadComponentImporter_Setup.exe"
    Copy-Item -LiteralPath $SetupPath -Destination $FinalSetupPath -Force

    Write-Host "Built app folder: $SourceDir"
    Write-Host "Built installer: $FinalSetupPath"
}
finally {
    Pop-Location
}
