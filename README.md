# Distributed Sync System (DSS)

Sistem ini mensimulasikan arsitektur *distributed systems* modern, berfokus pada **sinkronisasi data yang konsisten**, *fault tolerance*, dan skalabilitas. DSS mengimplementasikan tiga mekanisme konsensus/koherensi yaitu **Raft Consensus**, **Consistent Hashing**, dan **MESI Cache Coherence**, semuanya dengan menggunakan Docker Compose.

[](https://opensource.org/licenses/MIT) [](https://www.python.org/) [](https://www.docker.com/)

-----

## Fitur Inti yang Diimplementasikan

Proyek ini telah menyelesaikan semua *Core Requirements* dengan fokus pada ketahanan di bawah kegagalan.

### 1. Distributed Lock Manager (DLM)

  * **Algoritma:** **Raft Consensus** (Implementasi *from scratch*).
  * **Ketahanan:** Mendukung *Leader Election* otomatis dan *Log Replication* ke 3 node.
  * **Safety:** Menerapkan *Deadlock Detection* berbasis *timeout* yang berhasil memicu *release* otomatis pada *lock* yang macet (*verified* saat *load test*).

### 2. Distributed Queue System (DQS)

  * **Distribusi:** **Consistent Hashing** digunakan untuk merutekan *topic* ke *Queue Node* yang bertanggung jawab, menjamin skalabilitas horizontal.
  * **Delivery Guarantee:** Menerapkan **At-Least-Once Delivery** melalui mekanisme *Pending Acknowledgement Queue* dan *Redelivery Monitor* (*asyncio task*).
  * **Persistence:** Menggunakan **Redis** untuk *message persistence* dan *state storage*.

### 3. Distributed Cache Coherence (DCC)

  * **Protokol:** Protokol **MESI (Modified, Exclusive, Shared, Invalid)** berbasis *invalidation* untuk menjaga koherensi data di 3 node Cache.
  * **Efisiensi:** Menggunakan kebijakan *Cache Replacement* **LRU (Least Recently Used)**, didukung oleh *Write-Back* untuk memastikan tidak ada data Modified yang hilang saat *eviction*.

### 4. Containerization & Monitoring

  * **Orkestrasi:** Deployment penuh menggunakan **Docker Compose** (total 11 *services*).
  * **Observability:** Semua node Python mengekspos *endpoint* `/metrics` yang di-*scrape* oleh **Prometheus** dan divisualisasikan oleh **Grafana** (`http://localhost:3000`).

-----

## Panduan Deployment dan Pengujian

### Prasyarat

  * **Python 3.8+**
  * **Docker & Docker Compose** (Wajib)

### Langkah-Langkah Deployment

1.  **Kloning Repository:**

    ```bash
    git clone 
    cd distributed-sync-system
    ```

2.  **Siapkan Environment:**
    Salin dan isi file `.env.example` menjadi `.env` di *root directory*. Pastikan variabel `RAFT_PEERS`, `QUEUE_NODES`, dan `CACHE_PEERS` terisi dengan daftar *service* Docker yang benar (tanpa *quotes* di sekeliling nilai JSON).

3.  **Build dan Jalankan Sistem:**
    Perintah ini akan membangun *image* Python dan meluncurkan 11 *services* di *background*.

    ```bash
    docker compose -f docker/docker-compose.yml up --build -d
    ```

4.  **Verifikasi Status:**

    ```bash
    docker compose -f docker/docker-compose.yml ps
    ```

    Semua *services* (9 node aplikasi + 2 Monitoring + 1 Redis) harus berstatus **`Up`**.

### Pengujian Fungsional (PowerShell)

#### 1\. Identifikasi Leader Raft

Gunakan *probe* pada port 8001, 8002, 8003 untuk menemukan Leader aktif (`$LeaderPort`).

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
                    # Rilis probe lock
                    Invoke-RestMethod -Uri "http://localhost:$Port/lock/release" -Method Post -Headers $Headers -Body (@{lock_name = "probe_lock"; client_id = "PowerShell_Prober"} | ConvertTo-Json) | Out-Null
                    return $Port
                }
            } catch {}
        }
        Write-Host "⚠️ GAGAL menemukan Leader yang stabil."
        return $null
    }

#### 2\. Uji Failover Lock Manager (Wajib Demo)

Ini membuktikan *failover* berjalan. Asumsikan Leader di Port 8003:

1.  **Acquire Lock:** `curl -X POST http://localhost:8003/lock/acquire ...`
2.  **Stop Leader:** `docker stop docker-node_lock_3-1`
3.  **Verifikasi Leader Baru:** Jalankan *probe* lagi. Node 8001 atau 8002 akan menjadi Leader baru.
4.  **Acquire pada Leader Baru:** `curl -X POST http://localhost:8001/lock/acquire ...` (Harus berhasil jika *lock* lama sudah dirilis/di-*timeout*).

#### 3\. Uji Redelivery Queue (At-Least-Once)

1.  **Publish:** `curl -X POST http://localhost:8011/queue/publish ...`
2.  **Consume (Tanpa ACK):** `curl -X POST http://localhost:8011/queue/consume ...`
3.  **Tunggu 35 detik** (Timeout Monitor).
4.  **Consume Lagi:** *Request* ini akan mendapatkan pesan yang sama (Bukti *At-Least-Once*).

-----

## Video Demo

[]
