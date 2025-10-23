# Dokumentasi Arsitektur Sistem Sinkronisasi Terdistribusi (DSS)

## 1. Pendahuluan

Arsitektur *Distributed Sync System* (DSS) yang dikembangkan untuk menyimulasikan skenario sistem terdistribusi dunia nyata. DSS terdiri dari sebelas (11) layanan mikro yang terorkestrasi, dirancang untuk memastikan **konsistensi data** dan **toleransi kegagalan** melalui penerapan algoritma konsensus dan koherensi terdepan.

## 2. Struktur Arsitektur Tingkat Tinggi

DSS mengadopsi arsitektur *microservices* terdistribusi, dibagi menjadi tiga klaster fungsional utama (Lock, Queue, Cache) yang berinteraksi melalui *message passing* berbasis HTTP. Klaster ini bergantung pada satu *Data Store* sentral (Redis) dan Lapisan *Observability* (Prometheus & Grafana) untuk pemantauan *state* dan kinerja.



### 2.1. Komponen Layanan (Total 11 Services)

| Lapisan Fungsional | Layanan (Service Name) | Jumlah Node | Algoritma Kunci |
| :--- | :--- | :--- | :--- |
| **I. Consensus & Lock** | `node_lock_1`, `node_lock_2`, `node_lock_3` | 3 | **Raft Consensus** |
| **II. Messaging & Queue** | `node_queue_1`, `node_queue_2`, `node_queue_3` | 3 | **Consistent Hashing** |
| **III. Data Coherence** | `node_cache_1`, `node_cache_2`, `node_cache_3` | 3 | **MESI Protocol** (LRU) |
| **IV. Infrastructure** | `redis_state` | 1 | *Key-Value Store* (Persistence/Memory Utama) |
| **V. Observability** | `prometheus`, `grafana` | 2 | *Metrics Aggregation* & *Visualization* |

## 3. Desain Fungsional dan Mekanisme Sinkronisasi

### 3.1. Distributed Lock Manager (DLM)

DLM adalah komponen yang paling sensitif terhadap konsistensi.

* **Mekanisme Inti:** Setiap permintaan *lock* (*acquire* atau *release*) harus diarahkan ke **Raft Leader** (salah satu dari 3 *node\_lock*). Leader kemudian mencatat permintaan tersebut ke dalam *Raft Log* dan mereplikasikannya ke *Follower*. *Lock* hanya diberikan setelah *command* di-*commit* ke mayoritas node ($N/2 + 1$).
* **Toleransi Kegagalan:** Sistem secara otomatis melakukan **Leader Election** ketika Leader saat ini gagal (simulasi *network partition*). Log *lock state* yang direplikasi memastikan konsistensi *Linearizability*.
* **Deadlock Detection:** Sebuah *asynchronous task* (`deadlock_monitor`) berjalan di Leader, secara berkala memeriksa *Lock Table*. Jika *lock* melewati *expiry time* (timeout), *monitor* secara otomatis mengirim *command* `RELEASE` ke Raft Log untuk dilepaskan.

### 3.2. Distributed Queue System (DQS)

DQS dirancang untuk skalabilitas horizontal dan jaminan pengiriman.

* **Routing:** Menggunakan **Consistent Hashing** untuk memetakan *topic* ke *Queue Node* yang spesifik, memastikan *load balancing* yang efisien dan meminimalkan *re-sharding*.
* **Persistence & Delivery:** Pesan disimpan dalam **Redis List**. *At-Least-Once Delivery* dijamin melalui mekanisme *Pending Acknowledgement Queue*. Pesan yang dikonsumsi dipindahkan dari *antrian utama* ke *antrian pending* (atomik menggunakan Redis RPOPLPUSH).
* **Recovery:** Jika *Consumer* gagal mengirim ACK dalam periode *timeout* (30 detik), *Redelivery Monitor* (sebuah *async task*) secara otomatis mengembalikan pesan tersebut ke antrian utama untuk dikirim ulang.

### 3.3. Distributed Cache Coherence (DCC)

DCC memastikan *Cache Node* tidak menyimpan data basi saat terjadi *Write* pada *node* lain.

* **Protokol MESI:** Setiap *Cache Line* memiliki *state* (`M, E, S, I`). Operasi *Write* pada *Cache Node* memicu **Invalidation Broadcast** ke semua *peer*.
* **Writeback Safety:** Jika suatu *Cache Node* menerima sinyal *Invalidate* untuk data yang dimilikinya dalam status **Modified (M)**, *node* tersebut harus melakukan **Write Back** data terbaru ke Redis (Memori Utama) sebelum mengubah *state*nya menjadi Invalid (`I`).
* **LRU Policy:** Kebijakan *Least Recently Used* mengatur *eviction* ketika *cache* penuh, memastikan *Write Back* data yang kotor jika perlu, sebelum diganti.

## 4. Lapisan Observability dan Kinerja

Sistem DSS dirancang untuk *Performance Monitoring* yang ketat, yang esensial untuk menganalisis *overhead* dari protokol konsensus.

* **Metrics Exposition:** Semua 9 *Application Node* (Lock, Queue, Cache) mengekspos metrik kinerja internal (seperti `raft_is_leader`, `cache_hits_total`, `latency`) melalui *endpoint* `/metrics` dengan format **Prometheus Exposition**.
* **Prometheus:** Mengumpulkan metrik secara periodik dari setiap node.
* **Grafana:** Menyediakan visualisasi *real-time* yang digunakan untuk *benchmarking*, menganalisis *throughput*, latensi 99%ile, dan stabilitas Raft Leader di bawah beban.