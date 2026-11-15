#include "topography.h"
#include "distribution_v2.hpp"

static const distribution_v2::Config kConfig = {
    distribution_v2::Kind::Topography,
    "topography",
    6,
    {500.0, 15.0, 180.0, 50.0, 0.0, 0.0, 0.0, 0.0},
    {1000.0, 15.0, 103.9, 50.0, 50.0, 0.01, 0.5, 1.0},
    true
};

extern "C" int32_t run_module(const char* earth_ptile_path,
                               const char* target_ptile_path,
                               const char* out_hmap_path,
                               const char* out_breakdown_json_path) {
    return distribution_v2::run(earth_ptile_path, target_ptile_path,
                                out_hmap_path, out_breakdown_json_path, kConfig);
}
