BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE product_variants (
    id VARCHAR(80) NOT NULL, 
    category VARCHAR(20) NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    version VARCHAR(160) NOT NULL, 
    data JSON NOT NULL, 
    mode VARCHAR(12) NOT NULL, 
    reviewed VARCHAR(20) NOT NULL, 
    price_observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_product_variants_category ON product_variants (category);

CREATE INDEX ix_product_variants_mode ON product_variants (mode);

CREATE TABLE anonymous_sessions (
    id VARCHAR(36) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (token_hash)
);

CREATE TABLE requirement_revisions (
    id VARCHAR(36) NOT NULL, 
    session_id VARCHAR(36) NOT NULL, 
    base_id VARCHAR(36), 
    data JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES anonymous_sessions (id)
);

CREATE INDEX ix_requirement_revisions_session_id ON requirement_revisions (session_id);

CREATE TABLE operation_runs (
    id VARCHAR(36) NOT NULL, 
    session_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    idempotency_key VARCHAR(100) NOT NULL, 
    input_hash VARCHAR(64) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    stage VARCHAR(80) NOT NULL, 
    output JSON, 
    error JSON, 
    result_id VARCHAR(36), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (session_id, idempotency_key), 
    FOREIGN KEY(session_id) REFERENCES anonymous_sessions (id)
);

CREATE INDEX ix_operation_runs_session_id ON operation_runs (session_id);

CREATE INDEX ix_operation_runs_status ON operation_runs (status);

CREATE TABLE recommendation_snapshots (
    id VARCHAR(36) NOT NULL, 
    session_id VARCHAR(36) NOT NULL, 
    run_id VARCHAR(36) NOT NULL, 
    requirement_id VARCHAR(36) NOT NULL, 
    data JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES anonymous_sessions (id), 
    UNIQUE (run_id), 
    FOREIGN KEY(run_id) REFERENCES operation_runs (id), 
    FOREIGN KEY(requirement_id) REFERENCES requirement_revisions (id)
);

CREATE INDEX ix_recommendation_snapshots_session_id ON recommendation_snapshots (session_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

