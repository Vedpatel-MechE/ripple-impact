-- RIPPLE hosted schema. Applied idempotently under a Postgres advisory lock.

CREATE TABLE IF NOT EXISTS missions (
    id_hash TEXT PRIMARY KEY,
    view_token_hash TEXT NOT NULL,
    edit_token_hash TEXT NOT NULL,
    state_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
    id_hash TEXT NOT NULL REFERENCES missions(id_hash),
    version INTEGER NOT NULL CHECK (version >= 1),
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (id_hash, version)
);

CREATE TABLE IF NOT EXISTS signals (
    id_hash TEXT PRIMARY KEY,
    owner_token_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'reserved', 'withdrawn')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_events (
    event_id BIGSERIAL PRIMARY KEY,
    id_hash TEXT NOT NULL REFERENCES signals(id_hash),
    event TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assemblies (
    id_hash TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('inviting', 'confirmed', 'declined')),
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL DEFAULT '',
    expired INTEGER NOT NULL DEFAULT 0 CHECK (expired IN (0, 1))
);

CREATE TABLE IF NOT EXISTS assembly_participants (
    assembly_id_hash TEXT NOT NULL REFERENCES assemblies(id_hash),
    role TEXT NOT NULL,
    signal_id_hash TEXT NOT NULL REFERENCES signals(id_hash),
    invite_token_hash TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('pending', 'accepted', 'declined')),
    decided_at TEXT,
    PRIMARY KEY (assembly_id_hash, role)
);

CREATE TABLE IF NOT EXISTS assembly_events (
    event_id BIGSERIAL PRIMARY KEY,
    assembly_id_hash TEXT NOT NULL REFERENCES assemblies(id_hash),
    role TEXT NOT NULL,
    event TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('participant', 'admin')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_events (
    event_id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    event TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_carts (
    id TEXT PRIMARY KEY,
    creator_user_id TEXT NOT NULL REFERENCES users(id),
    mission_slug TEXT NOT NULL,
    group_name TEXT NOT NULL,
    creator_statement TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('impact', 'affordability', 'speed', 'reliability')),
    package_type TEXT NOT NULL CHECK (package_type IN ('starter', 'balanced', 'resilient')),
    package_json TEXT NOT NULL,
    goal_cents INTEGER NOT NULL CHECK (goal_cents BETWEEN 10000 AND 5000000),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'funded', 'closed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS circle_contributions (
    id TEXT PRIMARY KEY,
    cart_id TEXT NOT NULL REFERENCES smart_carts(id),
    display_name TEXT NOT NULL,
    anonymous INTEGER NOT NULL CHECK (anonymous IN (0, 1)),
    amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 100 AND 5000000),
    message TEXT NOT NULL DEFAULT '',
    payment_status TEXT NOT NULL CHECK (payment_status = 'sandbox-authorized'),
    gateway_reference TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS smart_cart_events (
    event_id BIGSERIAL PRIMARY KEY,
    cart_id TEXT NOT NULL REFERENCES smart_carts(id),
    event TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_intakes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('company', 'recipient', 'repairer')),
    payload_json TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status = 'unverified'),
    created_at TEXT NOT NULL,
    user_id TEXT REFERENCES users(id),
    workflow_status TEXT NOT NULL DEFAULT 'submitted'
        CHECK (workflow_status IN ('submitted', 'reviewing', 'needs-information', 'approved', 'declined')),
    review_notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS intake_events (
    event_id BIGSERIAL PRIMARY KEY,
    intake_id TEXT NOT NULL REFERENCES role_intakes(id),
    event TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulated_pledges (
    id TEXT PRIMARY KEY,
    mission_slug TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 100 AND 10000000),
    display_name TEXT NOT NULL,
    anonymous INTEGER NOT NULL CHECK (anonymous IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'simulated' CHECK (status = 'simulated'),
    created_at TEXT NOT NULL,
    user_id TEXT REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS pledge_events (
    event_id BIGSERIAL PRIMARY KEY,
    pledge_id TEXT NOT NULL REFERENCES simulated_pledges(id),
    event TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS request_limits (
    key_hash TEXT PRIMARY KEY,
    event_count INTEGER NOT NULL CHECK (event_count >= 1),
    window_started INTEGER NOT NULL
);

CREATE OR REPLACE FUNCTION ripple_prevent_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only records are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION ripple_decision_once() RETURNS trigger AS $$
BEGIN
    IF OLD.decision <> 'pending' THEN
        RAISE EXCEPTION 'participant decisions are final';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION ripple_expired_once() RETURNS trigger AS $$
BEGIN
    IF OLD.expired = 1 AND NEW.expired <> 1 THEN
        RAISE EXCEPTION 'expired invitations cannot be reactivated';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    CREATE TRIGGER revisions_no_update BEFORE UPDATE ON revisions
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER revisions_no_delete BEFORE DELETE ON revisions
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER signal_events_no_update BEFORE UPDATE ON signal_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER signal_events_no_delete BEFORE DELETE ON signal_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER assembly_events_no_update BEFORE UPDATE ON assembly_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER assembly_events_no_delete BEFORE DELETE ON assembly_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER intake_events_no_update BEFORE UPDATE ON intake_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER intake_events_no_delete BEFORE DELETE ON intake_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER pledge_events_no_update BEFORE UPDATE ON pledge_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER pledge_events_no_delete BEFORE DELETE ON pledge_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER auth_events_no_update BEFORE UPDATE ON auth_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER auth_events_no_delete BEFORE DELETE ON auth_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER smart_cart_events_no_update BEFORE UPDATE ON smart_cart_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER smart_cart_events_no_delete BEFORE DELETE ON smart_cart_events
        FOR EACH ROW EXECUTE FUNCTION ripple_prevent_mutation();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER assembly_decision_once BEFORE UPDATE OF decision ON assembly_participants
        FOR EACH ROW EXECUTE FUNCTION ripple_decision_once();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER assembly_expired_once BEFORE UPDATE OF expired ON assemblies
        FOR EACH ROW EXECUTE FUNCTION ripple_expired_once();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
