-- PostgreSQL + PostGIS schema for hosting processed cross-planetary analog datasets
-- and C++20 OptiAlgo discovery sweep results for the standalone WebGIS backend.
-- Binary .ptile / .hmap / pre-rendered RGBA PNG overlays live in object storage (S3/R2/MinIO)
-- and are referenced by URI here.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS targets (
    target_id            TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    body                 TEXT NOT NULL CHECK (body IN ('MOON', 'MARS')),
    lat                  DOUBLE PRECISION NOT NULL,
    lon                  DOUBLE PRECISION NOT NULL,
    gravity_ms2          DOUBLE PRECISION NOT NULL,
    surface_pressure_pa  DOUBLE PRECISION NOT NULL,
    radiation_msv_yr     DOUBLE PRECISION NOT NULL,
    official_portals     JSONB NOT NULL DEFAULT '[]'::jsonb,
    geom                 GEOMETRY(Point, 4326) GENERATED ALWAYS AS (
                             ST_SetSRID(ST_MakePoint(lon, lat), 4326)
                         ) STORED
);

CREATE TABLE IF NOT EXISTS earth_regions (
    site_id              TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    lat                  DOUBLE PRECISION NOT NULL,
    lon                  DOUBLE PRECISION NOT NULL,
    bbox                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_known_analog      BOOLEAN NOT NULL DEFAULT FALSE,
    novelty_weight_150km DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    official_portals     JSONB NOT NULL DEFAULT '[]'::jsonb,
    geom                 GEOMETRY(Point, 4326) GENERATED ALWAYS AS (
                             ST_SetSRID(ST_MakePoint(lon, lat), 4326)
                         ) STORED
);
CREATE INDEX IF NOT EXISTS idx_earth_regions_geom ON earth_regions USING GIST (geom);

CREATE TABLE IF NOT EXISTS known_analogs_mask (
    analog_id            TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    buffer_km            DOUBLE PRECISION NOT NULL DEFAULT 150.0,
    geojson_feature      JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS standardized_tiles (
    tile_id              TEXT PRIMARY KEY,
    body                 TEXT NOT NULL CHECK (body IN ('EARTH', 'MOON', 'MARS')),
    region_or_target_id  TEXT NOT NULL,
    domain               TEXT NOT NULL CHECK (domain IN (
                             'topography', 'mineralogy', 'thermal_illumination',
                             'granular_aeolian', 'volatiles_subsurface'
                         )),
    base_height          INTEGER NOT NULL DEFAULT 512,
    base_width           INTEGER NOT NULL DEFAULT 512,
    base_resolution_m    DOUBLE PRECISION NOT NULL DEFAULT 30.0,
    num_octaves          INTEGER NOT NULL DEFAULT 5,
    num_channels         INTEGER NOT NULL,
    provenance           JSONB NOT NULL DEFAULT '{}'::jsonb,
    ptile_uri            TEXT NOT NULL,
    sha256               TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_std_tiles_lookup ON standardized_tiles (region_or_target_id, domain);

CREATE TABLE IF NOT EXISTS analog_pairs (
    pair_id                   TEXT PRIMARY KEY,
    site_id                   TEXT NOT NULL REFERENCES earth_regions(site_id),
    target_id                 TEXT NOT NULL REFERENCES targets(target_id),
    composite_score           DOUBLE PRECISION NOT NULL,
    novel_composite_score     DOUBLE PRECISION NOT NULL,
    scale_invariance_index    DOUBLE PRECISION NOT NULL,
    novelty_weight            DOUBLE PRECISION NOT NULL,
    domain_scores             JSONB NOT NULL DEFAULT '{}'::jsonb,
    channel_residuals         JSONB NOT NULL DEFAULT '{}'::jsonb,
    physical_breakdown_flags  JSONB NOT NULL DEFAULT '[]'::jsonb,
    operational_test_protocol TEXT NOT NULL DEFAULT '',
    composite_hmap_uri        TEXT NOT NULL DEFAULT '',
    overlay_png_prefix        TEXT NOT NULL DEFAULT '',
    backend                   TEXT NOT NULL DEFAULT 'cpp',
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analog_pairs_novel ON analog_pairs (target_id, novel_composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_analog_pairs_unmasked ON analog_pairs (target_id, composite_score DESC);
