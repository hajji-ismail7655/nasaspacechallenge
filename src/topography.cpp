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

// 7 channels: 6 original + illumination proxy
static const int NC = 7;
static const double REF_MU[NC] = {500.0, 15.0, 180.0, 50.0, 0.0, 0.0, 0.0};
static const double REF_SIG[NC] = {1000.0, 15.0, 103.9, 50.0, 50.0, 0.01, 0.5};

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
    size_t exp_e = 128, exp_t = 128;
    // compute expected from header (need to read header first but check size >= 128 first)
    if (est.st_size < 128 || tst.st_size < 128) { munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -13; }
    TileBinaryHeader* eh = (TileBinaryHeader*)emap;
    TileBinaryHeader* th = (TileBinaryHeader*)tmap;
    if (eh->magic != PTIL_MAGIC || th->magic != PTIL_MAGIC) { munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -7; }
    if (eh->version != CONTRACT_VERSION || th->version != CONTRACT_VERSION) { munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -8; }
    for (uint32_t k = 0; k < eh->num_octaves; k++) exp_e += (size_t)eh->num_channels * (eh->base_height >> k) * (eh->base_width >> k) * 4;
    for (uint32_t k = 0; k < th->num_octaves; k++) exp_t += (size_t)th->num_channels * (th->base_height >> k) * (th->base_width >> k) * 4;
    if ((size_t)est.st_size < exp_e || (size_t)tst.st_size < exp_t) { munmap(emap, est.st_size); munmap(tmap, tst.st_size); return -12; }

    uint32_t num_octaves = eh->num_octaves;
    if (th->num_octaves < num_octaves) num_octaves = th->num_octaves;
    if (num_octaves > 32) num_octaves = 32;
    uint32_t base_height = eh->base_height;
    uint32_t base_width = eh->base_width;
    uint32_t th_base_height = th->base_height;
    uint32_t th_base_width = th->base_width;
    uint32_t nc_e = eh->num_channels;
    uint32_t nc_t = th->num_channels;
    // use 6 tile channels + 1 proxy
    uint32_t nc = 6; if (nc_e < 6) nc = nc_e; if (nc_t < 6) nc = nc_t;
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

    // channel residuals accumulators
    double e_sum[NC+1], t_sum[NC+1]; long e_cnt[NC+1], t_cnt[NC+1];
    double e_sumsq[NC+1], t_sumsq[NC+1];
    for (int c = 0; c <= (int)nc; c++) { e_sum[c]=t_sum[c]=e_sumsq[c]=t_sumsq[c]=0; e_cnt[c]=t_cnt[c]=0; }

    for (uint32_t k = 0; k < num_octaves; k++) {
        uint32_t Hk = base_height >> k; if (Hk == 0) Hk = 1;
        uint32_t Wk = base_width >> k; if (Wk == 0) Wk = 1;
        uint32_t th_Hk = th_base_height >> k; if (th_Hk == 0) th_Hk = 1;
        uint32_t th_Wk = th_base_width >> k; if (th_Wk == 0) th_Wk = 1;

        size_t eo = 0, to = 0;
        for (uint32_t kk = 0; kk < k; kk++) {
            uint32_t Hkk = base_height >> kk; if (Hkk == 0) Hkk = 1;
            uint32_t Wkk = base_width >> kk; if (Wkk == 0) Wkk = 1;
            eo += (size_t)nc_e * Hkk * Wkk;
            uint32_t tHkk = th_base_height >> kk; if (tHkk == 0) tHkk = 1;
            uint32_t tWkk = th_base_width >> kk; if (tWkk == 0) tWkk = 1;
            to += (size_t)nc_t * tHkk * tWkk;
        }
        size_t oo = 0;
        for (uint32_t kk = 0; kk < k; kk++) {
            uint32_t Hkk = base_height >> kk; if (Hkk == 0) Hkk = 1;
            uint32_t Wkk = base_width >> kk; if (Wkk == 0) Wkk = 1;
            oo += 2 * Hkk * Wkk;
        }

        int r = 15 >> k; if (r < 3) r = 3;
        int win = 2 * r + 1;

        // Precompute normalized earth grid (nc+1 channels including proxy) and tex grid
        // normalized: nan for nodata
        // We'll just compute on demand. Precompute target signature.
        // Target signature per channel (0..nc, where nc is proxy index 6)
        double t_mean[NC+1], t_std[NC+1], t_quant[NC+1][5], t_tex[NC+1];
        for (int c = 0; c <= (int)nc; c++) {
            // collect valid target normalized values
            // for c < nc use tile channels; for c == nc (proxy) compute from slope/aspect
            std::vector<float> vals;
            double sum = 0, sumsq = 0; long cnt = 0;
            // We need normalized target grid for texture; compute inline
            // First pass: collect vals for quantiles/mean/std
            for (uint32_t i = 0; i < th_Hk; i++) {
                for (uint32_t j = 0; j < th_Wk; j++) {
                    float z;
                    if (c < (int)nc) {
                        float v = tbase[to + ((size_t)c * th_Hk + i) * th_Wk + j];
                        if (v == nodata_val) continue;
                        z = (float)((v - REF_MU[c]) / REF_SIG[c]);
                        if (z < -5.0f) z = -5.0f;
                        if (z > 5.0f) z = 5.0f;
                    } else {
                        // proxy: sin(deg2rad(slope))*cos(deg2rad(aspect)) / 0.5
                        float vs = tbase[to + (1 * th_Hk + i) * th_Wk + j];
                        float va = tbase[to + (2 * th_Hk + i) * th_Wk + j];
                        if (vs == nodata_val || va == nodata_val) continue;
                        double sl = (vs - REF_MU[1]) / REF_SIG[1]; // normalized slope (approx)
                        // use raw degrees instead:
                        // Actually use raw: vs is raw slope degrees
                        double zr = std::sin((vs) * M_PI / 180.0) * std::cos((va) * M_PI / 180.0);
                        z = (float)(zr / 0.5);
                        if (z < -5.0f) z = -5.0f;
                        if (z > 5.0f) z = 5.0f;
                    }
                    vals.push_back(z);
                    sum += z; sumsq += (double)z*z; cnt++;
                    // residuals accumulators (raw)
                    if (c < (int)nc) {
                        float v = tbase[to + ((size_t)c * th_Hk + i) * th_Wk + j];
                        if (v != nodata_val) { t_sum[c] += v; t_sumsq[c] += (double)v*v; t_cnt[c]++; }
                    }
                }
            }
            t_mean[c] = cnt > 0 ? sum / cnt : 0.0;
            t_std[c] = cnt > 0 ? std::sqrt(sumsq/cnt - t_mean[c]*t_mean[c]) : 0.0;
            if (t_std[c] < 0) t_std[c] = 0;
            if (vals.size() > 0) {
                std::sort(vals.begin(), vals.end());
                int n = vals.size();
                // linear quantiles
                for (int q = 0; q < 5; q++) {
                    double p = (q==0)?0.10:(q==1)?0.25:(q==2)?0.50:(q==3)?0.75:0.90;
                    double pos = p * (n - 1);
                    int lo = (int)std::floor(pos);
                    int hi = lo + 1; if (hi >= n) hi = n-1;
                    double frac = pos - lo;
                    t_quant[c][q] = vals[lo] * (1.0 - frac) + vals[hi] * frac;
                }
            } else {
                for (int q = 0; q < 5; q++) t_quant[c][q] = 0.0;
            }
            // texture energy: backward diff on nan->0, averaged over all cells (win*win handled in window)
            // For target signature, compute mean gradient magnitude over valid cells
            double tsum = 0; long tcnt = 0;
            for (uint32_t i = 0; i < th_Hk; i++) {
                for (uint32_t j = 0; j < th_Wk; j++) {
                    float v;
                    if (c < (int)nc) {
                        v = tbase[to + ((size_t)c * th_Hk + i) * th_Wk + j];
                        if (v == nodata_val) continue;
                        float z = (float)((v - REF_MU[c]) / REF_SIG[c]);
                        if (z < -5.0f) z = -5.0f; if (z > 5.0f) z = 5.0f;
                    } else {
                        float vs = tbase[to + (1 * th_Hk + i) * th_Wk + j];
                        float va = tbase[to + (2 * th_Hk + i) * th_Wk + j];
                        if (vs == nodata_val || va == nodata_val) continue;
                        double zr = std::sin(vs * M_PI / 180.0) * std::cos(va * M_PI / 180.0);
                        float z = (float)(zr / 0.5);
                        if (z < -5.0f) z = -5.0f; if (z > 5.0f) z = 5.0f;
                        v = z; // dummy
                    }
                    // gradient backward
                    // need normalized grid; recompute z
                    float zc;
                    if (c < (int)nc) {
                        float vv = tbase[to + ((size_t)c * th_Hk + i) * th_Wk + j];
                        zc = (float)((vv - REF_MU[c]) / REF_SIG[c]);
                        if (zc < -5) zc = -5; if (zc > 5) zc = 5;
                    } else {
                        float vs = tbase[to + (1 * th_Hk + i) * th_Wk + j];
                        float va = tbase[to + (2 * th_Hk + i) * th_Wk + j];
                        double zr = std::sin(vs * M_PI / 180.0) * std::cos(va * M_PI / 180.0);
                        zc = (float)(zr / 0.5);
                        if (zc < -5) zc = -5; if (zc > 5) zc = 5;
                    }
                    double gx = (j > 0) ? std::fabs(zc - ( [&](){ if (c < (int)nc) { float vv = tbase[to+((size_t)c*th_Hk+i)*th_Wk+(j-1)]; if (vv==nodata_val) return 0.0f; float zz=(float)((vv-REF_MU[c])/REF_SIG[c]); if(zz<-5)zz=-5; if(zz>5)zz=5; return zz;} else { float v1n = tbase[to + (1 * th_Hk + i) * th_Wk + (j-1)]; float v2n = tbase[to + (2 * th_Hk + i) * th_Wk + (j-1)]; if (v1n == nodata_val || v2n == nodata_val) return 0.0f; double zr = std::sin(v1n * M_PI / 180.0) * std::cos(v2n * M_PI / 180.0); float zz = (float)(zr / 0.5); if (zz < -5.0f) zz = -5.0f; if (zz > 5.0f) zz = 5.0f; return zz; } }() )) : 0.0;
                    double gy = (i > 0) ? std::fabs(zc - ( [&](){ if (c < (int)nc) { float vv = tbase[to+((size_t)c*th_Hk+(i-1))*th_Wk+j]; if (vv==nodata_val) return 0.0f; float zz=(float)((vv-REF_MU[c])/REF_SIG[c]); if(zz<-5)zz=-5; if(zz>5)zz=5; return zz;} else { float v1n = tbase[to + (1 * th_Hk + (i-1)) * th_Wk + j]; float v2n = tbase[to + (2 * th_Hk + (i-1)) * th_Wk + j]; if (v1n == nodata_val || v2n == nodata_val) return 0.0f; double zr = std::sin(v1n * M_PI / 180.0) * std::cos(v2n * M_PI / 180.0); float zz = (float)(zr / 0.5); if (zz < -5.0f) zz = -5.0f; if (zz > 5.0f) zz = 5.0f; return zz; } }() )) : 0.0;
                    tsum += std::sqrt(gx*gx + gy*gy);
                    tcnt++;
                }
            }
            t_tex[c] = tcnt > 0 ? tsum / tcnt : 0.0;
            // earth residuals accumulators
            for (uint32_t i = 0; i < th_Hk; i++)
                for (uint32_t j = 0; j < th_Wk; j++) {
                    if (c < nc) {
                        float v = tbase[to + ((size_t)c * th_Hk + i) * th_Wk + j];
                        if (v != nodata_val) { /* already accumulated above? no, that was target. Need earth separately. */ }
                    }
                }
        }

        double sum_sim = 0.0;
        long count = 0;

        #pragma omp parallel for collapse(2) reduction(+:sum_sim,count)
        for (int i = 0; i < (int)Hk; i++) {
            for (int j = 0; j < (int)Wk; j++) {
                // center nodata check
                int center_nodata = 0;
                for (uint32_t c = 0; c < nc; c++) {
                    float v = ebase[eo + ((size_t)c * Hk + i) * Wk + j];
                    if (v == nodata_val) { center_nodata = 1; break; }
                }
                // also proxy channel (c=nc) needs slope/aspect valid
                float vs = ebase[eo + (1 * Hk + i) * Wk + j];
                float va = ebase[eo + (2 * Hk + i) * Wk + j];
                if (vs == nodata_val || va == nodata_val) center_nodata = 1;

                // f_valid: min over channels (nc+1) of per-channel valid fraction in window
                // compute per-channel valid fractions
                float fv[NC+1];
                for (int c = 0; c <= (int)nc; c++) {
                    int wcount = 0, wvalid = 0;
                    for (int wi = -r; wi <= r; wi++) {
                        for (int wj = -r; wj <= r; wj++) {
                            int ii = i + wi, jj = j + wj;
                            wcount++;
                            if (ii < 0 || ii >= (int)Hk || jj < 0 || jj >= (int)Wk) continue;
                            int anynod = 0;
                            if (c < (int)nc) {
                                float v = ebase[eo + ((size_t)c * Hk + ii) * Wk + jj];
                                if (v == nodata_val) anynod = 1;
                            } else {
                                float v1 = ebase[eo + (1 * Hk + ii) * Wk + jj];
                                float v2 = ebase[eo + (2 * Hk + ii) * Wk + jj];
                                if (v1 == nodata_val || v2 == nodata_val) anynod = 1;
                            }
                            if (!anynod) wvalid++;
                        }
                    }
                    fv[c] = (float)wvalid / (float)wcount;
                }
                float f_valid = fv[0];
                for (int c = 1; c <= (int)nc; c++) if (fv[c] < f_valid) f_valid = fv[c];

                if (center_nodata || f_valid < 0.25f) {
                    obase[oo + (0 * Hk + i) * Wk + j] = 0.0f;
                    obase[oo + (1 * Hk + i) * Wk + j] = 0.0f;
                    continue;
                }

                // per-channel earth window quantiles, texture, std
                double Dsum = 0.0;
                double std_diff_sum = 0.0;
                for (uint32_t c = 0; c <= nc; c++) {
                    // collect window values
                    float wbuf[961];
                    int wn = 0;
                    double esum = 0, esumsq = 0; long ecnt = 0;
                    for (int wi = -r; wi <= r; wi++) {
                        for (int wj = -r; wj <= r; wj++) {
                            int ii = i + wi, jj = j + wj;
                            if (ii < 0 || ii >= (int)Hk || jj < 0 || jj >= (int)Wk) continue;
                            float z;
                            if (c < nc) {
                                float v = ebase[eo + ((size_t)c * Hk + ii) * Wk + jj];
                                if (v == nodata_val) continue;
                                z = (float)((v - REF_MU[c]) / REF_SIG[c]);
                                if (z < -5.0f) z = -5.0f;
                                if (z > 5.0f) z = 5.0f;
                            } else {
                                float v1 = ebase[eo + (1 * Hk + ii) * Wk + jj];
                                float v2 = ebase[eo + (2 * Hk + ii) * Wk + jj];
                                if (v1 == nodata_val || v2 == nodata_val) continue;
                                double zr = std::sin(v1 * M_PI / 180.0) * std::cos(v2 * M_PI / 180.0);
                                z = (float)(zr / 0.5);
                                if (z < -5.0f) z = -5.0f;
                                if (z > 5.0f) z = 5.0f;
                            }
                            wbuf[wn++] = z;
                            esum += z; esumsq += (double)z*z; ecnt++;
                        }
                    }
                    // quantiles (linear)
                    double eq[5] = {0,0,0,0,0};
                    if (wn > 0) {
                        std::sort(wbuf, wbuf + wn);
                        for (int q = 0; q < 5; q++) {
                            double p = (q==0)?0.10:(q==1)?0.25:(q==2)?0.50:(q==3)?0.75:0.90;
                            double pos = p * (wn - 1);
                            int lo = (int)std::floor(pos);
                            int hi = lo + 1; if (hi >= wn) hi = wn-1;
                            double frac = pos - lo;
                            eq[q] = wbuf[lo] * (1.0 - frac) + wbuf[hi] * frac;
                        }
                    }
                    double esd = ecnt > 0 ? std::sqrt(esumsq/ecnt - (esum/ecnt)*(esum/ecnt)) : 0.0;
                    if (esd < 0) esd = 0;
                    // W1
                    double w1 = 0.0;
                    for (int q = 0; q < 5; q++) w1 += std::fabs(eq[q] - t_quant[c][q]);
                    w1 /= 5.0;
                    // texture earth: backward diff on nan->0 (0 for nodata), averaged over win*win
                    // Precompute normalized grid not available per-pixel; compute window mean of gradient magnitude
                    // using (i,j) window. We'll approximate by summing gradients at valid cells / (win*win).
                    double texsum = 0.0;
                    for (int wi = -r; wi <= r; wi++) {
                        for (int wj = -r; wj <= r; wj++) {
                            int ii = i + wi, jj = j + wj;
                            if (ii < 0 || ii >= (int)Hk || jj < 0 || jj >= (int)Wk) continue;
                            // gradient at (ii,jj) using backward diff on normalized value (0 if nodata)
                            float zc;
                            if (c < (int)nc) {
                                float v = ebase[eo + ((size_t)c * Hk + ii) * Wk + jj];
                                if (v == nodata_val) zc = 0; else { zc = (float)((v - REF_MU[c]) / REF_SIG[c]); if (zc<-5) zc=-5; if (zc>5) zc=5; }
                            } else {
                                float v1 = ebase[eo + (1 * Hk + ii) * Wk + jj];
                                float v2 = ebase[eo + (2 * Hk + ii) * Wk + jj];
                                if (v1 == nodata_val || v2 == nodata_val) zc = 0;
                                else { double zr = std::sin(v1 * M_PI / 180.0) * std::cos(v2 * M_PI / 180.0); zc = (float)(zr/0.5); if (zc<-5) zc=-5; if (zc>5) zc=5; }
                            }
                            // backward diff
                            float zleft = 0, zup = 0;
                            if (jj > 0) {
                                float v = ebase[eo + ((size_t)c * Hk + ii) * Wk + (jj-1)];
                                if (c < (int)nc) {
                                    if (v == nodata_val) zleft = 0; else { zleft = (float)((v - REF_MU[c]) / REF_SIG[c]); if (zleft<-5) zleft=-5; if (zleft>5) zleft=5; }
                                } else {
                                    float v1 = ebase[eo + (1*Hk+ii)*Wk + (jj-1)];
                                    float v2 = ebase[eo + (2*Hk+ii)*Wk + (jj-1)];
                                    if (v1==nodata_val||v2==nodata_val) zleft=0;
                                    else { double zr=std::sin(v1*M_PI/180.0)*std::cos(v2*M_PI/180.0); zleft=(float)(zr/0.5); if(zleft<-5)zleft=-5; if(zleft>5)zleft=5; }
                                }
                            }
                            if (ii > 0) {
                                float v = ebase[eo + ((size_t)c * Hk + (ii-1)) * Wk + jj];
                                if (c < (int)nc) {
                                    if (v == nodata_val) zup = 0; else { zup = (float)((v - REF_MU[c]) / REF_SIG[c]); if (zup<-5) zup=-5; if (zup>5) zup=5; }
                                } else {
                                    float v1 = ebase[eo + (1*Hk+(ii-1))*Wk + jj];
                                    float v2 = ebase[eo + (2*Hk+(ii-1))*Wk + jj];
                                    if (v1==nodata_val||v2==nodata_val) zup=0;
                                    else { double zr=std::sin(v1*M_PI/180.0)*std::cos(v2*M_PI/180.0); zup=(float)(zr/0.5); if(zup<-5)zup=-5; if(zup>5)zup=5; }
                                }
                            }
                            double gx = std::fabs(zc - zleft);
                            double gy = std::fabs(zc - zup);
                            texsum += std::sqrt(gx*gx + gy*gy);
                        }
                    }
                    double etex = texsum / (double)(win*win);
                    double deltaE = std::fabs(etex - t_tex[c]) / (etex + t_tex[c] + 1e-6);
                    Dsum += 0.75 * w1 + 0.25 * deltaE;
                    std_diff_sum += std::fabs(esd - t_std[c]);
                }
                double D = Dsum / (double)(nc + 1);
                float sim = (float)std::exp(-D);
                float conf = f_valid * (float)(1.0 / (1.0 + std_diff_sum / (double)(nc + 1)));
                if (sim < 0) sim = 0; if (sim > 1) sim = 1;
                if (conf < 0) conf = 0; if (conf > 1) conf = 1;
                obase[oo + (0 * Hk + i) * Wk + j] = sim;
                obase[oo + (1 * Hk + i) * Wk + j] = conf;
                if (conf > 0.0f) { sum_sim += sim; count++; }
            }
        }
        if (count > 0) octave_means[k] = sum_sim / (double)count;
    }

    // accumulate earth raw channel residuals
    for (uint32_t c = 0; c < nc; c++) {
        size_t eo2 = 0;
        for (uint32_t kk = 0; kk < num_octaves; kk++) {
            uint32_t Hkk = base_height >> kk; if (Hkk == 0) Hkk = 1;
            uint32_t Wkk = base_width >> kk; if (Wkk == 0) Wkk = 1;
            for (uint32_t i = 0; i < Hkk; i++)
                for (uint32_t j = 0; j < Wkk; j++) {
                    float v = ebase[eo2 + ((size_t)c * Hkk + i) * Wkk + j];
                    if (v != nodata_val) { e_sum[c] += v; e_sumsq[c] += (double)v*v; e_cnt[c]++; }
                }
            eo2 += (size_t)nc_e * Hkk * Wkk;
        }
    }

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
            // build channel_residuals json
            char crbuf[8192]; int crpos = 0;
            crpos += snprintf(crbuf + crpos, sizeof(crbuf)-crpos, "{");
            for (uint32_t c = 0; c < nc; c++) {
                double emean = e_cnt[c] > 0 ? e_sum[c]/e_cnt[c] : 0.0;
                double tmean = t_cnt[c] > 0 ? t_sum[c]/t_cnt[c] : 0.0;
                double epooled = e_cnt[c] > 0 ? e_sumsq[c]/e_cnt[c] - emean*emean : 0.0;
                double tpooled = t_cnt[c] > 0 ? t_sumsq[c]/t_cnt[c] - tmean*tmean : 0.0;
                double pooled = std::sqrt(epooled + tpooled + 1e-12);
                double zdiv = pooled > 0 ? (emean - tmean) / pooled : 0.0;
                if (c > 0) crpos += snprintf(crbuf + crpos, sizeof(crbuf)-crpos, ",");
                crpos += snprintf(crbuf + crpos, sizeof(crbuf)-crpos, " \"ch%u\": {\"earth_mean\": %.6f, \"target_mean\": %.6f, \"z_divergence\": %.6f}", c, emean, tmean, zdiv);
            }
            crpos += snprintf(crbuf + crpos, sizeof(crbuf)-crpos, "}");
            fprintf(f, "  \"channel_residuals\": %s,\n", crbuf);
            fprintf(f, "  \"physical_breakdown_flags\": [\n");
            fprintf(f, "    {\"flag\": \"GRAVITY_SCALING\", \"gravity_scaling_factor\": %.6f},\n", (double)th->gravity_ms2 / (double)eh->gravity_ms2);
            fprintf(f, "    {\"flag\": \"ATMOSPHERE_GAP\", \"atmospheric_pressure_gap_pa\": %.6f},\n", (double)std::fabs(eh->surface_pressure_pa - th->surface_pressure_pa));
            fprintf(f, "    {\"flag\": \"RADIATION_DELTA\", \"radiation_delta_msv_yr\": %.6f},\n", (double)std::fabs(eh->radiation_msv_yr - th->radiation_msv_yr));
            if (th->body == 2 && eh->body == 1)
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

