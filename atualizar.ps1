$ProgressPreference = 'SilentlyContinue'
$apiUrl = "https://api.github.com/repos/leolcw1/token-gen-dist/contents/version.json"
$localVer = "1.0.0"

if (Test-Path (Join-Path $PSScriptRoot "version.json")) {
    try {
        $json = Get-Content (Join-Path $PSScriptRoot "version.json") -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($json.version) { $localVer = $json.version }
    } catch {}
}

function Parse-VersionObj($vStr) {
    try {
        if (-not $vStr) { return New-Object System.Version(0, 0, 0, 0) }
        $clean = ($vStr.ToString() -replace '^[vV]', '').Trim()
        $parts = $clean.Split('.')
        $ints = @()
        foreach ($p in $parts) {
            $digits = ($p -replace '\D', '')
            if ($digits) { $ints += [int]$digits }
        }
        while ($ints.Count -lt 4) { $ints += 0 }
        return New-Object System.Version($ints[0], $ints[1], $ints[2], $ints[3])
    } catch {
        return New-Object System.Version(0, 0, 0, 0)
    }
}

try {
    $manifest = Invoke-RestMethod -Uri $apiUrl -Headers @{
        "Accept" = "application/vnd.github.v3.raw"
        "User-Agent" = "PokasUpdater"
        "Cache-Control" = "no-cache"
    }
    $remoteVer = $manifest.version

    $remoteParsed = Parse-VersionObj $remoteVer
    $localParsed = Parse-VersionObj $localVer

    # REGRA ESTRITA: Apenas atualiza se a versao remota for ESTRITAMENTE SUPERIOR (-gt)
    if ($remoteVer -and ($remoteParsed -gt $localParsed)) {
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

            # REGRA INVIOLAVEL: NUNCA tocar em arquivos .txt ou diretorios de contas/backups
            $fLower = $fname.ToLower()
            if ($fLower.EndsWith(".txt") -or $fLower.EndsWith(".lic") -or $fLower.EndsWith(".key") -or $fLower.EndsWith(".vault") -or $fLower.Contains("contas") -or $fLower.Contains("backup")) {
                continue
            }

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
        Write-Host "[INFO] A aplicacao ja esta na versao mais recente (v$localVer). Nenhuma atualizacao pendente." -ForegroundColor Green
    }
} catch {
    Write-Host "[ERRO] Falha ao verificar/baixar atualizacoes: $_" -ForegroundColor Red
}
