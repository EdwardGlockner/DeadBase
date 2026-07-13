CREATE TABLE IF NOT EXISTS player_profile (
    account_id INTEGER PRIMARY KEY,
    primary_heroes_json TEXT NOT NULL DEFAULT '[]',
    secondary_heroes_json TEXT NOT NULL DEFAULT '[]',
    playstyle_json TEXT NOT NULL DEFAULT '{}',
    coaching_goals_json TEXT NOT NULL DEFAULT '[]',
    recurring_issues_json TEXT NOT NULL DEFAULT '[]',
    preferences_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS linked_account (
    account_id INTEGER PRIMARY KEY,
    persona_name TEXT NOT NULL,
    profile_url TEXT,
    avatar_url TEXT,
    country_code TEXT,
    matches_played_last_30d INTEGER,
    last_team_avg_badge INTEGER,
    raw_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_experiment (
    experiment_id TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL,
    hero_id INTEGER,
    hypothesis TEXT NOT NULL,
    branch_a_json TEXT NOT NULL,
    branch_b_json TEXT NOT NULL,
    evaluation_window TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS coaching_note (
    note_id TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL,
    hero_id INTEGER,
    note_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS preference (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
