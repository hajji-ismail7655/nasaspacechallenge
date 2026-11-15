#ifndef TOPOGRAPHY_H
#define TOPOGRAPHY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
int32_t run_module(const char* earth_ptile_path,
                   const char* target_ptile_path,
                   const char* out_hmap_path,
                   const char* out_breakdown_json_path);
#ifdef __cplusplus
}
#endif

#endif /* TOPOGRAPHY_H */
