#include "mineralogy.h"

#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstdint>
#include <cmath>
#include <cstring>
#include <cstdio>
#include <omp.h>

static const uint32_t PTIL_MAGIC = 0x4C495450U;
static const uint32_t HMAP_MAGIC = 0x50414D48U;
static const uint32_t CONTRACT_VERSION = 1U;

struct alignas(64) TileBinaryHeader {
    uint32_t magic;
    uint32_t version;
    uint32_t body;
    uint32_t domain;
    uint32_t num_octaves;
    uint32_t num_channels;
    uint32_t base_height;
    uint32_t base_width;
    double base_resolution_m;
    double center_lat_deg;
    double center_lon_deg;
    float nodata_value;
    float gravity_ms2;
    float surface_pressure_pa;
    float radiation_msv_yr;
    unsigned char reserved[40];
};
// pad to 128 via alignment not guaranteed; we rely on file layout 128 bytes.
// Ensure struct size is 128 by static assert.
static_assert(sizeof(TileBinaryHeader) == 128, "header must be 128 bytes");

static size_t header_size() { return 128; }

extern "C" int32_t run_module(const char* earth_ptile_path,
                              const char* target_ptile_path,
                              const char* out_hmap_path,
                              const char* out_breakdown_json_path) {
    // ---- open & mmap earth ----
    int efd = open(earth_ptile_path, O_RDONLY);
    if (efd < 0) return -1;
    struct stat est; 
    if (fstat(efd, &est) != 0) { close(efd); return -2; }
    void* emap = mmap(nullptr, est.st_size, PROT_READ, MAP_PRIVATE, efd, 0);
    close(efd);
    if (emap == MAP_FAILED) return -3;

    // ---- open & mmap target ----
    int tfd = open(target_ptile_path, O_RDONLY);
    if (tfd < 0) { munmap(emap, est.st_size); return -4; }
    struct stat tst;
    if (fstat(tfd, &tst) != 0) { close(tfd); munmap(emap, est.st_size); return -5; }
    void* tmap = mmap(nullptr, tst.st_size, PROT_READ, MAP_PRIVATE, tfd, 0);
    close(tfd);
    if (tmap == MAP_FAILED) { munmap(emap, est.st_size); return -6; }

    TileBinaryHeader* eh = (TileBinaryHeader*)emap;
    TileBinaryHeader* th = (TileBinaryHeader*)tmap;
    if (eh->magic != PTIL_MAGIC || th->magic != PTIL_MAGIC) { 
        munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -7; }
    if (eh->version != CONTRACT_VERSION || th->version != CONTRACT_VERSION) {
        munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -8; }

    uint32_t num_octaves = eh->num_octaves;
    if (th->num_octaves < num_octaves) num_octaves = th->num_octaves;
    uint32_t base_height = eh->base_height;
    uint32_t base_width = eh->base_width;
    uint32_t nc_e = eh->num_channels;
    uint32_t nc_t = th->num_channels;
    uint32_t nc = nc_e < nc_t ? nc_e : nc_t;
    float nodata = eh->nodata_value;

    // compute output size
    size_t out_size = 128;
    for (uint32_t k = 0; k < num_octaves; k++) {
        uint32_t Hk = base_height >> k;
        uint32_t Wk = base_width >> k;
        out_size += 2 * Hk * Wk * sizeof(float);
    }

    // create output file
    int ofd = open(out_hmap_path, O_RDWR | O_CREAT | O_TRUNC, 0644);
    if (ofd < 0) { munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -9; }
    if (ftruncate(ofd, out_size) != 0) { close(ofd); munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -10; }
    void* omap = mmap(nullptr, out_size, PROT_READ | PROT_WRITE, MAP_SHARED, ofd, 0);
    close(ofd);
    if (omap == MAP_FAILED) { munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -11; }

    TileBinaryHeader* oh = (TileBinaryHeader*)omap;
    *oh = *eh;
    oh->magic = HMAP_MAGIC;
    oh->num_channels = 2;

    const float* ebase = (const float*)((const char*)emap + 128);
    const float* tbase = (const float*)((const char*)tmap + 128);
    float* obase = (float*)((char*)omap + 128);

    // per-octave mean sim for scale invariance
    double octave_means[32];
    for (uint32_t k = 0; k < num_octaves; k++) octave_means[k] = 0.0;

    for (uint32_t k = 0; k < num_octaves; k++) {
        uint32_t Hk = base_height >> k;
        uint32_t Wk = base_width >> k;
        // offsets in floats
        // earth: cumulative over previous octaves with nc_e channels
        size_t eo = 0, to = 0;
        for (uint32_t kk = 0; kk < k; kk++) {
            uint32_t Hkk = base_height >> kk;
            uint32_t Wkk = base_width >> kk;
            eo += (size_t)nc_e * Hkk * Wkk;
            to += (size_t)nc_t * Hkk * Wkk;
        }
        size_t oo = 0;
        for (uint32_t kk = 0; kk < k; kk++) {
            uint32_t Hkk = base_height >> kk;
            uint32_t Wkk = base_width >> kk;
            oo += 2 * Hkk * Wkk;
        }

        double sum_sim = 0.0;
        long count = 0;

        #pragma omp parallel for collapse(2) reduction(+:sum_sim,count)
        for (int i = 0; i < (int)Hk; i++) {
            for (int j = 0; j < (int)Wk; j++) {
                double dot = 0.0, ne = 0.0, nt = 0.0;
                int nodata = 0;
                // first pass
                for (uint32_t c = 0; c < nc; c++) {
                    float ev = ebase[eo + ((size_t)c * Hk + i) * Wk + j];
                    float tv = tbase[to + ((size_t)c * Hk + i) * Wk + j];
                    if (ev == nodata || tv == nodata) { nodata = 1; break; }
                    dot += (double)ev * (double)tv;
                    ne += (double)ev * (double)ev;
                    nt += (double)tv * (double)tv;
                }
                float sim = 0.0f, conf = 0.0f;
                if (!nodata && ne > 0.0 && nt > 0.0) {
                    double cos = dot / (std::sqrt(ne) * std::sqrt(nt));
                    sim = (float)((cos + 1.0) / 2.0);
                    if (sim < 0.0f) sim = 0.0f;
                    if (sim > 1.0f) sim = 1.0f;
                    double relsum = 0.0;
                    for (uint32_t c = 0; c < nc; c++) {
                        float ev = ebase[eo + ((size_t)c * Hk + i) * Wk + j];
                        float tv = tbase[to + ((size_t)c * Hk + i) * Wk + j];
                        double denom = (double)std::fabs(ev) + (double)std::fabs(tv) + 1e-6;
                        relsum += (double)std::fabs(ev - tv) / denom;
                    }
                    double rel = relsum / (double)nc;
                    conf = (float)(1.0 / (1.0 + rel));
                    if (conf < 0.0f) conf = 0.0f;
                    if (conf > 1.0f) conf = 1.0f;
                }
                obase[oo + (0 * Hk + i) * Wk + j] = sim;
                obase[oo + (1 * Hk + i) * Wk + j] = conf;
                sum_sim += sim;
                count++;
            }
        }
        if (count > 0) octave_means[k] = sum_sim / (double)count;
    }

    // scale invariance index
    double mean = 0.0;
    for (uint32_t k = 0; k < num_octaves; k++) mean += octave_means[k];
    mean /= num_octaves;
    double var = 0.0;
    for (uint32_t k = 0; k < num_octaves; k++) {
        double d = octave_means[k] - mean;
        var += d * d;
    }
    var /= (num_octaves > 1 ? num_octaves : 1);
    double si = 1.0 - std::sqrt(var);
    if (si < 0.0) si = 0.0;
    if (si > 1.0) si = 1.0;

    // write breakdown json (minimal but valid)
    if (out_breakdown_json_path) {
        FILE* f = fopen(out_breakdown_json_path, "w");
        if (f) {
            fprintf(f, "{\n");
            fprintf(f, "  \"scale_invariance_index\": %.6f,\n", si);
            fprintf(f, "  \"channel_residuals\": {},\n");
            fprintf(f, "  \"physical_breakdown_flags\": [\n");
            fprintf(f, "    {\"flag\": \"GRAVITY_SCALING\", \"gravity_scaling_factor\": %.6f},\n", (double)th->gravity_ms2 / (double)eh->gravity_ms2);
            fprintf(f, "    {\"flag\": \"ATMOSPHERE_GAP\", \"atmospheric_pressure_gap_pa\": %.6f},\n", (double)std::fabs(eh->surface_pressure_pa - th->surface_pressure_pa));
            fprintf(f, "    {\"flag\": \"RADIATION_DELTA\", \"radiation_delta_msv_yr\": %.6f}\n", (double)std::fabs(eh->radiation_msv_yr - th->radiation_msv_yr));
            fprintf(f, "  ]\n");
            fprintf(f, "}\n");
            fclose(f);
        }
    }

    msync(omap, out_size, MS_SYNC);
    munmap(omap, out_size);
    munmap(emap, est.st_size);
    munmap(tmap, tst.st_size);
    return 0;
}
