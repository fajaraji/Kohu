# Laporan kerja Kohu v2

Diperbarui 4 November 2026, sekitar 11:00 UTC (18:00 WIB). Semua pekerjaan ada di branch `kohu-v2` repo `fajaraji/Kohu`, satu commit per tiket, sudah di-push. Branch `main` tidak disentuh. Daftar tiket ada di `TICKETS.md`.

Catatan branch: instruksi sistem sesi ini menyebut branch `claude/sweet-meitner-b96sp1`, tetapi tugas dari kamu meminta `kohu-v2`. Saya hanya push ke `kohu-v2`.

## Ringkasan

Putaran 1 (3 November, sekitar 2,5 jam) menyelesaikan semua tiket di rencana: U1, U2, D1, L1, A1 sampai A7, B1 sampai B8, C1 sampai C5. Putaran 2 (4 November) menutup celah yang ternyata terlewat:

| Tiket | Hasil |
|---|---|
| G1 Mode demo publik | Selesai. Dengan `KOHU_PUBLIC_DEMO=1`, keputusan Steward hanya berlaku untuk browser pengunjung itu sendiri (ada tombol untuk membatalkan keputusan sendiri). Upload dan edit video dimatikan. Pertanyaan dibatasi per pengunjung, per IP dan total. Pemakaian Meta juga dicatat di database, jadi batas biaya tetap berlaku setelah restart |
| G2 Desain ulang UI | Selesai. Referensinya GOV.UK Design System, catatan bernomor ala Gwern/Tufte, dan dokumentasi Stripe (lihat `docs/design.md`). Tanpa neon, glow, kartu bertumpuk, chip, atau emoji. Sitasi berupa nomor kecil dengan daftar sumber di bawah jawaban. Sudah dicek di lebar 1366 px dan 390 px |
| G3 Decode mask SAM | Terblokir. Pemasangan `meta-sam-parser` ditolak oleh pemeriksa izin sandbox. Algoritmanya hanya ada di kode referensi Meta, dan kode itu tidak saya salin karena itu sama saja mengakali penolakan tadi |
| G4 Docker | Selesai. Image (sekarang berbasis `ubuntu:24.04`) di-build dan dijalankan penuh dengan Postgres 16. Ini menemukan bug nyata: aplikasi mati kalau Postgres belum siap. Sekarang entrypoint menunggu sampai sekitar 60 detik. `meta-sam-parser` tidak ikut dalam build uji karena alasan G3 |
| G5 Tes pipeline model | Selesai. Pipeline video, semua jalur penandaan SAM dan region PDF dites dengan klien palsu, tanpa jaringan |
| G6 Eval lebih kuat | Selesai. Ada klip kedua yang direkam setelah aturan disetel (uji held-out), dan pertanyaan dijalankan 3 kali |
| G7 Review keamanan | Selesai. Header keamanan (no-referrer, CSP, anti-frame), trace hanya bisa dibaca penanyanya, header IP Cloudflare hanya dipercaya kalau diaktifkan, mode publik wajib secret minimal 16 karakter, upload dicek dengan ffprobe, jendela sel dibatasi |
| G8 Gambar slide | Selesai. Slide dirender dengan LibreOffice saat build, lalu ditampilkan di panel sitasi |
| G9 Video dan dokumen | Selesai. Video direkam ulang dengan UI baru dan upload yang benar-benar diproses live (128 detik, dipercepat dan diberi label). Kartu Hyperframes disamakan gayanya dengan aplikasi |

Putaran 3 (4 November sore) mengikuti masukan setelah putaran 2:

| Tiket | Hasil |
|---|---|
| H1 Tampilan gelap | Selesai. Mengikuti screenshot referensi: latar gelap dengan satu cahaya hangat, navigasi berbentuk pil, badge kecil, judul besar dengan satu frasa bergradasi, dan command bar untuk bertanya (pilih dengan panah, `/` untuk fokus). Tanpa neon dan tanpa emoji |
| H2 Pipeline deploy | Selesai, tapi belum pernah deploy. GitHub Actions menjalankan tes di setiap push dan pull request, lalu menjalankan `wrangler deploy` ke Cloudflare Containers setiap ada push ke `main`. Tes di CI sudah hijau untuk `kohu-v2`. Deploy baru jalan setelah kamu mengisi secret `CLOUDFLARE_API_TOKEN` dan `CLOUDFLARE_ACCOUNT_ID` di repo (lihat `docs/deploy.md`) |
| H3 Video v3 | Selesai. Seluruh video sekarang satu komposisi Hyperframes bergaya UI Kohu. Ada pembuka dan penutup beranimasi, rekaman di dalam bingkai aplikasi yang zoom ke bagian penting, label dan caption beranimasi, serta transisi pendek tanpa kartu layar penuh. Ada musik latar buatan sendiri yang mengecil saat narasi bicara. Panjangnya sekarang sekitar 2 menit 9 detik (sebelumnya 3 menit) |

Commit ditulis dalam bahasa Inggris. Hanya laporan ini yang berbahasa Indonesia.

Total tes: 100, semuanya lulus. Clone baru plus `./seed.sh` tanpa kunci juga berhasil (75 chunk, 4 konflik dari cache, 0 penilaian yang terlewat).

## Yang sudah diverifikasi dengan API Meta asli

- **Transkripsi:** Muse Voice Transcribe 1.0 mengembalikan turn bertimestamp.
- **Video jadi langkah:** Muse Spark 1.3 dengan video, Files API, mode background, dan polling.
- **SAM 3.1:** menandai kontrol di frame video lewat box prompt yang diperhalus dari box Spark. SAM juga menemukan grafik dan tabel di halaman PDF.
- **Muse Spark lainnya:**
  - membaca halaman hasil scan dan halaman grafik;
  - menjalankan agen dengan tool calling;
  - menulis jawaban akhir dengan JSON schema;
  - menilai konflik antar sumber.
- **Keputusan Steward mengubah jawaban:** jawaban Employee berubah setelah Steward memutuskan.
- **Upload video dari UI:** diproses live sampai jadi langkah dengan tanda SAM.

## Hasil eval (detail di `docs/eval-result.md`)

- **Pertanyaan:**
  - Tiga run terakhir: 19, 19 dan 20 dari 20.
  - Satu-satunya yang tidak stabil adalah q01 (lulus 1 dari 3). Saat gagal, jawabannya menjelaskan cek stok tanpa memakai kata "check stock" yang dicari ceknya.
  - Run pertama tanggal 3 November mendapat 18 karena dua cek saya salah. Ceknya sudah diperbaiki dan alasannya dicatat.
- **Kebocoran:** 0 dari 74 cek.
- **Konflik:** 2 dari 3 konflik tanaman tertangkap, 0 dari 3 kontrol ditandai. Batas belanja $3.000 lawan $5.000 lolos karena juri menganggap batas di deck hanya untuk satu tim.
- **Klip yang dipakai untuk menyetel:** 9 dari 9 langkah ditemukan, selisih waktu median 0,22 detik, dan 9 dari 9 tanda SAM tepat.
- **Klip held-out (direkam setelah penyetelan):** 4 dari 5 langkah ditemukan dan ditandai dengan benar. Langkah "klik Check stock" digabung dengan langkah lain dan ditandai di tombol yang salah. Satu langkah tambahan muncul tanpa elemen di layar, dan langkah itu dengan benar tidak ditandai.
- **Grafik:** 10 dari 10 nilai terbaca benar.

## Yang masih UNVERIFIED atau gagal

- **Mask SAM:** belum pernah di-decode (lihat G3). Semua tanda masih berupa kotak SAM.
- **Deploy ke Cloudflare:** belum dilakukan, sesuai instruksi. Konfigurasinya hanya dicek dengan `wrangler deploy --dry-run`. Kredensial Cloudflare dan database Montrack tidak pernah dipakai.
- **Waktu jawab:** 11 sampai 37 detik, median sekitar 23 detik.
- **Narasi video:** suara sintetis (Kokoro TTS) dan diberi label.
- **Ukuran korpus:** kecil, jadi angka eval menunjukkan alurnya bekerja, bukan bukti untuk skala besar.

## Biaya Meta

Sekitar 6,00 USD tercatat sampai sekarang (termasuk rekaman ulang untuk video v3), jauh di bawah batas 30 USD. Hampir semua hasil model di-cache di `corpus/spark-cache/`, jadi seed ulang tidak memanggil model lagi.

## Cara menjalankan

```bash
pip install -r api/requirements.txt
```

```bash
./seed.sh
```

```bash
uvicorn api.app:app --port 8000
```

Sebelum demo, kembalikan keadaan awal:

```bash
python video/reset_demo.py
```

Tes:

```bash
python -m pytest -q tests
```

## Yang perlu kamu lakukan

1. **Izinkan atau pasang `meta-sam-parser`.** Kalau mau saya yang memasangnya di sini, izinkan perintah ini di pengaturan izin Claude Code: `pip install meta-sam-parser`. Atau pasang di mesinmu, lalu jalankan `python api/video.py remark refund-process-video` dan `python api/regions.py` untuk menggambar mask asli.
2. **Tonton `video/kohu-demo.mp4`** (sekitar 129 detik). Ganti narasinya dengan suara manusia kalau mau, lalu unggah sendiri.
3. **Siapkan deploy Cloudflare** (langkah lengkap di `docs/deploy.md`). Butuh paket Workers Paid karena Containers belum ada di paket gratis. Siapkan Postgres 16 dengan `pg_trgm` di luar Cloudflare, lalu:
   - isi secret repo GitHub `CLOUDFLARE_API_TOKEN` dan `CLOUDFLARE_ACCOUNT_ID`;
   - isi secret Worker dengan `wrangler secret put`: `DATABASE_URL`, `KOHU_SESSION_SECRET` (acak, minimal 16 karakter), `META_API_KEY`;
   - push ke `main`, maka GitHub Actions menjalankan tes lalu deploy.

   Alamatnya nanti `https://kohu.<subdomain-akunmu>.workers.dev`. Subdomain itu dipilih sekali di dashboard Cloudflare (bagian Workers). Domain sendiri bisa ditambahkan belakangan. Isi database sekali dengan `./seed.sh` dari mesinmu (perintahnya ada di `docs/deploy.md`).
4. **Merge `kohu-v2` ke `main`.**
5. **Buka pull request ke `alfianhid/Kohu`** kalau tim ingin repo itu yang dipakai.
6. **Pastikan repo public.**
7. **Submit.** Representative (Alfian) submit sebelum Kamis 5 November 09:00 WIB, dengan semua anggota tim, link repo yang benar, link video, dan URL hosting. Draf teksnya ada di `docs/submission.md`.
