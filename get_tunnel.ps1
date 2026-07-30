$r = try { Invoke-RestMethod -Uri 'http://127.0.0.1:20241/quicktunnel' -ErrorAction SilentlyContinue } catch { $null }
if ($r -and $r.hostname) {
    Write-Host "[OK] Cloudflare Tunnel HTTPS URL của bạn:" -ForegroundColor Green
    Write-Host ("https://" + $r.hostname) -ForegroundColor Yellow
    Write-Host ("Web Admin: https://" + $r.hostname + "/admin") -ForegroundColor Cyan
} else {
    $dockerLog = try { docker logs veostudio_admin_tunnel 2>&1 | Select-String "trycloudflare.com" } catch { $null }
    if ($dockerLog) {
        Write-Host $dockerLog -ForegroundColor Yellow
    } else {
        Write-Host "⚠️ Chưa bật Cloudflare Tunnel!" -ForegroundColor Red
        Write-Host "   Hãy chạy 1 trong 2 tệp sau:" -ForegroundColor Gray
        Write-Host "   1. Chay_Cloudflare_Tunnel.bat (Chạy trực tiếp không cần Docker)" -ForegroundColor Gray
        Write-Host "   2. Chay_Docker_WebAdmin.bat (Nếu sử dụng Docker Desktop)" -ForegroundColor Gray
    }
}
