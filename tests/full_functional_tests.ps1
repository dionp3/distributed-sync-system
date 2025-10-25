# =====================================================================
# Distributed Sync System - Full Functional Test Suite 
# =====================================================================

# --- 0. PERSIAPAN GLOBAL ---
$Ports = 8001, 8002, 8003
$Headers = @{"Content-Type" = "application/json"}
$LeaderPort = $null 
$QueuePort = 8011
$CachePort1 = 8021
$CachePort2 = 8022
$CachePort3 = 8023
$LOCK_TIMEOUT_SECS = 10
$REDELIVERY_WAIT_SECS = 35 

function Find-RaftLeader {
    $probeBody = @{lock_name = "probe_lock"; client_id = "PowerShell_Prober"; lock_type = "exclusive"; timeout = 1.0} | ConvertTo-Json
    
    Write-Host "--- Probing untuk Leader Raft ---"
    foreach ($Port in $Ports) {
        $lockURL = "http://localhost:$Port/lock/acquire"
        try {
            $result = Invoke-RestMethod -Uri $lockURL -Method Post -Headers $Headers -Body $probeBody -TimeoutSec 1
            if ($result.success -eq $True) {
                Write-Host "✅ LEADER DITEMUKAN: Port $Port."
                Invoke-RestMethod -Uri "http://localhost:$Port/lock/release" -Method Post -Headers $Headers -Body (@{lock_name = "probe_lock"; client_id = "PowerShell_Prober"} | ConvertTo-Json) | Out-Null
                return $Port
            }
        } catch {}
    }
    Write-Host "⚠️ GAGAL menemukan Leader yang stabil."
    return $null
}

$LeaderPort = Find-RaftLeader
if (-not $LeaderPort) { exit }

Write-Host "🔑 Raft Leader Aktif di Port $LeaderPort."

Write-Host "Memulai pengujian..."
$lockAcquireURL = "http://localhost:$LeaderPort/lock/acquire"
$lockReleaseURL = "http://localhost:$LeaderPort/lock/release"

# =====================================================================
# 1. UJI DISTRIBUTED LOCK MANAGER (DLM) - KONSISTENSI & DEADLOCK
# =====================================================================
Write-Host "`n======================= DLM (Raft) Test ========================"
$dataA = @{lock_name="DB_RW"; client_id="ClientA"; lock_type="exclusive"; timeout=$LOCK_TIMEOUT_SECS}
$dataB = @{lock_name="DB_RW"; client_id="ClientB"; lock_type="exclusive"; timeout=1.0}

# 1.1 Acquire Lock (Client A)
Write-Host "[1] Client A Acquire (Eksklusif)..."
$resultA = Invoke-RestMethod -Uri $lockAcquireURL -Method Post -Headers $Headers -Body ($dataA | ConvertTo-Json)
Write-Host "    Status Acquire A: $($resultA.success)"

# 1.2 Contention (Client B)
Write-Host "[2] Client B Contention (Harus Ditolak)..."
$resultB = Invoke-RestMethod -Uri $lockAcquireURL -Method Post -Headers $Headers -Body ($dataB | ConvertTo-Json)
Write-Host "    Status Acquire B: $($resultB.success)"

# 1.3 Uji Deadlock Detection
Write-Host "`n[3] Uji Deadlock: Menunggu $($LOCK_TIMEOUT_SECS + 2) detik..."
Write-Host "    (Cek Log Node $LeaderPort untuk pesan 'DEADLOCK DETECTED')"
Start-Sleep -Seconds ($LOCK_TIMEOUT_SECS + 2) 
$LeaderContainer = "docker-node_lock_$($LeaderPort-8000)-1"
$deadlockPassed = docker logs $LeaderContainer 2>&1 | Select-String "DEADLOCK DETECTED"

# 1.4 Acquire Ulang (Client B) - Verifikasi Lock Dirilis
Write-Host "[4] Client B: Acquire Ulang (Verifikasi Deadlock Release)..."
$finalResult = Invoke-RestMethod -Uri $lockAcquireURL -Method Post -Headers $Headers -Body ($dataB | ConvertTo-Json)

if ($finalResult.success -eq $True) {
    Write-Host "✅ PASSED: Deadlock Detection BERHASIL. Lock berhasil diperoleh kembali."
    Invoke-RestMethod -Uri $lockReleaseURL -Method Post -Headers $Headers -Body ($dataB | ConvertTo-Json) | Out-Null
} else {
    Write-Host "❌ FAILED: Lock masih macet setelah deteksi."
}
if ($deadlockPassed) { Write-Host "✅ LOG CHECK: Deadlock pesan ditemukan di log." }

# =====================================================================
# 2. UJI DISTRIBUTED QUEUE SYSTEM - AT-LEAST-ONCE DELIVERY 
# =====================================================================
Write-Host "`n======================= DQS (Queue) Test ======================="
$topicName = "INVOICE_PROCESS"
$urlQueuePublish = "http://localhost:$QueuePort/queue/publish"
$urlQueueConsume = "http://localhost:$QueuePort/queue/consume"
$urlQueueAck = "http://localhost:$QueuePort/queue/ack"

# 2.1 Publish Pesan
Write-Host "[5] Pesan dipublish..."
Invoke-RestMethod -Uri $urlQueuePublish -Method Post -Headers $Headers -Body (@{topic=$topicName; data=@{order_id="ORD101"}} | ConvertTo-Json) | Out-Null

# 2.2 Consume Pertama (Tanpa ACK)
$msgResult = Invoke-RestMethod -Uri $urlQueueConsume -Method Post -ContentType "application/json" -Body (@{topic=$topicName} | ConvertTo-Json)
$MessageObject = $msgResult | ConvertTo-Json | ConvertFrom-Json
$MessageID = $MessageObject.message.id
Write-Host "    Pesan dikonsumsi (ID: $MessageID). TIDAK ada ACK."

# 2.3 Uji Redelivery
Write-Host "⏱️ [6] Menunggu $REDELIVERY_WAIT_SECS detik untuk Redelivery Monitor..."
Start-Sleep -Seconds $REDELIVERY_WAIT_SECS

# 2.4 Consume Kedua (Verifikasi Redelivery)
$msgResult2 = Invoke-RestMethod -Uri $urlQueueConsume -Method Post -ContentType "application/json" -Body (@{topic=$topicName} | ConvertTo-Json)

if ($msgResult2.message.id -eq $MessageID) {
    Write-Host "✅ PASSED: At-Least-Once Delivery BERHASIL (Pesan ID $MessageID di-Redeliver)."
    # Cleanup: Kirim ACK
    Invoke-RestMethod -Uri $urlQueueAck -Method Post -Headers $Headers -Body (@{topic=$topicName; message_id=$MessageID} | ConvertTo-Json) | Out-Null
} else {
    Write-Host "❌ FAILED: Redelivery Monitor tidak bekerja."
}

# =====================================================================
# 3. UJI DISTRIBUTED CACHE COHERENCE (MESI) 
# =====================================================================
Write-Host "`n====================== DCC (MESI) Test ======================="
$CacheKey = "USER_CONFIG_FILE"

# 3.1 Node 1: WRITE (I -> M) - Menulis Versi 1
Write-Host "[7] Node ${CachePort1}: WRITE (I -> M) dan Broadcasting INVAL..."
Invoke-RestMethod -Uri "http://localhost:$CachePort1/cache/write" -Method Post -Headers $Headers -Body (@{key=$CacheKey; value="Version_1"} | ConvertTo-Json) | Out-Null

# 3.2 Node 2: READ (I -> S) - Mendapatkan salinan Shared
Write-Host "[8] Node ${CachePort2}: READ (I -> S)..."
Invoke-RestMethod -Uri "http://localhost:$CachePort2/cache/read" -Method Post -Headers $Headers -Body (@{key=$CacheKey} | ConvertTo-Json) | Out-Null
Write-Host "    (Node 8022 sekarang memegang state Shared)"

# 3.3 Node 3: WRITE (Memicu Invalidasi) - Menulis Versi 2
Write-Host "[9] Node ${CachePort3}: WRITE (Memicu INVAL ke peer)..."
Invoke-RestMethod -Uri "http://localhost:$CachePort3/cache/write" -Method Post -Headers $Headers -Body (@{key=$CacheKey; value="Version_2_Final"} | ConvertTo-Json) | Out-Null
Start-Sleep -Seconds 1.5 # Beri waktu RPC untuk propagasi

# 3.4 Verifikasi Invalidation pada Node 2 (Log Check)
Write-Host "[10] Verifikasi: Cek Log Node ${CachePort2} untuk pesan INVAL..."
$CacheContainerB = "docker-node_cache_2-1"
$invalPassed = docker logs $CacheContainerB 2>&1 | Select-String "Received INVAL for $CacheKey. State -> I"

if ($invalPassed) {
    Write-Host "✅ PASSED: MESI Invalidation BERHASIL. Node B mengubah state ke Invalid."
} else {
    Write-Host "❌ FAILED: Node B gagal memproses INVAL."
}

# =====================================================================
# 4. FINAL STATUS
# =====================================================================
Write-Host "`n========================================================"
Write-Host "✅ PENGUJIAN FUNGSIONALITAS INTI SELESAI. SIAP UNTUK PERFORMANCE TEST."
Write-Host "========================================================"