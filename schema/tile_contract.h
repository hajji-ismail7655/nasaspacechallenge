#ifndef TILE_CONTRACT_H
#define TILE_CONTRACT_H

#include <stdint.h>

#define PTIL_MAGIC 0x4C495450U /* "PTIL" little-endian */
#define HMAP_MAGIC 0x50414D48U /* "HMAP" little-endian */
#define CONTRACT_VERSION 1U

typedef enum {
    BODY_EARTH = 1,
    BODY_MOON  = 2,
    BODY_MARS  = 3
} PlanetaryBody;

typedef enum {
    DOMAIN_TOPOGRAPHY           = 1,
    DOMAIN_MINERALOGY           = 2,
    DOMAIN_THERMAL_ILLUMINATION = 3,
    DOMAIN_GRANULAR_AEOLIAN     = 4,
    DOMAIN_VOLATILES_SUBSURFACE = 5
} FeatureDomain;

/* 128-byte fixed header at byte offset 0 of every .ptile and .hmap file */
typedef struct __attribute__((aligned(64))) {
    uint32_t magic;              /* PTIL_MAGIC or HMAP_MAGIC */
    uint32_t version;            /* CONTRACT_VERSION */
    uint32_t body;               /* PlanetaryBody enum */
    uint32_t domain;             /* FeatureDomain enum */
    uint32_t num_octaves;        /* Number of scale-space octaves (default: 5) */
    uint32_t num_channels;       /* Feature channels per octave */
    uint32_t base_height;        /* Height in pixels at octave 0 */
    uint32_t base_width;         /* Width in pixels at octave 0 */
    double   base_resolution_m;  /* Meters per pixel at octave 0 (e.g., 30.0) */
    double   center_lat_deg;     /* Planetocentric latitude of tile center */
    double   center_lon_deg;     /* Planetocentric longitude (0-360 E) */
    float    nodata_value;       /* Canonical NaN/nodata sentinel (-9999.0f) */
    float    gravity_ms2;        /* 9.80665 (Earth), 1.622 (Moon), 3.72076 (Mars) */
    float    surface_pressure_pa;/* 101325.0 (Earth), 3e-10 (Moon), 610.0 (Mars) */
    float    radiation_msv_yr;   /* Baseline surface ionizing dose rate */
    uint8_t  reserved[40];       /* Zero-padded to 128 bytes */
} TileBinaryHeader;

/*
 * Payload Layout immediately following the 128-byte header:
 * For octave k in [0 .. num_octaves - 1]:
 *   H_k = base_height >> k
 *   W_k = base_width  >> k
 *   Block size = num_channels * H_k * W_k * sizeof(float)
 *   Memory order: C-contiguous [octave][channel][row][col], IEEE-754 float32
 */

#endif /* TILE_CONTRACT_H */
EOF