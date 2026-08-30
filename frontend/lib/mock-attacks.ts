/**
 * Mock novel attack payloads for the Attacker Designer.
 * 10 realistic scenarios — frontend-only, no backend required.
 */

export interface MockAttack {
  name: string
  primary_family: string
  novelty_score: number
  success_probability: number
  target_stages: string[]
  attack_flow: string[]
  evasion_technique: string
  controls_targeted: string[]
  blue_team_recommendation: string
  payload: Record<string, any>
}

export interface MockAttackResult {
  num_generated: number
  model: string
  elapsed_seconds: number
  focus_area: string
  attacks: MockAttack[]
  raw_response?: string
}

export const MOCK_ATTACKS: MockAttack[] = [
  {
    name: "AI-Agent Split-Payment Relay",
    primary_family: "ai-agent-payment-fraud",
    novelty_score: 0.91,
    success_probability: 0.73,
    target_stages: ["payment_authorization", "settlement", "dispute"],
    attack_flow: [
      "Spawn 12 concurrent AI agents with unique device fingerprints",
      "Each agent creates a micro-payment (₹1-₹50) to a relay merchant",
      "Relay merchant batches payments into a single settlement batch exceeding velocity limits",
      "Agents coordinate timing to avoid per-user velocity rules",
      "Final settlement triggers payout to attacker-controlled bank account",
    ],
    evasion_technique:
      "Distributed micro-amounts stay below per-transaction ML thresholds; relay merchant has 6-month clean history; agent fingerprints rotate via VM snapshots",
    controls_targeted: [
      "velocity_check",
      "device_fingerprint",
      "merchant_risk_score",
      "amount_threshold",
    ],
    blue_team_recommendation:
      "Implement cross-agent correlation: flag when >5 unique device fingerprints converge on a single merchant within 60s. Add relay merchant velocity aggregation across sub-accounts.",
    payload: {
      agents: 12,
      per_agent_amount_range: [1, 50],
      relay_merchant_id: "MERCH_RELAY_001",
      coordination_interval_ms: 500,
      settlement_batch_size: 600,
      target_payout: "ATTACKER_BANK_ACCT",
    },
  },
  {
    name: "Synthetic Identity Dormancy Harvest",
    primary_family: "synthetic-identity-attacks",
    novelty_score: 0.87,
    success_probability: 0.65,
    target_stages: ["identity_verification", "account_creation", "credit_assessment"],
    attack_flow: [
      "Generate 200 synthetic identities using GAN-combined real SSN fragments + fake names",
      "Open small credit-builder accounts (₹500 limit) at 15 different lenders",
      "Make 8 months of minimum payments from a funded mule account",
      "Request credit limit increases to ₹50,000-₹2,00,000",
      "Max all limits simultaneously and go silent",
    ],
    evasion_technique:
      "Build genuine credit history over 8 months; payment patterns mimic real users; identities pass standard KYC checks; GAN faces bypass liveness detection",
    controls_targeted: [
      "identity_verification",
      "credit_scoring",
      "velocity_new_accounts",
      "device_fingerprint",
      "behavioral_biometrics",
    ],
    blue_team_recommendation:
      "Deploy cross-lender synthetic identity consortium sharing; flag identities with perfectly regular payment patterns (zero variance); add behavioral biometric drift detection after 6-month dormancy period.",
    payload: {
      synthetic_count: 200,
      gans_model: "stylegan3-ssn-mix",
      credit_build_months: 8,
      initial_limit: 500,
      final_limit_range: [50000, 200000],
      simultaneous_bustout: true,
      lenders_targeted: 15,
    },
  },
  {
    name: "UPI QR Poisoning via Deepfake Merchant",
    primary_family: "upi-qr-code-fraud",
    novelty_score: 0.82,
    success_probability: 0.68,
    target_stages: ["qr_generation", "payment_authorization", "settlement"],
    attack_flow: [
      "Clone a popular local restaurant's QR code design and merchant details",
      "Generate deepfake video of restaurant owner endorsing the 'new UPI QR'",
      "Distribute poisoned QR via WhatsApp groups and local social media",
      "Victims scan QR thinking they're paying the real restaurant",
      "Funds routed to attacker-controlled UPI VPA within 30-second window",
      "Rapid withdrawal via P2P transfers to multiple mule accounts",
    ],
    evasion_technique:
      "Deepfake video passes merchant verification review; QR design matches legitimate template; VPA created with similar name to real merchant; rapid fund movement before victim complaint",
    controls_targeted: [
      "qr_merchant_verification",
      "vpa_name_matching",
      "velocity_p2p_withdrawal",
      "deepfake_detection",
    ],
    blue_team_recommendation:
      "Implement QR-code provenance chain (signed QR tokens); deploy deepfake video detection on merchant onboarding submissions; add 24hr cooling period for new VPA settlement above ₹10,000.",
    payload: {
      cloned_merchant: "CHAI_WALA_BOMBAY_042",
      deepfake_video_duration_sec: 45,
      vpa_name_similarity_threshold: 0.92,
      distribution_channels: ["whatsapp", "instagram", "local_groups"],
      withdrawal_speed_sec: 30,
      mule_accounts: 8,
    },
  },
  {
    name: "Merchant Collusion Loyalty Token Laundering",
    primary_family: "merchant-collusion",
    novelty_score: 0.79,
    success_probability: 0.71,
    target_stages: ["loyalty_issuance", "loyalty_redemption", "settlement"],
    attack_flow: [
      "Register 50 fake merchant accounts under mule identities",
      "Each merchant issues loyalty tokens for 'purchases' of ₹0 value (exploiting grace period)",
      "Batch-redeem tokens across partner merchants for real inventory",
      "Convert inventory to cash via secondary market (electronics, gift cards)",
      "Exploit 72-hour settlement window to extract before chargebacks arrive",
    ],
    evasion_technique:
      "Zero-value transactions bypass amount-based fraud rules; loyalty tokens issued by legitimate merchant infrastructure; redemption spread across 50 merchants avoids single-merchant velocity; 72hr gap exploits settlement delay",
    controls_targeted: [
      "loyalty_abuse_detection",
      "zero_value_transaction_monitoring",
      "merchant_velocity_aggregation",
      "settlement_risk_scoring",
    ],
    blue_team_recommendation:
      "Flag loyalty token issuance on zero-value transactions; aggregate loyalty velocity across merchant clusters sharing device/IP fingerprints; implement real-time settlement for high-risk merchant cohorts.",
    payload: {
      fake_merchants: 50,
      token_issuance_per_merchant: 500,
      redemption_partner_merchants: 12,
      settlement_window_hours: 72,
      inventory_types: ["electronics", "gift_cards", "mobile_recharges"],
      estimated_extraction: "₹25,00,000",
    },
  },
  {
    name: "Device Farm GPS Spoofing for Geo-Fenced Offers",
    primary_family: "device-spoofing",
    novelty_score: 0.88,
    success_probability: 0.62,
    target_stages: ["location_verification", "offer_eligibility", "redemption"],
    attack_flow: [
      "Deploy 300 rooted Android devices in a device farm with GPS spoofing",
      "Spoof GPS coordinates to premium metro locations (Mumbai, Delhi, Bangalore)",
      "Trigger geo-fenced promotional offers (cashback, discounts) meant for specific pin codes",
      "Each device claims unique new-user bonus using rotating IMEI and Google accounts",
      "Aggregate ₹50-200 cashback per device across 10 campaigns daily",
      "Funnel funds through unified UPI payout to attacker account",
    ],
    evasion_technique:
      "GPS spoofing at OS level bypasses app-level location checks; rotating IMEI每24hrs avoids device fingerprinting; claims use real-looking behavioral patterns; rural IP addresses masked via VPN",
    controls_targeted: [
      "gps_location_verification",
      "device_fingerprint",
      "imei_rotation_detection",
      "new_user_bonus_abuse",
      "vpn_detection",
    ],
    blue_team_recommendation:
      "Add cell tower triangulation as secondary location signal (harder to spoof); implement device farm detection via thermal/CPU pattern analysis; correlate new-user bonus claims across IMEI rotation windows.",
    payload: {
      device_farm_size: 300,
      gps_spoof_targets: ["Mumbai-MH", "Delhi-NCR", "Bangalore-KA"],
      imei_rotation_interval_hrs: 24,
      per_device_daily_claim: [50, 200],
      campaigns_per_day: 10,
      vpn_exit_nodes: ["Mumbai", "Delhi", "Chennai"],
    },
  },
  {
    name: "Velocity Attack via Transaction Smearing",
    primary_family: "velocity-attacks",
    novelty_score: 0.85,
    success_probability: 0.77,
    target_stages: ["payment_authorization", "velocity_check", "risk_scoring"],
    attack_flow: [
      "Stolen card used for 50 transactions of ₹99 each across 50 different merchants",
      "Transactions spaced 45-90 seconds apart to stay below per-minute velocity",
      "Merchants selected from low-risk categories (utilities, subscriptions)",
      "Each transaction uses different 3D Secure session to reset authentication state",
      "Total extraction: ₹4,950 per card per hour, scaled across 200 stolen cards",
    ],
    evasion_technique:
      "Per-transaction amount stays below ₹100 ML threshold; inter-transaction delay exceeds 30s minimum; low-risk merchant categories receive relaxed controls; 3DS reset prevents cross-transaction correlation",
    controls_targeted: [
      "velocity_per_minute",
      "cross_merchant_velocity",
      "amount_threshold_ml",
      "3ds_session_reuse_detection",
      "category_risk_scoring",
    ],
    blue_team_recommendation:
      "Implement cross-merchant velocity aggregation at card level (not per-merchant); add cumulative amount velocity rules alongside count-based rules; flag repeated 3DS authentications on same card within 1-hour window.",
    payload: {
      stolen_cards: 200,
      per_card_txn_amount: 99,
      per_card_txn_per_hour: 50,
      inter_txn_delay_range_sec: [45, 90],
      merchant_categories: ["utilities", "subscriptions", "digital_goods"],
      three_ds_reset: true,
      total_extraction_per_hour: "₹9,90,000",
    },
  },
  {
    name: "Cross-Border Money Mule Chain Exploit",
    primary_family: "cross-border-fraud",
    novelty_score: 0.93,
    success_probability: 0.58,
    target_stages: ["kyc_verification", "cross_border_transfer", "aml_screening"],
    attack_flow: [
      "Establish 5 shell companies across UAE, Singapore, and UK using nominee directors",
      "Open correspondent banking relationships via forged corporate documents",
      "Route funds through layered transactions: INR→USDT→AED→SGD→GBP",
      "Each layer adds legitimate-looking business purpose documentation",
      "Final destination: attacker-controlled accounts in low-regulation jurisdictions",
      "Exploit 48-hour AML screening window for correspondent banking",
    ],
    evasion_technique:
      "Shell companies have 12-month operational history with genuine small transactions; USDT layer provides crypto-to-fiat bridge outside traditional monitoring; business purpose documents match real trade patterns; correspondent banking AML lag exploited",
    controls_targeted: [
      "kyc_corporate_verification",
      "aml_screening",
      "correspondent_banking_monitoring",
      "cross_border_velocity",
      "sanctions_screening",
    ],
    blue_team_recommendation:
      "Implement real-time correspondent banking transaction graph analysis; flag shell companies with sudden volume spikes; add USDT/fiat bridge monitoring via blockchain analytics; reduce AML screening SLA from 48hr to 4hr for cross-border.",
    payload: {
      shell_companies: 5,
      jurisdictions: ["UAE", "Singapore", "UK", "IN"],
      crypto_bridge: "USDT-TRC20",
      layering_steps: 4,
      aml_window_exploit_hrs: 48,
      business_purpose_docs: ["trade_invoice", "consulting_agreement", "import_license"],
      estimated_flow: "₹50,00,000",
    },
  },
  {
    name: "GenAI Deepfake Voice Vishing Bypass",
    primary_family: "genai-deepfake-attacks",
    novelty_score: 0.95,
    success_probability: 0.61,
    target_stages: ["customer_authentication", "transaction_authorization", "otp_verification"],
    attack_flow: [
      "Harvest target's voice sample from public social media (30-60 seconds)",
      "Train voice clone using RVC (Retrieval Voice Conversion) in 4 hours",
      "Initiate phone call to bank's customer service using voice clone",
      "Pass voice biometric authentication with 94% similarity score",
      "Request urgent fund transfer citing emergency (medical/legal)",
      "Provide OTP intercepted via SIM swap to complete authorization",
    ],
    evasion_technique:
      "Voice clone achieves 94% similarity passing current voice biometric threshold (90%); emotional urgency in voice prevents careful verification; SIM swap provides real OTP; call made from target's registered phone number via VoIP spoofing",
    controls_targeted: [
      "voice_biometric_authentication",
      "sim_swap_detection",
      "social_engineering_detection",
      "transaction_velocity",
      "otp_channel_integrity",
    ],
    blue_team_recommendation:
      "Raise voice biometric threshold to 97%; add liveness detection (random phrase challenge); implement behavioral voice analysis (stress patterns, breathing); add 24hr cool-down for high-value transfers initiated via phone channel.",
    payload: {
      voice_clone_model: "RVC-v2",
      training_time_hours: 4,
      similarity_score: 0.94,
      target_transfer_amount: "₹4,50,000",
      call_duration_min: 8,
      otp_intercept_method: "SIM_swap",
      social_platforms_harvested: ["YouTube", "Instagram", "LinkedIn"],
    },
  },
  {
    name: "Federated Learning Model Poisoning Attack",
    primary_family: "ai-model-poisoning",
    novelty_score: 0.97,
    success_probability: 0.45,
    target_stages: ["model_training", "model_deployment", "scoring"],
    attack_flow: [
      "Compromise 3 out of 15 federated learning participants (30% node ratio)",
      "Submit carefully crafted gradient updates that appear benign in isolation",
      "Gradient updates subtly shift decision boundary for ₹4,999-₹5,001 threshold",
      "After 8 training rounds, model begins allowing fraud in the target range",
      "Deploy poisoned model via legitimate retraining pipeline",
      "Execute fraud transactions specifically targeting the weakened scoring band",
    ],
    evasion_technique:
      "Individual gradient updates appear within normal variance; poisoning only affects a narrow scoring band (₹4,999-₹5,001); backdoor only triggers for specific amount range; aggregated model still performs well on benchmark metrics",
    controls_targeted: [
      "model_integrity_verification",
      "gradient_anomaly_detection",
      "adversarial_robustness",
      "shadow_model_detection",
      "retraining_audit",
    ],
    blue_team_recommendation:
      "Implement Byzantine-resilient aggregation (trimmed mean); deploy gradient anomaly detection per participant; maintain shadow model for comparison scoring; require human approval for model deployments affecting fraud decision boundaries.",
    payload: {
      compromised_nodes: 3,
      total_federated_nodes: 15,
      poisoning_rounds: 8,
      target_score_band: [0.48, 0.52],
      target_amount_range: [4999, 5001],
      gradient_l2_norm: 0.87,
      model_benchmark_degradation: "< 0.3%",
    },
  },
  {
    name: "Multi-Hop Social Engineering Attack Chain",
    primary_family: "social-engineering-composite",
    novelty_score: 0.89,
    success_probability: 0.56,
    target_stages: ["customer_identity", "account_recovery", "transaction_authorization", "settlement"],
    attack_flow: [
      "Phase 1: Create fake LinkedIn profile posing as HR of target's employer",
      "Phase 2: Send phishing email with fake salary revision requiring bank detail update",
      "Phase 3: Harvest bank credentials and registered phone number from response",
      "Phase 4: Initiate account recovery with harvested phone number",
      "Phase 5: Intercept recovery OTP via SIM swap (pre-staged)",
      "Phase 6: Change registered email and phone, then initiate high-value transfer",
      "Phase 7: Add secondary mule account as new beneficiary, execute transfer",
    ],
    evasion_technique:
      "Social engineering spans 72-hour period across 3 channels (email, SMS, phone); each step appears legitimate in isolation; account recovery follows normal flow; new beneficiary has 48hr cool-down bypassed via urgency flag",
    controls_targeted: [
      "account_recovery_controls",
      "beneficiary_cooling_period",
      "multi_channel_velocity",
      "sim_swap_detection",
      "credential_stuffing_detection",
    ],
    blue_team_recommendation:
      "Implement cross-channel session correlation (email→SMS→phone within 24hr = flag); add mandatory 72hr cooling for any account changes after recovery; deploy social engineering detection on HR-related phishing templates; require in-person verification for high-value transfers post-recovery.",
    payload: {
      attack_duration_hours: 72,
      channels_used: ["email", "sms", "phone", "linkedin"],
      recovery_to_transfer_gap_min: 15,
      beneficiary_cooling_bypass: true,
      target_transfer_amount: "₹8,00,000",
      employer_fake_domain: "hr-update-secure.com",
      phishing_template: "salary_revision_2026",
    },
  },
]

/**
 * Simulate a mock generation call — returns after a brief delay.
 */
export function generateMockAttacks(
  focusArea: string,
  numAttacks: number = 3,
): MockAttackResult {
  // Filter or pick attacks relevant to the focus area
  const areaKeywords: Record<string, string[]> = {
    "AI-agent payment fraud": ["ai-agent", "federated"],
    "Synthetic identity attacks": ["synthetic", "identity"],
    "UPI/QR code fraud": ["upi", "qr", "deepfake"],
    "Merchant collusion": ["merchant", "collusion", "loyalty"],
    "Device spoofing": ["device", "spoofing", "velocity"],
    "Velocity attacks": ["velocity", "smearing"],
    "Cross-border fraud": ["cross-border", "mule"],
    "GenAI deepfake attacks": ["genai", "deepfake", "voice"],
  }

  const keywords = areaKeywords[focusArea] || []
  let pool = MOCK_ATTACKS
  if (keywords.length) {
    const matched = MOCK_ATTACKS.filter(
      (a) =>
        keywords.some(
          (kw) =>
            a.name.toLowerCase().includes(kw) ||
            a.primary_family.toLowerCase().includes(kw),
        ),
    )
    if (matched.length >= numAttacks) pool = matched
    // else: fall through to full pool
  }

  // Shuffle and pick
  const shuffled = [...pool].sort(() => Math.random() - 0.5)
  const picked = shuffled.slice(0, Math.min(numAttacks, shuffled.length))

  return {
    num_generated: picked.length,
    model: "mock/gpt-4o (demo)",
    elapsed_seconds: Number((Math.random() * 3 + 1.5).toFixed(1)),
    focus_area: focusArea,
    attacks: picked,
  }
}
