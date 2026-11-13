#include "volatiles_subsurface.h"
#include "distribution_v2.hpp"

static const distribution_v2::Config kConfig = {
    distribution_v2::Kind::Volatiles,
    "volatiles_subsurface",
    5,
    {5.0, 1.0, 3.0, 0.0, 2.0, 0.0, 0.0, 0.0},
    {5.0, 1.0, 2.0, 50.0, 2.0, 1.0, 1.0, 1.0},
    false
};

extern "C" int32_t run_module(const char* earth_ptile_path,
                               const char* target_ptile_path,
                               const char* out_hmap_path,
                               const char* out_breakdown_json_path) {
    return distribution_v2::run(earth_ptile_path, target_ptile_path,
                                out_hmap_path, out_breakdown_json_path, kConfig);
}
