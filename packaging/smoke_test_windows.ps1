$ErrorActionPreference = "Stop"

$executable = Resolve-Path "dist/ToyokoTracker/ToyokoTracker.exe"
$port = 45170
$configDirectory = Join-Path $env:RUNNER_TEMP "toyoko-tracker-smoke-$PID"
$env:TOYOKO_TRACKER_CONFIG_DIR = $configDirectory
$process = Start-Process `
  -FilePath $executable `
  -WorkingDirectory (Split-Path $executable) `
  -ArgumentList "--local-only", "--port", "$port" `
  -PassThru

try {
  $deadline = (Get-Date).AddSeconds(45)
  $lastError = ""
  $httpReady = $false
  $windowReady = $false
  while ((Get-Date) -lt $deadline) {
    $process.Refresh()
    if ($process.HasExited) {
      throw "ToyokoTracker exited during startup with code $($process.ExitCode)"
    }
    $windowReady = (
      $process.MainWindowHandle -ne 0 -and
      $process.MainWindowTitle -match "Toyoko Chan"
    )
    if (-not $httpReady) {
      try {
        $response = Invoke-WebRequest `
          -Uri "http://127.0.0.1:$port/" `
          -UseBasicParsing `
          -TimeoutSec 3
        if ($response.StatusCode -eq 200 -and $response.Content -match "Toyoko") {
          $httpReady = $true
        }
        else {
          $lastError = "unexpected HTTP status $($response.StatusCode)"
        }
      }
      catch {
        $lastError = $_.Exception.Message
      }
    }
    if ($httpReady -and $windowReady) {
      break
    }
    Start-Sleep -Seconds 1
  }
  if (-not $httpReady -or -not $windowReady) {
    $process.Refresh()
    $startupLog = Join-Path $configDirectory "desktop-startup-error.log"
    if (Test-Path $startupLog) {
      $lastError = "$lastError`n$(Get-Content -Raw $startupLog)"
    }
    throw "ToyokoTracker did not become ready: HTTP=$httpReady window=$windowReady handle=$($process.MainWindowHandle) title='$($process.MainWindowTitle)'; $lastError"
  }
  Write-Output "Desktop smoke test passed: HTTP 200, window '$($process.MainWindowTitle)', PID $($process.Id)"
}
finally {
  Get-Process ToyokoTracker -ErrorAction SilentlyContinue | Stop-Process -Force
  Remove-Item -Recurse -Force $configDirectory -ErrorAction SilentlyContinue
}
