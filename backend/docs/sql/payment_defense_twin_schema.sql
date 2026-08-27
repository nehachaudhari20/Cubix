-- Payment Defense Twin — PostgreSQL-ready schema
-- JSON remains the development source of truth for the Knowledge Base.
-- Load these tables later; do not mix domains.

-- ============================================================
-- A. KNOWLEDGE BASE
-- ============================================================

CREATE TABLE IF NOT EXISTS kb_attack_families (
    attack_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    objective TEXT,
    attacker TEXT,
    target TEXT,
    lifecycle_stage_id TEXT,
    traditional_mechanism TEXT,
    genai_classification TEXT CHECK (genai_classification IN ('traditional', 'genai_amplified', 'genai_load_bearing', 'unknown')),
    genai_load_bearing BOOLEAN,
    genai_transformation TEXT,
    simulation_type TEXT,
    simulation_template_id TEXT,
    sandbox_executable BOOLEAN,
    confidence TEXT,
    maturity TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_attack_variants (
    variant_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES kb_attack_families (attack_id),
    name TEXT NOT NULL,
    slug TEXT,
    origin TEXT NOT NULL CHECK (origin IN ('source_backed', 'implementation_derived')),
    origin_note TEXT,
    sandbox_executable BOOLEAN,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_attack_vectors (
    vector_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES kb_attack_families (attack_id),
    variant_id TEXT REFERENCES kb_attack_variants (variant_id),
    simulation_template_id TEXT,
    sandbox_executable BOOLEAN,
    origin TEXT CHECK (origin IN ('source_backed', 'implementation_derived')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_signals (
    signal_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    description TEXT,
    false_positive_risk TEXT,
    cross_account_needed BOOLEAN,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_controls (
    control_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_lifecycle_stages (
    stage_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sequence INTEGER,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_relationships (
    relationship_id TEXT PRIMARY KEY,
    from_ref TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    to_ref TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_simulation_templates (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    campaign_pattern TEXT,
    origin TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_simulation_parameters (
    parameter_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    value_type TEXT,
    attacker_controllable BOOLEAN,
    origin TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_state_requirements (
    requirement_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_legitimate_counterparts (
    counterpart_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    origin TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_genai_capabilities (
    capability_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb_signal_feature_mappings (
    mapping_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES kb_signals (signal_id),
    feature_names JSONB NOT NULL,
    origin TEXT,
    confidence TEXT
);

CREATE TABLE IF NOT EXISTS kb_evidence (
    evidence_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    locator TEXT,
    excerpt TEXT,
    confidence TEXT,
    maturity TEXT
);

CREATE TABLE IF NOT EXISTS kb_family_variant (
    family_id TEXT NOT NULL REFERENCES kb_attack_families (attack_id),
    variant_id TEXT NOT NULL REFERENCES kb_attack_variants (variant_id),
    PRIMARY KEY (family_id, variant_id)
);

CREATE TABLE IF NOT EXISTS kb_family_signal (
    family_id TEXT NOT NULL REFERENCES kb_attack_families (attack_id),
    signal_id TEXT NOT NULL REFERENCES kb_signals (signal_id),
    PRIMARY KEY (family_id, signal_id)
);

CREATE TABLE IF NOT EXISTS kb_family_control (
    family_id TEXT NOT NULL REFERENCES kb_attack_families (attack_id),
    control_id TEXT NOT NULL REFERENCES kb_controls (control_id),
    PRIMARY KEY (family_id, control_id)
);

CREATE TABLE IF NOT EXISTS kb_family_capability (
    family_id TEXT NOT NULL REFERENCES kb_attack_families (attack_id),
    capability_id TEXT NOT NULL REFERENCES kb_genai_capabilities (capability_id),
    PRIMARY KEY (family_id, capability_id)
);

-- ============================================================
-- B. SANDBOX STATE (mutable runtime)
-- ============================================================

CREATE TABLE IF NOT EXISTS sandbox_customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT,
    pan TEXT,
    dob TEXT,
    address TEXT,
    created_at TIMESTAMPTZ,
    verified BOOLEAN,
    trust_score DOUBLE PRECISION,
    account_age_days INTEGER,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS sandbox_devices (
    device_id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES sandbox_customers (customer_id),
    fingerprint JSONB,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    is_known BOOLEAN
);

CREATE TABLE IF NOT EXISTS sandbox_accounts (
    account_id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES sandbox_customers (customer_id),
    balance DOUBLE PRECISION,
    created_at TIMESTAMPTZ,
    is_active BOOLEAN,
    daily_limit DOUBLE PRECISION,
    monthly_limit DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS sandbox_merchants (
    merchant_id TEXT PRIMARY KEY,
    name TEXT,
    mcc TEXT,
    declared_mcc TEXT,
    risk_score DOUBLE PRECISION,
    kyb_verified BOOLEAN,
    created_at TIMESTAMPTZ,
    owner_customer_id TEXT,
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS sandbox_beneficiaries (
    beneficiary_id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES sandbox_customers (customer_id),
    name TEXT,
    account_ref TEXT,
    created_at TIMESTAMPTZ,
    is_verified BOOLEAN,
    risk_score DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS sandbox_transactions (
    transaction_id TEXT PRIMARY KEY,
    customer_id TEXT,
    device_id TEXT,
    account_id TEXT,
    merchant_id TEXT,
    beneficiary_id TEXT,
    amount DOUBLE PRECISION,
    currency TEXT,
    payment_rail TEXT,
    occurred_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- ============================================================
-- C. EXPERIMENT / OBSERVATION (immutable)
-- ============================================================

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    campaign_id TEXT,
    loop_run_id TEXT,
    environment_version TEXT,
    model_version TEXT,
    sandbox_state_ref TEXT,
    status TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS attack_instances (
    instance_id TEXT PRIMARY KEY,
    vector_id TEXT,
    family_id TEXT,
    variant_id TEXT,
    experiment_id TEXT REFERENCES experiments (experiment_id),
    campaign_id TEXT,
    concrete_entities JSONB,
    concrete_parameters JSONB,
    generated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    experiment_id TEXT REFERENCES experiments (experiment_id),
    campaign_id TEXT,
    attack_vector_id TEXT,
    attack_instance_id TEXT,
    attack_family_id TEXT,
    transaction_id TEXT,
    action_type TEXT NOT NULL,
    decision TEXT NOT NULL,
    outcome TEXT,
    reason TEXT,
    ml_score DOUBLE PRECISION,
    unified_risk DOUBLE PRECISION,
    model_version TEXT,
    environment_version TEXT,
    features JSONB,
    controls_triggered JSONB,
    state_before JSONB,
    state_after JSONB,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Existing platform tables remain: loop_runs, campaign_events, scheduler_config

-- ============================================================
-- D. RED MEMORY (environment-specific, not taxonomy)
-- ============================================================

CREATE TABLE IF NOT EXISTS red_memory (
    memory_id TEXT PRIMARY KEY,
    environment_version TEXT,
    model_version TEXT,
    vector_id TEXT,
    family_id TEXT,
    context TEXT NOT NULL,
    observed_control TEXT,
    response TEXT,
    attack_attempted TEXT,
    evidence_count INTEGER,
    confidence DOUBLE PRECISION,
    last_validated TIMESTAMPTZ
);

-- ============================================================
-- E. ADVERSARIAL BUFFER / TRAINING / MODEL REGISTRY
-- ============================================================

CREATE TABLE IF NOT EXISTS adversarial_examples (
    evidence_id TEXT PRIMARY KEY,
    observation_id TEXT,
    campaign_id TEXT,
    attack_family TEXT,
    attack_variant TEXT,
    sandbox_decision TEXT,
    evasion_outcome TEXT,
    label INTEGER,
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    selection_reason TEXT,
    features JSONB,
    created_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS training_datasets (
    dataset_version TEXT PRIMARY KEY,
    parent_dataset_version TEXT,
    created_at TIMESTAMPTZ,
    sources JSONB,
    selection_policy TEXT,
    feature_version TEXT,
    row_manifest_path TEXT
);

CREATE TABLE IF NOT EXISTS model_versions (
    model_version TEXT PRIMARY KEY,
    parent_model_version TEXT,
    dataset_version TEXT,
    feature_version TEXT,
    algorithm TEXT,
    training_config JSONB,
    metrics JSONB,
    evaluation_run_id TEXT,
    deployment_status TEXT CHECK (deployment_status IN ('candidate', 'active', 'retired', 'rejected')),
    artifact_path TEXT NOT NULL,
    created_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    evaluation_run_id TEXT PRIMARY KEY,
    model_version TEXT REFERENCES model_versions (model_version),
    dataset_version TEXT,
    metrics JSONB,
    created_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_observations_experiment ON observations (experiment_id);
CREATE INDEX IF NOT EXISTS idx_observations_vector ON observations (attack_vector_id);
CREATE INDEX IF NOT EXISTS idx_instances_vector ON attack_instances (vector_id);
CREATE INDEX IF NOT EXISTS idx_variants_family ON kb_attack_variants (family_id);
CREATE INDEX IF NOT EXISTS idx_vectors_family ON kb_attack_vectors (family_id);
