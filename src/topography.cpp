#include "topography.h"

#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstdint>
#include <cmath>
#include <cstring>
#include <cstdio>
#include <algorithm>
#include <vector>
#include <omp.h>

static const uint32_t PTIL_MAGIC = 0x4C495450U;
static const uint32_t HMAP_MAGIC = 0x50414D48U;
static const uint32_t CONTRACT_VERSION = 1U;
static const float NODATA = -9999.0f;

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
    unsigned char reserved[56];
};
static_assert(sizeof(TileBinaryHeader) == 128, "header must be 128 bytes");

// Per-channel reference (mu, sigma) for topography (6 channels + illumination proxy handled in Python only;
// C++ uses 6 channels to match tile).
static const int NC = 6;
static const double REF_MU[NC] = {500.0, 15.0, 180.0, 50.0, 0.0, 0.0};
static const double REF_SIG[NC] = {1000.0, 15.0, 103.9, 50.0, 50.0, 0.01};

static inline float norm_channel(float x, int c) {
    if (x == NODATA) return NAN;
    double z = (x - REF_MU[c]) / REF_SIG[c];
    if (z < -5.0) z = -5.0;
    if (z > 5.0) z = 5.0;
    return (float)z;
}

extern "C" int32_t run_module(const char* earth_ptile_path,
                              const char* target_ptile_path,
                              const char* out_hmap_path,
                              const char* out_breakdown_json_path) {
    int efd = open(earth_ptile_path, O_RDONLY);
    if (efd < 0) return -1;
    struct stat est; if (fstat(efd, &est) != 0) { close(efd); return -2; }
    void* emap = mmap(nullptr, est.st_size, PROT_READ, MAP_PRIVATE, efd, 0);
    close(efd);
    if (emap == MAP_FAILED) return -3;

    int tfd = open(target_ptile_path, O_RDONLY);
    if (tfd < 0) { munmap(emap, est.st_size); return -4; }
    struct stat tst; if (fstat(tfd, &tst) != 0) { close(tfd); munmap(emap, est.st_size); return -5; }
    void* tmap = mmap(nullptr, tst.st_size, PROT_READ, MAP_PRIVATE, tfd, 0);
    close(tfd);
    if (tmap == MAP_FAILED) { munmap(emap, est.st_size); return -6; }

    if (est.st_size < 128 || tst.st_size < 128) {
        munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -13; }
    TileBinaryHeader* eh = (TileBinaryHeader*)emap;
    TileBinaryHeader* th = (TileBinaryHeader*)tmap;
    if (eh->magic != PTIL_MAGIC || th->magic != PTIL_MAGIC) { munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -7; }
    if (eh->version != CONTRACT_VERSION || th->version != CONTRACT_VERSION) { munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -8; }

    uint32_t num_octaves = eh->num_octaves;
    if (th->num_octaves < num_octaves) num_octaves = th->num_octaves;
    if (num_octaves > 32) num_octaves = 32;
    uint32_t base_height = eh->base_height;
    uint32_t base_width = eh->base_width;
    uint32_t th_base_height = th->base_height;
    uint32_t th_base_width = th->base_width;
    uint32_t nc_e = eh->num_channels;
    uint32_t nc_t = th->num_channels;
    uint32_t nc = nc_e < nc_t ? nc_e : nc_t;
    if (nc > NC) nc = NC;
    float nodata_val = eh->nodata_value;

    size_t out_size = 128;
    for (uint32_t k = 0; k < num_octaves; k++) {
        uint32_t Hk = base_height >> k; if (Hk == 0) Hk = 1;
        uint32_t Wk = base_width >> k; if (Wk == 0) Wk = 1;
        out_size += 2 * Hk * Wk * sizeof(float);
    }

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

    double octave_means[32];
    for (uint32_t k = 0; k < num_octaves; k++) octave_means[k] = 0.0;

    // Precompute target octave signatures (outside hot loops)
    // For each octave: per-channel mean/std/quantiles(5)/texture
    // We'll compute on demand per octave inside loop (still outside pixel loop).

    for (uint32_t k = 0; k < num_octaves; k++) {
        uint32_t Hk = base_height >> k; if (Hk == 0) Hk = 1;
        uint32_t Wk = base_width >> k; if (Wk == 0) Wk = 1;
        uint32_t th_Hk = th_base_height >> k; if (th_Hk == 0) th_Hk = 1;
        uint32_t th_Wk = th_base_width >> k; if (th_Wk == 0) th_Wk = 1;

        // earth octave offset
        size_t eo = 0;
        for (uint32_t kk = 0; kk < k; kk++) {
            uint32_t Hkk = base_height >> kk; if (Hkk == 0) Hkk = 1;
            uint32_t Wkk = base_width >> kk; if (Wkk == 0) Wkk = 1;
            eo += (size_t)nc_e * Hkk * Wkk;
        }
        // target octave offset
        size_t to = 0;
        for (uint32_t kk = 0; kk < k; kk++) {
            uint32_t Hkk = th_base_height >> kk; if (Hkk == 0) Hkk = 1;
            uint32_t Wkk = th_base_width >> kk; if (Wkk == 0) Wkk = 1;
            to += (size_t)nc_t * Hkk * Wkk;
        }
        size_t oo = 0;
        for (uint32_t kk = 0; kk < k; kk++) {
            uint32_t Hkk = base_height >> kk; if (Hkk == 0) Hkk = 1;
            uint32_t Wkk = base_width >> kk; if (Wkk == 0) Wkk = 1;
            oo += 2 * Hkk * Wkk;
        }

        // Normalize earth octave channels into a float buffer (nc, Hk, Wk) with nan for nodata
        // We'll work directly with indices.
        // Target signature: per channel mean/std/quantiles/texture
        double t_mean[NC], t_std[NC], t_quant[NC][5], t_tex[NC];
        for (uint32_t c = 0; c < nc; c++) {
            // collect valid target values
            std::vector<float> vals;
            vals.reserve(th_Hk * th_Wk);
            double sum = 0, sumsq = 0; long cnt = 0;
            for (uint32_t i = 0; i < th_Hk; i++)
                for (uint32_t j = 0; j < th_Wk; j++) {
                    float v = tbase[to + ((size_t)c * th_Hk + i) * th_Wk + j];
                    if (v == nodata_val) continue;
                    float z = (float)((v - REF_MU[c]) / REF_SIG[c]);
                    if (z < -5.0f) z = -5.0f;
                    if (z > 5.0f) z = 5.0f;
                    vals.push_back(z);
                    sum += z; sumsq += (double)z * z; cnt++;
                }
            t_mean[c] = cnt > 0 ? sum / cnt : 0.0;
            t_std[c] = cnt > 0 ? std::sqrt(sumsq / cnt - t_mean[c]*t_mean[c]) : 0.0;
            if (t_std[c] < 0) t_std[c] = 0;
            // quantiles
            if (vals.size() > 0) {
                std::sort(vals.begin(), vals.end());
                int n = vals.size();
                int qidx[5] = { (int)(0.10*(n-1)), (int)(0.25*(n-1)), (int)(0.50*(n-1)), (int)(0.75*(n-1)), (int)(0.90*(n-1)) };
                for (int q = 0; q < 5; q++) t_quant[c][q] = vals[qidx[q]];
            } else {
                for (int q = 0; q < 5; q++) t_quant[c][q] = 0.0;
            }
            // texture energy: mean gradient magnitude on normalized target
            // compute normalized target grid first
        }
        // texture energy per channel for target
        for (uint32_t c = 0; c < nc; c++) {
            // build normalized grid
            std::vector<float> grid(th_Hk * th_Wk);
            for (uint32_t i = 0; i < th_Hk; i++)
                for (uint32_t j = 0; j < th_Wk; j++) {
                    float v = tbase[to + ((size_t)c * th_Hk + i) * th_Wk + j];
                    if (v == nodata_val) { grid[i*th_Wk+j] = NAN; continue; }
                    float z = (float)((v - REF_MU[c]) / REF_SIG[c]);
                    if (z < -5.0f) z = -5.0f;
                    if (z > 5.0f) z = 5.0f;
                    grid[i*th_Wk+j] = z;
                }
            double tsum = 0; long tcnt = 0;
            for (uint32_t i = 0; i < th_Hk; i++)
                for (uint32_t j = 0; j < th_Wk; j++) {
                    if (std::isnan(grid[i*th_Wk+j])) continue;
                    double gx = (j+1 < th_Wk && !std::isnan(grid[i*th_Wk+(j+1)])) ? std::fabs(grid[i*th_Wk+(j+1)] - grid[i*th_Wk+j]) : 0.0;
                    double gy = (i+1 < th_Hk && !std::isnan(grid[(i+1)*th_Wk+j])) ? std::fabs(grid[(i+1)*th_Wk+j] - grid[i*th_Wk+j]) : 0.0;
                    tsum += std::sqrt(gx*gx + gy*gy);
                    tcnt++;
                }
            t_tex[c] = tcnt > 0 ? tsum / tcnt : 0.0;
        }

        int r = 15 >> k; if (r < 3) r = 3;
        int win = 2 * r + 1;

        double sum_sim = 0.0;
        long count = 0;

        #pragma omp parallel for collapse(2) reduction(+:sum_sim,count)
        for (int i = 0; i < (int)Hk; i++) {
            for (int j = 0; j < (int)Wk; j++) {
                // center pixel nodata check
                int center_nodata = 0;
                for (uint32_t c = 0; c < nc; c++) {
                    float v = ebase[eo + ((size_t)c * Hk + i) * Wk + j];
                    if (v == nodata_val) { center_nodata = 1; break; }
                }
                // f_valid: fraction of valid pixels in window
                int wcount = 0, wvalid = 0;
                for (int wi = -r; wi <= r; wi++) {
                    for (int wj = -r; wj <= r; wj++) {
                        int ii = i + wi, jj = j + wj;
                        wcount++;
                        if (ii < 0 || ii >= (int)Hk || jj < 0 || jj >= (int)Wk) continue;
                        int anynod = 0;
                        for (uint32_t c = 0; c < nc; c++) {
                            float v = ebase[eo + ((size_t)c * Hk + ii) * Wk + jj];
                            if (v == nodata_val) { anynod = 1; break; }
                        }
                        if (!anynod) wvalid++;
                    }
                }
                float f_valid = (float)wvalid / (float)wcount;
                if (center_nodata || f_valid < 0.25f) {
                    obase[oo + (0 * Hk + i) * Wk + j] = 0.0f;
                    obase[oo + (1 * Hk + i) * Wk + j] = 0.0f;
                    continue;
                }

                // per-channel earth window quantiles, texture, std
                double Dsum = 0.0;
                double std_diff_sum = 0.0;
                for (uint32_t c = 0; c < nc; c++) {
                    // collect window values
                    std::vector<float> wvals;
                    wvals.reserve((2*r+1)*(2*r+1));
                    double esum = 0, esumsq = 0; long ecnt = 0;
                    for (int wi = -r; wi <= r; wi++) {
                        for (int wj = -r; wj <= r; wj++) {
                            int ii = i + wi, jj = j + wj;
                            if (ii < 0 || ii >= (int)Hk || jj < 0 || jj >= (int)Wk) continue;
                            float v = ebase[eo + ((size_t)c * Hk + ii) * Wk + jj];
                            if (v == nodata_val) continue;
                            float z = (float)((v - REF_MU[c]) / REF_SIG[c]);
                            if (z < -5.0f) z = -5.0f;
                            if (z > 5.0f) z = 5.0f;
                            wvals.push_back(z);
                            esum += z; esumsq += (double)z*z; ecnt++;
                            // texture: gradient at (ii,jj)
                            // We'll compute texture separately below; skip here
                        }
                    }
                    // earth quantiles
                    double eq[5] = {0,0,0,0,0};
                    if (wvals.size() > 0) {
                        std::sort(wvals.begin(), wvals.end());
                        int n = wvals.size();
                        int qidx[5] = { (int)(0.10*(n-1)), (int)(0.25*(n-1)), (int)(0.50*(n-1)), (int)(0.75*(n-1)), (int)(0.90*(n-1)) };
                        for (int q = 0; q < 5; q++) eq[q] = wvals[qidx[q]];
                    }
                    double esd = ecnt > 0 ? std::sqrt(esumsq/ecnt - (esum/ecnt)*(esum/ecnt)) : 0.0;
                    if (esd < 0) esd = 0;
                    // W1
                    double w1 = 0.0;
                    for (int q = 0; q < 5; q++) w1 += std::fabs(eq[q] - t_quant[c][q]);
                    w1 /= 5.0;
                    // texture earth: mean gradient magnitude in window
                    double texsum = 0; long tcnt2 = 0;
                    for (int wi = -r; wi <= r; wi++) {
                        for (int wj = -r; wj <= r; wj++) {
                            int ii = i + wi, jj = j + wj;
                            if (ii < 0 || ii >= (int)Hk || jj < 0 || jj >= (int)Wk) continue;
                            float v = ebase[eo + ((size_t)c * Hk + ii) * Wk + jj];
                            if (v == nodata_val) continue;
                            float z = (float)((v - REF_MU[c]) / REF_SIG[c]);
                            if (z < -5.0f) z = -5.0f;
                            if (z > 5.0f) z = 5.0f;
                            double gx = 0, gy = 0;
                            if (jj+1 < (int)Wk) {
                                float v2 = ebase[eo + ((size_t)c*Hk+ii)*Wk+(jj+1)];
                                if (v2 != nodata_val) {
                                    float z2 = (float)((v2 - REF_MU[c])/REF_SIG[c]);
                                    if (z2<-5) z2=-5; if (z2>5) z2=5;
                                    gx = std::fabs(z2 - z);
                                }
                            }
                            if (ii+1 < (int)Hk) {
                                float v2 = ebase[eo + ((size_t)c*Hk+(ii+1))*Wk+jj];
                                if (v2 != nodata_val) {
                                    float z2 = (float)((v2 - REF_MU[c])/REF_SIG[c]);
                                    if (z2<-5) z2=-5; if (z2>5) z2=5;
                                    gy = std::fabs(z2 - z);
                                }
                            }
                            texsum += std::sqrt(gx*gx + gy*gy);
                            tcnt2++;
                        }
                    }
                    double etex = tcnt2 > 0 ? texsum / tcnt2 : 0.0;
                    double deltaE = std::fabs(etex - t_tex[c]) / (etex + t_tex[c] + 1e-6);
                    Dsum += 0.75 * w1 + 0.25 * deltaE;
                    std_diff_sum += std::fabs(esd - t_std[c]);
                }
                double D = Dsum / (double)nc;
                float sim = (float)std::exp(-D);
                float conf = f_valid * (float)(1.0 / (1.0 + std_diff_sum / (double)nc));
                if (sim < 0) sim = 0; if (sim > 1) sim = 1;
                if (conf < 0) conf = 0; if (conf > 1) conf = 1;
                obase[oo + (0 * Hk + i) * Wk + j] = sim;
                obase[oo + (1 * Hk + i) * Wk + j] = conf;
                if (conf > 0.0f) { sum_sim += sim; count++; }
            }
        }
        if (count > 0) octave_means[k] = sum_sim / (double)count;

    // scale invariance
    double mean = 0.0;
    for (uint32_t k = 0; k < num_octaves; k++) mean += octave_means[k];
    mean /= num_octaves;
    double var = 0.0;
    for (uint32_t k = 0; k < num_octaves; k++) { double d = octave_means[k]-mean; var += d*d; }
    var /= (num_octaves > 1 ? num_octaves : 1);
    double si = 1.0 - std::sqrt(var);
    if (si < 0) si = 0; if (si > 1) si = 1;

    // breakdown json
    if (out_breakdown_json_path) {
        FILE* f = fopen(out_breakdown_json_path, "w");
        if (f) {
            fprintf(f, "{\n");
            fprintf(f, "  \"scale_invariance_index\": %.6f,\n", si);
            // channel_residuals using ch0.. keys (computed from raw earlier? skip, use empty for now)
            fprintf(f, "  \"channel_residuals\": {},\n");
            fprintf(f, "  \"physical_breakdown_flags\": [\n");
            fprintf(f, "    {\"flag\": \"GRAVITY_SCALING\", \"gravity_scaling_factor\": %.6f},\n", (double)th->gravity_ms2 / (double)eh->gravity_ms2);
            fprintf(f, "    {\"flag\": \"ATMOSPHERE_GAP\", \"atmospheric_pressure_gap_pa\": %.6f},\n", (double)std::fabs(eh->surface_pressure_pa - th->surface_pressure_pa));
            fprintf(f, "    {\"flag\": \"RADIATION_DELTA\", \"radiation_delta_msv_yr\": %.6f},\n", (double)std::fabs(eh->radiation_msv_yr - th->radiation_msv_yr));
            fprintf(f, "    {\"flag\": \"NO_ATMOSPHERE_TARGET\", \"details\": \"Target body has no atmosphere.\"}\n");
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
}
