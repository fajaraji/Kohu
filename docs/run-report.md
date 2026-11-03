# Laporan kerja Kohu v2

Ditulis 3 November 2026 (sekitar 22:00 UTC, 05:00 WIB tanggal 4 November). Semua pekerjaan ada di branch `kohu-v2` repo `fajaraji/Kohu`, satu commit per tiket, sudah di-push. Branch `main` tidak disentuh. Daftar tiket dan statusnya ada di `TICKETS.md`.

Catatan branch: instruksi sistem sesi ini menyebut branch `claude/sweet-meitner-b96sp1`, tetapi tugas dari kamu jelas meminta `kohu-v2`. Saya hanya push ke `kohu-v2`.

## Ringkasan singkat

Semua tiket selesai: U1, U2, D1, L1, A1 sampai A7, B1 sampai B8, C1 sampai C5. A7 (SAM di grafik dan tabel PDF) sebenarnya opsional karena SAM tidak gagal di elemen UI setelah diberi box, tapi tetap dikerjakan karena waktunya cukup. Tidak ada yang dipotong dari urutan potong.

Kunci Meta mulai bisa dipakai setelah kamu memasangnya sebagai network secret. Sebelum itu host `api.meta.ai` ditolak oleh proxy. Sejak tiket U1 semua jalur model dijalankan ke API asli.

## Yang berjalan dan sudah diverifikasi dengan API Meta asli

- Muse Voice Transcribe 1.0 mentranskrip narasi video (turn dengan `startMs` dan `endMs`, selisih sekitar 0,2 detik dari waktu asli).
- Video lewat Files API ke Muse Spark 1.3 dalam mode background dengan polling. Hasilnya 9 langkah untuk 9 aksi, selisih waktu mulai median 0,22 detik, alasan yang diucapkan ikut terambil.
- SAM 3.1 di frame video. Prompt frasa sering gagal di elemen UI (3 dari 5 tidak ketemu), jadi Spark memberi box lalu SAM memperhalus dengan box prompt. Hasil akhir 9 dari 9 tanda tepat di kontrol yang benar (IoU median 0,93).
- SAM 3.1 di halaman PDF menemukan grafik dan semua tabel, lalu Spark membaca potongannya. Grafik terbaca 10 dari 10 nilai benar.
- Muse Spark membaca halaman hasil scan dan halaman grafik (B2).
- Agen tanya jawab dengan tool calling dan `previous_response_id`, jawaban akhir dengan JSON schema, dicek di server (B4, B5).
- Deteksi konflik dengan Spark (279 sampai 280 pasangan dinilai, 4 ditandai), keputusan Steward, dan jawaban berubah setelah keputusan (B6, B7).
- Unggah video baru dari UI diproses live sampai jadi langkah dengan tanda SAM (dipakai di video demo).
- Eval 20 pertanyaan dijalankan live dua kali.

## Hasil eval (detail di `docs/eval-result.md`)

- Pertanyaan: run pertama 18 dari 20. Dua yang gagal (q07, q20) karena cek saya salah, bukan jawabannya: jawaban memberi nilai persis 4.9787 dan cek hanya menerima 4.98 atau 4.979. Cek diperbaiki, alasannya dicatat di `eval/questions.json`, lalu eval diulang. Run kedua 19 dari 20. q01 gagal karena jawabannya tidak memuat kata "check stock" walau isinya benar. Tetap dihitung gagal.
- Uji kebocoran: 0 gagal dari 74 cek untuk semua peran, semua tool dan semua route.
- Konflik: 2 dari 3 konflik yang ditanam tertangkap. Yang lolos adalah batas belanja $3.000 di deck melawan $5.000 di handbook, karena juri Spark menganggap batas di deck hanya untuk satu tim. 0 dari 3 pasangan kontrol ditandai. Ada satu tanda tambahan di dalam handbook PostHog sendiri (dua halaman menjelaskan dana sponsor open source secara berbeda).
- Penting: aturan deteksi, aturan penandaan SAM dan padding crop disetel di korpus dan klip yang sama. Ini bukan hasil uji yang terpisah.

## Yang UNVERIFIED atau gagal

- Decode mask SAM: paket resmi Meta `meta-sam-parser` ada di PyPI dan sudah masuk `api/requirements.txt`, tapi pemasangannya di sandbox ini ditolak oleh pemeriksa izin sandbox. Jadi semua tanda di sini digambar dari box SAM, bukan mask. Kode decode mask belum pernah jalan. Image Docker akan memasangnya, tapi itu juga belum diuji.
- Docker: `Dockerfile` dan `docker-compose.yml` sudah ditulis tapi image tidak bisa di-build di sini (Docker Hub kena rate limit, mirror Debian diblokir). Bagian lain dari alur sudah dicek dengan clone baru plus `./seed.sh` tanpa kunci, dan berhasil (75 chunk, 4 konflik dari cache, jawaban extractive berlabel degraded, Employee dapat 403 untuk XLSX).
- Deploy ke Cloudflare: tidak dilakukan, sesuai instruksi. Kredensial Cloudflare dan `DATABASE_URL` milik Montrack tidak pernah dipakai. Setiap perintah memakai database lokal, dan kode sekarang menolak host database non-lokal kecuali `KOHU_ALLOW_REMOTE_DB=1`.
- Waktu jawab 15 sampai 40 detik per pertanyaan (3 sampai 5 panggilan model). UI sekarang menampilkan langkah agen secara live selama menunggu.
- Narasi video demo memakai suara sintetis Kokoro TTS dan diberi label. Silakan rekam ulang dengan suara manusia kalau mau.
- Slide ditampilkan sebagai teks hasil ekstraksi, bukan gambar slide.

## Biaya Meta

Total tercatat sekitar 4,04 USD dari 756 panggilan (jauh di bawah batas 30 USD). Rinciannya kira-kira: penilaian konflik 1,83 USD, langkah agen 1,05 USD, jawaban akhir 0,65 USD, box Spark untuk SAM 0,17 USD, sisanya spike, baca halaman, video, SAM dan transkripsi. Total 1,39 juta token input, 0,51 juta token output, sekitar 100 detik audio, 53 gambar SAM. Log ada di `logs/meta-usage.jsonl` (tidak di-commit, hanya ada di container ini). Semua hasil model di-cache di `corpus/spark-cache/`, jadi seed ulang tidak memanggil model lagi.

## Cara menjalankan

```bash
pip install -r api/requirements.txt
```

```bash
cp .env.example .env
```

Isi `META_API_KEY` dan `KOHU_SESSION_SECRET` di `.env`, lalu:

```bash
./seed.sh
```

```bash
uvicorn api.app:app --port 8000
```

Buka http://localhost:8000. Sebelum rekam atau demo, kembalikan keadaan awal (konflik dibuka lagi, unggahan dihapus):

```bash
python video/reset_demo.py
```

Tes:

```bash
python -m pytest -q tests
```

Eval (memanggil API untuk 20 pertanyaan, sekitar 0,4 USD):

```bash
python eval/run_eval.py
```

## Yang perlu kamu lakukan

1. Tonton `video/kohu-demo.mp4` (180 detik). Semua bagian produk adalah rekaman asli aplikasi, waktu tunggu dipercepat dan diberi label. Naskah dan caption ada di `video/script.md` dan `video/captions.srt`. Ganti narasi kalau perlu, lalu unggah sendiri.
2. Coba aplikasinya sendiri dan pastikan alurnya cocok dengan video.
3. Deploy lewat Cloudflare dari mesin kamu: build image dari `Dockerfile`, siapkan Postgres 16 dengan `pg_trgm`, isi `DATABASE_URL`, `KOHU_ALLOW_REMOTE_DB=1`, `KOHU_SESSION_SECRET` (acak dan panjang) dan `META_API_KEY`, jalankan sekali dengan `KOHU_SEED_ON_START=1`. Kalau image gagal build, kabari saya dengan pesan errornya.
4. Opsional: `pip install meta-sam-parser` di mesin kamu, lalu `python api/video.py remark refund-process-video` untuk menggambar mask asli SAM (biaya kecil).
5. Merge `kohu-v2` ke `main` di `fajaraji/Kohu`.
6. Kalau tim ingin repo `alfianhid/Kohu` yang dipakai, buka pull request dari `fajaraji/Kohu` ke `alfianhid/Kohu`.
7. Pastikan repo yang dikirim bersifat public.
8. Draf teks submission ada di `docs/submission.md`. Representative, yaitu Alfian, harus submit sebelum Kamis 5 November 09:00 WIB, dengan semua anggota tim tercantum dan link repo yang benar (plus link video dan URL hosting).
