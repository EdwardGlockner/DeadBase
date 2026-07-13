CREATE TABLE IF NOT EXISTS source_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    request_url TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    raw_path TEXT NOT NULL,
    content_type TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_snapshot_lookup
    ON source_snapshot(provider, entity_type, entity_key, fetched_at DESC);

CREATE TABLE IF NOT EXISTS patch_event (
    patch_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT NOT NULL,
    link TEXT NOT NULL,
    source_guid TEXT,
    content_hash TEXT NOT NULL,
    snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
    content_excerpt TEXT
);

CREATE TABLE IF NOT EXISTS player_match (
    match_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    hero_id INTEGER NOT NULL,
    hero_level INTEGER,
    start_time INTEGER NOT NULL,
    game_mode INTEGER NOT NULL,
    match_mode INTEGER NOT NULL,
    player_team INTEGER NOT NULL,
    kills INTEGER NOT NULL,
    deaths INTEGER NOT NULL,
    assists INTEGER NOT NULL,
    denies INTEGER NOT NULL,
    net_worth INTEGER NOT NULL,
    last_hits INTEGER NOT NULL,
    team_abandoned INTEGER,
    abandoned_time_s INTEGER,
    match_duration_s INTEGER NOT NULL,
    match_result INTEGER NOT NULL,
    won INTEGER,
    snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
    raw_json TEXT NOT NULL,
    PRIMARY KEY (match_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_player_match_account_time
    ON player_match(account_id, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_player_match_hero_time
    ON player_match(hero_id, start_time DESC);

CREATE TABLE IF NOT EXISTS match_metadata (
    match_id INTEGER PRIMARY KEY,
    duration_s INTEGER,
    winning_team INTEGER,
    match_outcome INTEGER,
    snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_participant (
    match_id INTEGER NOT NULL REFERENCES match_metadata(match_id) ON DELETE CASCADE,
    player_slot INTEGER NOT NULL,
    account_id INTEGER,
    hero_id INTEGER,
    team INTEGER,
    won INTEGER,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (match_id, player_slot)
);

CREATE TABLE IF NOT EXISTS item_purchase (
    match_id INTEGER NOT NULL REFERENCES match_metadata(match_id) ON DELETE CASCADE,
    player_slot INTEGER NOT NULL,
    purchase_index INTEGER NOT NULL,
    account_id INTEGER,
    item_id INTEGER NOT NULL,
    upgrade_id INTEGER,
    bought_at_s INTEGER NOT NULL,
    sold_at_s INTEGER,
    imbued_ability_id INTEGER,
    flags INTEGER,
    upgrade_info INTEGER,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (match_id, player_slot, purchase_index)
);

CREATE INDEX IF NOT EXISTS idx_item_purchase_account
    ON item_purchase(account_id, item_id, bought_at_s);

CREATE TABLE IF NOT EXISTS stat_bucket (
    match_id INTEGER NOT NULL REFERENCES match_metadata(match_id) ON DELETE CASCADE,
    player_slot INTEGER NOT NULL,
    bucket_index INTEGER NOT NULL,
    account_id INTEGER,
    time_stamp_s INTEGER NOT NULL,
    net_worth INTEGER,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    denies INTEGER,
    creep_kills INTEGER,
    player_damage INTEGER,
    player_damage_taken INTEGER,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (match_id, player_slot, bucket_index)
);

CREATE INDEX IF NOT EXISTS idx_stat_bucket_account
    ON stat_bucket(account_id, time_stamp_s);

CREATE TABLE IF NOT EXISTS leaderboard_snapshot_entry (
    snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id) ON DELETE CASCADE,
    region TEXT NOT NULL,
    rank INTEGER NOT NULL,
    account_name TEXT NOT NULL,
    candidate_account_ids_json TEXT NOT NULL,
    top_hero_ids_json TEXT NOT NULL,
    badge_level INTEGER NOT NULL,
    ranked_rank INTEGER,
    ranked_subrank INTEGER,
    PRIMARY KEY (snapshot_id, rank, account_name)
);

CREATE TABLE IF NOT EXISTS analytics_snapshot (
    snapshot_id INTEGER PRIMARY KEY REFERENCES source_snapshot(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    query_fingerprint TEXT NOT NULL,
    query_params_json TEXT NOT NULL,
    coverage_start INTEGER,
    coverage_end INTEGER,
    patch_window_label TEXT
);

CREATE TABLE IF NOT EXISTS hero_analytics_stat (
    snapshot_id INTEGER NOT NULL REFERENCES analytics_snapshot(snapshot_id) ON DELETE CASCADE,
    hero_id INTEGER NOT NULL,
    bucket TEXT,
    matches INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    total_kills INTEGER,
    total_deaths INTEGER,
    total_assists INTEGER,
    total_net_worth INTEGER,
    total_last_hits INTEGER,
    total_denies INTEGER,
    total_player_damage INTEGER,
    total_player_damage_taken INTEGER,
    total_boss_damage INTEGER,
    total_creep_damage INTEGER,
    total_neutral_damage INTEGER,
    total_max_health INTEGER,
    total_shots_hit INTEGER,
    total_shots_missed INTEGER,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, hero_id, bucket)
);

CREATE INDEX IF NOT EXISTS idx_hero_analytics_stat_snapshot
    ON hero_analytics_stat(snapshot_id, matches DESC, hero_id);

CREATE TABLE IF NOT EXISTS item_analytics_stat (
    snapshot_id INTEGER NOT NULL REFERENCES analytics_snapshot(snapshot_id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL,
    bucket TEXT,
    matches INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    purchases INTEGER,
    players INTEGER,
    avg_bought_at_s REAL,
    total_bought_at_s REAL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, item_id, bucket)
);

CREATE INDEX IF NOT EXISTS idx_item_analytics_stat_snapshot
    ON item_analytics_stat(snapshot_id, matches DESC, item_id);

CREATE TABLE IF NOT EXISTS item_flow_summary (
    snapshot_id INTEGER NOT NULL REFERENCES analytics_snapshot(snapshot_id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    matches INTEGER NOT NULL,
    players INTEGER,
    total_kills INTEGER,
    total_deaths INTEGER,
    total_assists INTEGER,
    avg_net_worth REAL,
    avg_duration_s REAL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, scope)
);

CREATE TABLE IF NOT EXISTS item_flow_reach (
    snapshot_id INTEGER NOT NULL REFERENCES analytics_snapshot(snapshot_id) ON DELETE CASCADE,
    column_index INTEGER NOT NULL,
    reached_matches INTEGER NOT NULL,
    PRIMARY KEY (snapshot_id, column_index)
);

CREATE TABLE IF NOT EXISTS item_flow_node (
    snapshot_id INTEGER NOT NULL REFERENCES analytics_snapshot(snapshot_id) ON DELETE CASCADE,
    column_index INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    matches INTEGER NOT NULL,
    players INTEGER,
    total_kills INTEGER,
    total_deaths INTEGER,
    total_assists INTEGER,
    adjusted_win_rate REAL,
    avg_net_worth_at_buy REAL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, column_index, item_id)
);

CREATE INDEX IF NOT EXISTS idx_item_flow_node_snapshot
    ON item_flow_node(snapshot_id, column_index, matches DESC, item_id);

CREATE TABLE IF NOT EXISTS item_flow_edge (
    snapshot_id INTEGER NOT NULL REFERENCES analytics_snapshot(snapshot_id) ON DELETE CASCADE,
    from_column INTEGER NOT NULL,
    from_item_id INTEGER NOT NULL,
    to_item_id INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    matches INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, from_column, from_item_id, to_item_id)
);

CREATE INDEX IF NOT EXISTS idx_item_flow_edge_snapshot
    ON item_flow_edge(snapshot_id, matches DESC, from_column);

CREATE TABLE IF NOT EXISTS player_performance_curve_point (
    snapshot_id INTEGER NOT NULL REFERENCES analytics_snapshot(snapshot_id) ON DELETE CASCADE,
    game_time INTEGER NOT NULL,
    net_worth_avg REAL,
    net_worth_std REAL,
    kills_avg REAL,
    kills_std REAL,
    deaths_avg REAL,
    deaths_std REAL,
    assists_avg REAL,
    assists_std REAL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, game_time)
);

CREATE INDEX IF NOT EXISTS idx_player_performance_curve_snapshot
    ON player_performance_curve_point(snapshot_id, game_time ASC);

CREATE TABLE IF NOT EXISTS artifact_run (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    account_id INTEGER,
    hero_id INTEGER,
    generated_at TEXT NOT NULL,
    source_snapshot_ids_json TEXT NOT NULL,
    patch_context_json TEXT NOT NULL,
    output_path TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
