$ProgressPreference = 'SilentlyContinue'
$apiUrl = "https://api.github.com/repos/leolcw1/token-gen-dist/contents/version.json"
$localVer = "1.0.0"

if (Test-Path (Join-Path $PSScriptRoot "version.json")) {
    try {
        $json = Get-Content (Join-Path $PSScriptRoot "version.json") -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($json.version) { $localVer = $json.version }
    } catch {}
}

try {
    $manifest = Invoke-RestMethod -Uri $apiUrl -Headers @{
        "Accept" = "application/vnd.github.v3.raw"
        "User-Agent" = "PokasUpdater"
        "Cache-Control" = "no-cache"
    }
    $remoteVer = $manifest.version

    if ($remoteVer -and ($remoteVer -ne $localVer)) {
        Write-Host "[UPDATE] Nova versao encontrada: v$remoteVer (Atual: v$localVer)" -ForegroundColor Cyan
        
        # Fecha qualquer instancia anterior aberta para evitar bloqueio de arquivos
        Get-Process -Name "PokasStoreMobile" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

        Write-Host "[DOWNLOAD] Baixando arquivos atualizados..." -ForegroundColor Yellow

        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("Cache-Control", "no-cache")
        $webClient.Headers.Add("Pragma", "no-cache")
        foreach ($prop in $manifest.files.PSObject.Properties) {
            $fname = [string]$prop.Name
            $furl = [string]$prop.Value
            Write-Host "  -> Baixando: $fname" -ForegroundColor Gray
            $outPath = Join-Path $PSScriptRoot $fname
            $webClient.DownloadFile($furl, $outPath)
        }

        $manifestJson = $manifest | ConvertTo-Json -Depth 5
        $utf8NoBom = New-Object System.Text.UTF8Encoding $False
        [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot "version.json"), $manifestJson, $utf8NoBom)
        Write-Host ""
        Write-Host "[SUCESSO] Aplicacao atualizada para v$remoteVer com sucesso!" -ForegroundColor Green
        Write-Host "Voce ja pode abrir o PokasStoreMobile.exe ou INICIAR.bat." -ForegroundColor Green
    } else {
        Write-Host "[INFO] A aplicacao ja esta na versao mais recente (v$localVer)." -ForegroundColor Green
    }
} catch {
    Write-Host "[ERRO] Falha ao verificar/baixar atualizacoes: $_" -ForegroundColor Red
}
