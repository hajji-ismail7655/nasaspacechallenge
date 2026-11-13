#ifndef NASASPACE_DISTRIBUTION_V2_HPP
#define NASASPACE_DISTRIBUTION_V2_HPP

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <iomanip>
#include <limits>
#include <sstream>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#include <omp.h>

namespace distribution_v2 {
constexpr uint32_t kPtilMagic = 0x4C495450U;
constexpr uint32_t kHmapMagic = 0x50414D48U;
constexpr uint32_t kVersion = 1U;
constexpr float kNoData = -9999.0f;
constexpr int kMaxChannels = 8;
constexpr int kMaxWindow = 31;
constexpr int kMaxWindowCells = kMaxWindow * kMaxWindow;

struct alignas(64) TileHeader {
    uint32_t magic, version, body, domain, num_octaves, num_channels, base_height, base_width;
    double base_resolution_m, center_lat_deg, center_lon_deg;
    float nodata_value, gravity_ms2, surface_pressure_pa, radiation_msv_yr;
    unsigned char reserved[56];
};
static_assert(sizeof(TileHeader) == 128, "tile header must be 128 bytes");

enum class Kind { Topography, Mineralogy, Thermal, Granular, Volatiles };
struct Config {
    Kind kind;
    const char* name;
    uint32_t reference_count;
    double mu[kMaxChannels];
    double sigma[kMaxChannels];
    bool illumination_proxy;
};

struct Mapping {
    void* data = MAP_FAILED;
    size_t size = 0;
    Mapping() = default;
    Mapping(const Mapping&) = delete;
    Mapping& operator=(const Mapping&) = delete;
    ~Mapping() { if (data != MAP_FAILED) munmap(data, size); }
    bool open_read(const char* path) {
        int fd = open(path, O_RDONLY);
        if (fd < 0) return false;
        struct stat st;
        if (fstat(fd, &st) != 0 || st.st_size < 128) { close(fd); return false; }
        size = static_cast<size_t>(st.st_size);
        data = mmap(nullptr, size, PROT_READ, MAP_PRIVATE, fd, 0);
        close(fd);
        return data != MAP_FAILED;
    }
    const TileHeader* header() const { return static_cast<const TileHeader*>(data); }
    const float* payload() const { return reinterpret_cast<const float*>(static_cast<const char*>(data) + 128); }
};

inline bool checked_size(const TileHeader* h, size_t file_size) {
    if (!h || h->magic != kPtilMagic || h->version != kVersion ||
        h->num_octaves == 0 || h->num_octaves > 32 ||
        h->num_channels == 0 || h->base_height == 0 || h->base_width == 0) return false;
    uint64_t expected = 128;
    for (uint32_t k = 0; k < h->num_octaves; ++k) {
        if (k >= 32) return false;
        const uint32_t height = h->base_height >> k;
        const uint32_t width = h->base_width >> k;
        if (height == 0 || width == 0) return false;
        const uint64_t cells = static_cast<uint64_t>(height) * width;
        const uint64_t bytes = cells * h->num_channels * sizeof(float);
        if (bytes > std::numeric_limits<uint64_t>::max() - expected) return false;
        expected += bytes;
    }
    return expected <= file_size;
}

inline float clamp_z(double z) {
    return static_cast<float>(std::max(-5.0, std::min(5.0, z)));
}

struct Prefix {
    uint32_t height = 0, width = 0;
    std::vector<double> sum, sumsq, valid, texture;
    static double rect(const std::vector<double>& table, uint32_t width,
                       uint32_t r0, uint32_t c0, uint32_t r1, uint32_t c1) {
        const size_t stride = static_cast<size_t>(width) + 1;
        return table[static_cast<size_t>(r1) * stride + c1]
             - table[static_cast<size_t>(r0) * stride + c1]
             - table[static_cast<size_t>(r1) * stride + c0]
             + table[static_cast<size_t>(r0) * stride + c0];
    }
    double query_sum(uint32_t r0,uint32_t c0,uint32_t r1,uint32_t c1) const { return rect(sum,width,r0,c0,r1,c1); }
    double query_sumsq(uint32_t r0,uint32_t c0,uint32_t r1,uint32_t c1) const { return rect(sumsq,width,r0,c0,r1,c1); }
    double query_valid(uint32_t r0,uint32_t c0,uint32_t r1,uint32_t c1) const { return rect(valid,width,r0,c0,r1,c1); }
    double query_texture(uint32_t r0,uint32_t c0,uint32_t r1,uint32_t c1) const { return rect(texture,width,r0,c0,r1,c1); }
};

struct Grid {
    uint32_t height = 0, width = 0, channels = 0;
    bool any_valid = false;
    std::vector<float> values; // channel-major, NaN is invalid
    std::vector<Prefix> prefix;
    float at(uint32_t c,uint32_t i,uint32_t j) const {
        return values[(static_cast<size_t>(c)*height+i)*width+j];
    }
};

inline Grid make_grid(const float* base, size_t octave_offset,
                      uint32_t height, uint32_t width, uint32_t raw_channels,
                      uint32_t channels, const Config& cfg) {
    Grid g;
    g.height=height; g.width=width; g.channels=channels;
    const size_t cells=static_cast<size_t>(height)*width;
    g.values.assign(static_cast<size_t>(channels)*cells, std::numeric_limits<float>::quiet_NaN());
    for (uint32_t c=0;c<raw_channels;++c) {
        const float* src=base+octave_offset+static_cast<size_t>(c)*cells;
        float* dst=g.values.data()+static_cast<size_t>(c)*cells;
        for (size_t n=0;n<cells;++n) if (src[n] != kNoData)
            dst[n]=clamp_z((static_cast<double>(src[n])-cfg.mu[c])/cfg.sigma[c]);
    }
    if (cfg.illumination_proxy) {
        const float* slope=base+octave_offset+static_cast<size_t>(1)*cells;
        const float* aspect=base+octave_offset+static_cast<size_t>(2)*cells;
        float* dst=g.values.data()+static_cast<size_t>(raw_channels)*cells;
        for (size_t n=0;n<cells;++n) if (slope[n] != kNoData && aspect[n] != kNoData) {
            const double radians=3.14159265358979323846264338327950288/180.0;
            const double proxy=std::sin(static_cast<double>(slope[n])*radians)
                              *std::cos(static_cast<double>(aspect[n])*radians)/0.5;
            dst[n]=clamp_z(proxy);
        }
    }
    g.prefix.resize(channels);
    const size_t stride=static_cast<size_t>(width)+1;
    const size_t table_size=(static_cast<size_t>(height)+1)*stride;
    for (uint32_t c=0;c<channels;++c) {
        Prefix& p=g.prefix[c]; p.height=height; p.width=width;
        p.sum.assign(table_size,0.0); p.sumsq.assign(table_size,0.0);
        p.valid.assign(table_size,0.0); p.texture.assign(table_size,0.0);
        const size_t off=static_cast<size_t>(c)*cells;
        for (uint32_t i=0;i<height;++i) {
            double row_sum=0,row_sq=0,row_valid=0,row_tex=0;
            for (uint32_t j=0;j<width;++j) {
                const size_t n=off+static_cast<size_t>(i)*width+j;
                const float cur=g.values[n];
                const bool valid=std::isfinite(cur);
                const double z=valid?static_cast<double>(cur):0.0;
                double left=0,up=0;
                if (j>0) { const float v=g.values[n-1]; if(std::isfinite(v)) left=v; }
                if (i>0) { const float v=g.values[n-width]; if(std::isfinite(v)) up=v; }
                const double dx=j>0?std::fabs(z-left):0.0;
                const double dy=i>0?std::fabs(z-up):0.0;
                const double tex=std::sqrt(dx*dx+dy*dy);
                const size_t q=static_cast<size_t>(i+1)*stride+j+1;
                const size_t above=static_cast<size_t>(i)*stride+j+1;
                row_sum+=valid?z:0.0; row_sq+=valid?z*z:0.0;
                row_valid+=valid?1.0:0.0; row_tex+=tex;
                p.sum[q]=p.sum[above]+row_sum;
                p.sumsq[q]=p.sumsq[above]+row_sq;
                p.valid[q]=p.valid[above]+row_valid;
                p.texture[q]=p.texture[above]+row_tex;
                if(valid) g.any_valid=true;
            }
        }
    }
    return g;
}

struct Signature {
    double mean=0,std=0,quantile[5]={0,0,0,0,0},texture=0;
    uint64_t valid_count=0;
};
inline double percentile_sorted(const float* values,int n,double p) {
    if(n<=0) return 0.0;
    const double pos=p*static_cast<double>(n-1);
    const int lo=static_cast<int>(std::floor(pos));
    const int hi=std::min(lo+1,n-1);
    const double frac=pos-lo;
    return static_cast<double>(values[lo])*(1.0-frac)+static_cast<double>(values[hi])*frac;
}
inline void quantiles_select(float* values,int n,const double* ps,double* out) {
    int last_rank=-1;
    auto select_rank=[&](int rank) -> float {
        if(rank>last_rank) {
            if(rank==last_rank+1) {
                float* next=std::min_element(values+rank,values+n);
                std::iter_swap(values+rank,next);
            } else {
                std::nth_element(values+last_rank+1,values+rank,values+n);
            }
            last_rank=rank;
        }
        return values[rank];
    };
    for(int q=0;q<5;++q) {
        const double pos=ps[q]*static_cast<double>(n-1);
        const int lo=static_cast<int>(std::floor(pos));
        const int hi=std::min(lo+1,n-1);
        const double frac=pos-lo;
        const double a=select_rank(lo),b=select_rank(hi);
        out[q]=a*(1.0-frac)+b*frac;
    }
}
inline float numpy_pairwise_sum_f32(const float* values,size_t n) {
    if(n<8) {
        float total=-0.0f;
        for(size_t i=0;i<n;++i) total+=values[i];
        return total;
    }
    if(n<=128) {
        float r[8]={-0.0f,-0.0f,-0.0f,-0.0f,-0.0f,-0.0f,-0.0f,-0.0f};
        size_t i=0;
        for(;i<n-(n%8);i+=8) for(size_t lane=0;lane<8;++lane) r[lane]+=values[i+lane];
        float total=((r[0]+r[1])+(r[2]+r[3]))+((r[4]+r[5])+(r[6]+r[7]));
        for(;i<n;++i) total+=values[i];
        return total;
    }
    size_t split=n/2;
    split-=split%8;
    return numpy_pairwise_sum_f32(values,split)+numpy_pairwise_sum_f32(values+split,n-split);
}
inline std::vector<Signature> target_signature(const Grid& g) {
    static const double ps[5]={0.10,0.25,0.50,0.75,0.90};
    std::vector<Signature> sig(g.channels);
    const size_t cells=static_cast<size_t>(g.height)*g.width;
    for(uint32_t c=0;c<g.channels;++c) {
        std::vector<float> vals; vals.reserve(cells);
        double sum=0,sumsq=0,texsum=0;
        const size_t off=static_cast<size_t>(c)*cells;
        for(size_t n=0;n<cells;++n) {
            const float v=g.values[off+n];
            if(std::isfinite(v)) { vals.push_back(v); sum+=v; sumsq+=static_cast<double>(v)*v; }
        }
        Signature& s=sig[c]; s.valid_count=vals.size();
        if(!vals.empty()) {
            s.mean=sum/vals.size();
            s.std=std::sqrt(std::max(0.0,sumsq/vals.size()-s.mean*s.mean));
            std::sort(vals.begin(),vals.end());
            for(int q=0;q<5;++q) s.quantile[q]=percentile_sorted(vals.data(),static_cast<int>(vals.size()),ps[q]);
            const Prefix& p=g.prefix[c];
            for(size_t n=0;n<cells;++n) if(std::isfinite(g.values[off+n])) {
                const uint32_t i=static_cast<uint32_t>(n/g.width),j=static_cast<uint32_t>(n%g.width);
                const size_t stride=static_cast<size_t>(g.width)+1;
                texsum+=p.texture[(static_cast<size_t>(i)+1)*stride+j+1]
                       -p.texture[static_cast<size_t>(i)*stride+j+1]
                       -p.texture[(static_cast<size_t>(i)+1)*stride+j]
                       +p.texture[static_cast<size_t>(i)*stride+j];
            }
            s.texture=texsum/vals.size();
        }
    }
    return sig;
}

struct RawStats { double sum=0; uint64_t count=0; double mean=0,variance=0; };
inline void raw_stats(const float* base,const std::vector<size_t>& offsets,
                      const TileHeader* h,uint32_t channels,RawStats* stats) {
    for(uint32_t k=0;k<h->num_octaves;++k) {
        const uint32_t H=h->base_height>>k,W=h->base_width>>k;
        const size_t cells=static_cast<size_t>(H)*W;
        for(uint32_t c=0;c<channels;++c) {
            const float* src=base+offsets[k]+static_cast<size_t>(c)*cells;
            for(size_t n=0;n<cells;++n) if(src[n]!=kNoData) { stats[c].sum+=src[n]; ++stats[c].count; }
        }
    }
    for(uint32_t c=0;c<channels;++c) stats[c].mean=stats[c].count?stats[c].sum/stats[c].count:0.0;
    for(uint32_t k=0;k<h->num_octaves;++k) {
        const uint32_t H=h->base_height>>k,W=h->base_width>>k;
        const size_t cells=static_cast<size_t>(H)*W;
        for(uint32_t c=0;c<channels;++c) {
            const float* src=base+offsets[k]+static_cast<size_t>(c)*cells;
            for(size_t n=0;n<cells;++n) if(src[n]!=kNoData) {
                const double d=static_cast<double>(src[n])-stats[c].mean;
                stats[c].variance+=d*d;
            }
        }
    }
    for(uint32_t c=0;c<channels;++c)
        stats[c].variance=stats[c].count?stats[c].variance/stats[c].count:0.0;
}

inline uint32_t dim_at(uint32_t base,uint32_t k) { return base>>k; }
inline size_t byte_offset(const std::vector<size_t>& v,uint32_t k) { return v[k]; }

inline int32_t run(const char* earth_path,const char* target_path,const char* out_path,
                   const char* breakdown_path,const Config& cfg) {
    Mapping earth,target;
    if(!earth.open_read(earth_path)) return -1;
    if(!target.open_read(target_path)) return -2;
    const TileHeader* eh=earth.header(); const TileHeader* th=target.header();
    if(!checked_size(eh,earth.size)||!checked_size(th,target.size)) return -3;
    const uint32_t octaves=std::min(eh->num_octaves,th->num_octaves);
    const uint32_t raw_channels=std::min({eh->num_channels,th->num_channels,cfg.reference_count});
    if(raw_channels==0 || (cfg.illumination_proxy&&raw_channels<3)) return -4;
    const uint32_t channels=raw_channels+(cfg.illumination_proxy?1U:0U);
    const uint32_t H0=eh->base_height,W0=eh->base_width;
    std::vector<size_t> eoff(eh->num_octaves),toff(th->num_octaves),ooff(octaves);
    size_t ep=0,tp=0,op=128;
    for(uint32_t k=0;k<eh->num_octaves;++k) {
        eoff[k]=ep; ep+=static_cast<size_t>(eh->num_channels)*dim_at(eh->base_height,k)*dim_at(eh->base_width,k);
    }
    for(uint32_t k=0;k<th->num_octaves;++k) {
        toff[k]=tp; tp+=static_cast<size_t>(th->num_channels)*dim_at(th->base_height,k)*dim_at(th->base_width,k);
    }
    for(uint32_t k=0;k<octaves;++k) {
        ooff[k]=op; op+=static_cast<size_t>(2)*dim_at(H0,k)*dim_at(W0,k)*sizeof(float);
    }
    int ofd=open(out_path,O_RDWR|O_CREAT|O_TRUNC,0644);
    if(ofd<0) return -5;
    if(ftruncate(ofd,static_cast<off_t>(op))!=0) { close(ofd); return -6; }
    void* omap=mmap(nullptr,op,PROT_READ|PROT_WRITE,MAP_SHARED,ofd,0); close(ofd);
    if(omap==MAP_FAILED) return -7;
    TileHeader* oh=static_cast<TileHeader*>(omap); *oh=*eh; oh->magic=kHmapMagic; oh->num_octaves=octaves; oh->num_channels=2;
    float* out=reinterpret_cast<float*>(static_cast<char*>(omap)+128);
    const float* ebase=earth.payload(); const float* tbase=target.payload();

    RawStats eraw[kMaxChannels],traw[kMaxChannels];
    raw_stats(ebase,eoff,eh,raw_channels,eraw);
    // Target can have more channels than Earth; include NDVI channel for mineralogy hook.
    const uint32_t target_stat_channels=std::min(th->num_channels,cfg.reference_count);
    raw_stats(tbase,toff,th,target_stat_channels,traw);

    double octave_means[32]={0.0};
    for(uint32_t k=0;k<octaves;++k) {
        const uint32_t H=dim_at(H0,k),W=dim_at(W0,k);
        const uint32_t thH=dim_at(th->base_height,k),thW=dim_at(th->base_width,k);
        Grid eg=make_grid(ebase,eoff[k],H,W,raw_channels,channels,cfg);
        Grid tg=make_grid(tbase,toff[k],thH,thW,raw_channels,channels,cfg);
        std::vector<Signature> sig=target_signature(tg);
        const bool target_octave_valid=tg.any_valid;
        const int r=std::max(3,15>>k),win=2*r+1,area=win*win;
        const size_t outoff=(ooff[k]-128)/sizeof(float);
        double sum_sim=0.0; long long count=0;
        #pragma omp parallel for collapse(2) reduction(+:sum_sim,count) schedule(static)
        for(int i=0;i<static_cast<int>(H);++i) for(int j=0;j<static_cast<int>(W);++j) {
            const size_t n=static_cast<size_t>(i)*W+j;
            bool center_valid=true;
            for(uint32_t c=0;c<channels;++c) if(!std::isfinite(eg.values[static_cast<size_t>(c)*H*W+n])) { center_valid=false; break; }
            float sim=0.0f,conf=0.0f;
            if(center_valid && target_octave_valid) {
                const uint32_t r0=static_cast<uint32_t>(std::max(0,i-r)), c0=static_cast<uint32_t>(std::max(0,j-r));
                const uint32_t r1=static_cast<uint32_t>(std::min(static_cast<int>(H),i+r+1));
                const uint32_t c1=static_cast<uint32_t>(std::min(static_cast<int>(W),j+r+1));
                float f_valid=1.0f;
                double Dsum=0.0,std_diff_sum=0.0;
                for(uint32_t c=0;c<channels;++c) {
                    const Prefix& p=eg.prefix[c];
                    const double cnt=p.query_valid(r0,c0,r1,c1);
                    const float fv=static_cast<float>(cnt/static_cast<double>(area));
                    if(fv<f_valid) f_valid=fv;
                    const double mean64=cnt>0?p.query_sum(r0,c0,r1,c1)/cnt:0.0;
                    const double m264=cnt>0?p.query_sumsq(r0,c0,r1,c1)/cnt:0.0;
                    const float stable_std=static_cast<float>(std::sqrt(std::max(0.0,m264-mean64*mean64)));
                    const float local_tex=static_cast<float>(p.query_texture(r0,c0,r1,c1)/area);
                    float wbuf[kMaxWindowCells]; int wn=0;
                    float moments[kMaxWindowCells],squares[kMaxWindowCells]; int moment_count=0;
                    const size_t ch_off=static_cast<size_t>(c)*H*W;
                    for(int wi=-r;wi<=r;++wi) for(int wj=-r;wj<=r;++wj) {
                        const int ii=i+wi,jj=j+wj;
                        float v=0.0f;
                        if(ii>=0 && ii<static_cast<int>(H) && jj>=0 && jj<static_cast<int>(W)) {
                            v=eg.values[ch_off+static_cast<size_t>(ii)*W+jj];
                            if(std::isfinite(v)) wbuf[wn++]=v;
                            else v=0.0f;
                        }
                        moments[moment_count]=v; squares[moment_count]=v*v; ++moment_count;
                    }
                    const float parity_sum=numpy_pairwise_sum_f32(moments,static_cast<size_t>(area));
                    const float parity_sumsq=numpy_pairwise_sum_f32(squares,static_cast<size_t>(area));
                    const double parity_mean=cnt>0?static_cast<double>(parity_sum)/cnt:0.0;
                    const double parity_m2=cnt>0?static_cast<double>(parity_sumsq)/cnt:0.0;
                    const float local_std=static_cast<float>(std::sqrt(std::max(0.0,parity_m2-parity_mean*parity_mean)));
                    (void)stable_std;
                    double w1=0.0;
                    if(wn>0) {
                        static const double ps[5]={0.10,0.25,0.50,0.75,0.90};
                        double quantiles[5]; quantiles_select(wbuf,wn,ps,quantiles);
                        for(int q=0;q<5;++q) w1+=std::fabs(quantiles[q]-sig[c].quantile[q]);
                        w1/=5.0;
                    }
                    const double deltaE=std::fabs(static_cast<double>(local_tex)-sig[c].texture)
                                        /(static_cast<double>(local_tex)+sig[c].texture+1e-6);
                    Dsum+=0.75*w1+0.25*deltaE;
                    std_diff_sum+=std::fabs(static_cast<double>(local_std)-sig[c].std);
                }
                if(f_valid>=0.25f) {
                    const double D=Dsum/static_cast<double>(channels);
                    sim=static_cast<float>(std::exp(-D));
                    conf=static_cast<float>(f_valid/(1.0+std_diff_sum/static_cast<double>(channels)));
                    sim=std::max(0.0f,std::min(1.0f,sim));
                    conf=std::max(0.0f,std::min(1.0f,conf));
                }
            }
            out[outoff+n]=sim;
            out[outoff+static_cast<size_t>(H)*W+n]=conf;
            if(conf>0.0f) { sum_sim+=sim; ++count; }
        }
        if(count>0) octave_means[k]=sum_sim/static_cast<double>(count);
    }

    double si=1.0;
    if(octaves>1) {
        double mean=0.0; for(uint32_t k=0;k<octaves;++k) mean+=octave_means[k]; mean/=octaves;
        double var=0.0; for(uint32_t k=0;k<octaves;++k) { const double d=octave_means[k]-mean; var+=d*d; }
        si=std::max(0.0,std::min(1.0,1.0-std::sqrt(var/octaves)));
    }
    std::ostringstream json; json<<std::setprecision(17);
    json<<"{\n  \"scale_invariance_index\": "<<si<<",\n  \"channel_residuals\": {";
    for(uint32_t c=0;c<raw_channels;++c) {
        const double pooled=std::sqrt(eraw[c].variance+traw[c].variance+1e-12);
        const double zdiv=pooled>0.0?(eraw[c].mean-traw[c].mean)/pooled:0.0;
        if(c) json<<",";
        json<<"\n    \"ch"<<c<<"\": {\"earth_mean\": "<<eraw[c].mean<<", \"target_mean\": "<<traw[c].mean<<", \"z_divergence\": "<<zdiv<<"}";
    }
    if(raw_channels) json<<"\n  ";
    json<<"},\n  \"physical_breakdown_flags\": [";
    bool first=true;
    auto flag=[&](const std::string& text){ if(!first) json<<","; json<<"\n    "<<text; first=false; };
    const double gravity_factor=eh->gravity_ms2!=0.0f?static_cast<double>(th->gravity_ms2)/eh->gravity_ms2:1.0;
    flag("{\"flag\": \"GRAVITY_SCALING\", \"gravity_scaling_factor\": "+std::to_string(gravity_factor)+"}");
    flag("{\"flag\": \"ATMOSPHERE_GAP\", \"atmospheric_pressure_gap_pa\": "+std::to_string(std::fabs(eh->surface_pressure_pa-th->surface_pressure_pa))+"}");
    flag("{\"flag\": \"RADIATION_DELTA\", \"radiation_delta_msv_yr\": "+std::to_string(std::fabs(eh->radiation_msv_yr-th->radiation_msv_yr))+"}");
    switch(cfg.kind) {
        case Kind::Topography:
            if(th->body==2 && eh->body==1) flag("{\"flag\": \"NO_ATMOSPHERE_TARGET\", \"details\": \"Target body has no atmosphere; convective heat loss absent.\"}");
            break;
        case Kind::Mineralogy: {
            double ndvi=0.0;
            if(th->num_channels>7 && target_stat_channels>7 && traw[7].count) ndvi=traw[7].mean;
            if(th->body==2) {
                std::ostringstream s; s<<std::setprecision(17)<<"{\"flag\": \"BIOSPHERE_OVERPRINT\", \"biosphere_overprint\": "<<(ndvi>0.15?"true":"false")
                    <<", \"details\": \"Moon: NDVI mean "<<ndvi<<(ndvi>0.15?" > ":" <= ")<<"0.15.\"}";
                flag(s.str());
            } else if(ndvi>0.25) {
                std::ostringstream s; s<<std::setprecision(17)<<"{\"flag\": \"BIOSPHERE_OVERPRINT\", \"biosphere_overprint\": true, \"details\": \"Mars: dense vegetation NDVI "<<ndvi<<" > 0.25.\"}";
                flag(s.str());
            } else {
                std::ostringstream s; s<<std::setprecision(17)<<"{\"flag\": \"ASTROBIOLOGY_EXTREMOPHILE_ANALOG\", \"biosphere_overprint\": false, \"details\": \"Mars: "<<(ndvi>0.05?"sparse microbial analog":"no biosphere overprint")<<" (NDVI "<<ndvi<<").\"}";
                flag(s.str());
            }
            break;
        }
        case Kind::Thermal: {
            const double floor_delta=(raw_channels>1?eraw[1].mean-traw[1].mean:0.0);
            std::ostringstream s; s<<std::setprecision(17)<<"{\"flag\": \"CRYOGENIC_FLOOR_DELTA\", \"thermal_floor_delta_k\": "<<floor_delta
                <<", \"details\": \"Earth T_min - Target T_min = "<<floor_delta<<" K.\"}";
            flag(s.str());
            flag("{\"flag\": \"THERMAL_TEST_CHAMBER_CORRECTION\", \"details\": \"Apply thermal vacuum chamber correction for radiative-vs-convective heat loss ratio.\"}");
            break;
        }
        case Kind::Granular:
            flag("{\"flag\": \"GRAVITY_ADJUSTED_SALTATION\", \"gravity_scaling_factor\": "+std::to_string(gravity_factor)+", \"details\": \"Fluid threshold friction velocity u*t scales with sqrt(g).\"}");
            break;
        case Kind::Volatiles:
            flag("{\"flag\": \"SUBSURFACE_VOID_SCORING\", \"details\": \"Combine negative Bouguer anomalies, steep pit walls (>45 deg), and diurnal thermal damping at pit floors for lava-tube candidate scoring.\"}");
            break;
    }
    json<<"\n  ]\n}\n";
    if(breakdown_path) {
        FILE* f=std::fopen(breakdown_path,"w");
        if(!f) { munmap(omap,op); return -8; }
        const std::string data=json.str(); std::fwrite(data.data(),1,data.size(),f); std::fclose(f);
    }
    msync(omap,op,MS_SYNC); munmap(omap,op);
    return 0;
}
} // namespace distribution_v2
#endif
