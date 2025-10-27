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
    docker compose -f docker/docker-compose.yml --env-file .env up --build -d
    ```

4.  **Verifikasi Status:**

    ```bash
    docker compose -f docker/docker-compose.yml ps
    ```

    Semua *services* (9 node aplikasi + 2 Monitoring + 1 Redis) harus berstatus **`Up`**.

## Panduan Pengujian Fungsionalitas Inti (E2E)

File **`full_functional_tests.ps1`** adalah *suite* pengujian *end-to-end* (E2E) berbasis PowerShell yang secara otomatis memvalidasi semua ***Core Requirements***. Skrip ini mensimulasikan kondisi *contention*, *deadlock*, dan *fault recovery* secara berurutan.

### Cara Menjalankan Test Suite

Pastikan *virtual environment* (`venv`) Anda aktif dan semua *services* Docker berjalan (`Up`).

```bash
.\tests\full_functional_tests.ps1
```

-----

Skrip ini dibagi menjadi tiga bagian besar, masing-masing memvalidasi satu klaster fungsional.

### A. Uji Distributed Lock Manager (DLM) 

**Tujuan:** Membuktikan Raft Consensus menjamin *Linearizability* dan *Deadlock Monitor* berfungsi.

| Langkah Kritis | Narasi Logis | Hasil Verifikasi Kunci |
| :--- | :--- | :--- |
| **`Find-RaftLeader`** | Mengidentifikasi Leader Raft yang aktif (misalnya, Port 8003) sebelum memulai. | **`✅ LEADER DITEMUKAN: Port XXXX`** |
| **1.2 Contention** | Client A memegang *lock*. Client B mencoba *acquire* dan **ditolak** (`Status Acquire B: False`). | **Raft Consensus** membuktikan *lock state* konsisten. |
| **1.3 Deadlock Detection** | *Lock* ditinggalkan Client A dan *script* menunggu *timeout* (12 detik). | Log Leader harus mencatat **`DEADLOCK DETECTED`**. |
| **1.4 Acquire Ulang** | Client B berhasil *acquire* kembali. | **`✅ PASSED: Deadlock Detection BERHASIL.`** (Membuktikan *release* otomatis berhasil). |

### B. Uji Distributed Queue System (DQS) 

**Tujuan:** Membuktikan jaminan *At-Least-Once Delivery* melalui *Redelivery Monitor*.

| Langkah Kritis | Narasi Logis | Hasil Verifikasi Kunci |
| :--- | :--- | :--- |
| **2.2 Consume Pertama** | Pesan dikonsumsi tetapi **TIDAK ada ACK** (Simulasi Kegagalan Konsumen). Pesan pindah ke *Pending Queue*. | Log mencatat `Pesan dikonsumsi (ID: [ID])`. |
| **2.3 Redelivery Wait** | Skrip menunggu **35 detik** (melebihi *timeout* 30s). | *Background Monitor* mengambil alih pesan yang macet. |
| **2.4 Consume Kedua** | *Request* kedua berhasil mengambil pesan. | **`✅ PASSED: At-Least-Once Delivery BERHASIL.`** (ID pesan kedua cocok dengan ID pertama). |

### C. Uji Distributed Cache Coherence (DCC) 

**Tujuan:** Membuktikan **MESI Invalidation** bekerja di seluruh klaster.

| Langkah Kritis | Narasi Logis | Hasil Verifikasi Kunci |
| :--- | :--- | :--- |
| **3.1 Write (Node 1)** | Node 1 menulis V1 (State $I \to M$) dan memicu *Invalidate Broadcast*. | *State* awal diatur. |
| **3.2 Read (Node 2)** | Node 2 membaca V1 (State $I \to S$). | Node B kini memegang salinan *Shared*. |
| **3.3 Write (Node 3)** | Node 3 menulis V2 (State $I \to M$). Ini memicu RPC *Invalidate* ke Node 2. | Log Node 8023 (C) mencatat *Broadcasting INVAL*. |
| **3.4 Verifikasi Log** | *Script* memeriksa *logs* Node 8022. | **`✅ PASSED: MESI Invalidation BERHASIL. Node B mengubah state ke Invalid.`** (Membuktikan *coherence* terjamin). |

-----

## Pengujian Kinerja (Load Test Scenario) 

Fase ini mengukur *Throughput* dan *Latency* sistem di bawah beban tinggi (50+ pengguna). Kita menggunakan **Locust** untuk mensimulasikan *traffic* gabungan ke seluruh klaster.

### Struktur Load Test

File **`benchmarks/load_test_scenarios.py`**  mensimulasikan *user* yang secara bersamaan melakukan operasi di tiga klaster (Raft, Queue, Cache) dengan bobot berbeda:

  * **Bobot Tinggi (3):** Operasi Lock (Paling sensitif terhadap Latensi Raft).
  * **Bobot Sedang (2):** Operasi Queue (Menguji Consistent Hashing dan Redis I/O).
  * **Bobot Rendah (1):** Operasi Cache (Menguji Hit/Miss dan Invalidation).

### Eksekusi dan Akses Data

Pastikan semua *services* Docker berjalan (`docker compose ps`) dan *virtual environment* (`venv`)  aktif.

1.  **Jalankan Locust Generator:**
    Gunakan `python -m locust` untuk memulai generator beban.

    ```bash
    python -m locust -f benchmarks/load_test_scenarios.py
    ```

2.  **Akses Web Interface:**
    Buka *browser* dan navigasikan ke: `http://localhost:8089`

3.  **Konfigurasi dan Mulai Test:**
    Masukkan parameter berikut di UI Locust:

      * **Number of Users:** `50` (Simulasi beban tinggi)
      * **Spawn Rate:** `5` (Kecepatan *user* baru dibuat)
      * **Host:** `http://localhost`

4.  **Analisis Data:**
    Biarkan tes berjalan selama 5–10 menit. Data kinerja akan terekam dan dapat dianalisis di *tab* **Statistics** Locust.

## Video Demo

[https://youtu.be/hRF5W16az54]
