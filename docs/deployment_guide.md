# Panduan Deployment dan Troubleshooting

## 1\. Pendahuluan

Proses *deployment* sistem sinkronisasi terdistribusi (DSS) yang terdiri dari 11 layanan mikro (Raft, Consistent Hashing, MESI) menggunakan Docker Compose.

-----

## 2\. Prasyarat Sistem

| Persyaratan | Detail | Verifikasi |
| :--- | :--- | :--- |
| **Docker Engine** | Docker Desktop harus terinstal dan berjalan. | `docker --version` |
| **Docker Compose** | Docker Compose V2 harus terinstal. | `docker compose version` |
| **Python Libraries** | Pustaka wajib (`redis`, `aiohttp`, `locust`) harus diinstal dalam *virtual environment*. | `pip install -r requirements.txt` |
| **Resource** | Minimal 4 GB RAM/2 vCPU dialokasikan untuk Docker Engine. | Cek pengaturan Docker Desktop Anda. |

-----

## 3\. Proses Deployment dan Instalasi

### 3.1. Penyiapan Environment Lokal dan Dependensi

Langkah-langkah ini menyiapkan *virtual environment* (`venv`) dan menginstal *library* yang diperlukan (`locust`, dll.).

```bash
# 1. Buat dan Aktifkan Virtual Environment
python -m venv venv
venv\Scripts\activate

# 2. Instal Semua Dependensi Python
pip install -r requirements.txt
```

### 3.2. Konfigurasi Jaringan dan Peluncuran Klaster

1.  **Stop dan Bersihkan Container Lama (Opsional):**

    ```bash
    docker compose -f docker/docker-compose.yml down
    ```

2.  **Konfigurasi Environment:** Salin `.env.example` dan paste isinya ke file `.env` baru di *root directory* dengan daftar *peer* jaringan (RAFT\_PEERS, QUEUE\_NODES, CACHE\_PEERS) menggunakan format JSON yang benar.

3.  **Build dan Launching 11 Services:**
    Perintah ini meluncurkan sistem, menggunakan *explicit flag* `--env-file .env` untuk membaca konfigurasi dan `--build` untuk mengkompilasi kode Python.

    ```bash
    docker compose -f docker/docker-compose.yml --env-file .env up --build -d
    ```

4.  **Verifikasi Status Layanan:**
    Pastikan semua 11 *services* (9 node aplikasi, Redis, Prometheus, Grafana) berstatus **`Up`**.

    ```bash
    docker compose -f docker/docker-compose.yml ps
    ```

-----

## 4\. Akses, Monitoring, dan Pengujian Kinerja

### 4.1. Akses Monitoring dan API Utama

| Service | Tujuan | URL Akses | Default Credentials |
| :--- | :--- | :--- | :--- |
| **Grafana** | Visualisasi Metrik | `http://localhost:3000` | admin / admin |
| **Prometheus** | Query Metrik Targets | `http://localhost:9090` | N/A |
| **Lock Manager** | Raft API | `http://localhost:8001` (atau 8002/8003) | N/A |

### 4.2. Menjalankan Load Testing (Locust)

Gunakan *virtual environment* yang sama untuk menjalankan *load generator* Locust.

1.  **Eksekusi Locust:**

    ```bash
    python -m locust -f benchmarks/load_test_scenarios.py
    ```

2.  **Akses UI:** Buka browser ke **`http://localhost:8089`**. Masukkan `http://localhost` sebagai Host dan mulai pengujian.

-----

## 5\. Panduan Troubleshooting Khusus

| Error/Gejala | Kemungkinan Penyebab | Tindakan Korektif |
| :--- | :--- | :--- |
| **`JSONDecodeError` / Node Crash** | File `.env` kosong atau format JSON salah (misalnya, di `RAFT_PEERS`). | **Perbaiki `.env`** dan **`docker compose down`** lalu **`up --build -d`** ulang. |
| **`Connection refused`** | *Event loop* Python *crash* pasca-*startup* (kesalahan *race condition* Raft) atau *port binding* macet. | Cek `docker logs [container]`. Pastikan *locking* diterapkan di *logic* Raft. Lakukan *restart* total Docker Desktop. |
| **`parent snapshot does not exist`** | Docker Build Cache rusak. | Ulangi *deployment* dengan: `docker compose -f docker/docker-compose.yml up --build --no-cache -d`. |
| **Raft Stuck / Split-Vote** | Klaster tidak dapat mencapai mayoritas karena 2 node *candidate* bersaing. | Cek *logs* Node 1, 2, dan 3. Hentikan salah satu node yang bersaing (`docker stop`) dan *start* kembali untuk memecahkan *tie*. |

-----

## 6\. Cleanup (Penghentian Sistem)

Untuk menghentikan dan menghapus semua *container* serta jaringan yang dibuat oleh proyek:

```bash
docker compose -f docker/docker-compose.yml down
```