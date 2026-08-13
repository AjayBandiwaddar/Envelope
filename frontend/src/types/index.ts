// Shared TypeScript types for the Agent Action Firewall dashboard.
// Mirrors the response shapes documented in API_SPEC.md. Expanded as each
// API is implemented (Day 3+); Day 1 defines only the health/ready shapes
// actually wired up so far.

export interface HealthStatus {
  status: "ok";
}

export interface ReadinessStatus {
  status: "ready" | "not_ready";
  dependencies: {
    database: "ok" | "unavailable";
    redis: "ok" | "unavailable";
  };
}
