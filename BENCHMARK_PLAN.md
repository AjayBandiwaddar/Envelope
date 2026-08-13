````markdown id="p7v4k2"
# BENCHMARK_PLAN.md

# Agent Action Firewall — Performance Benchmark Plan

## 1. Purpose

This document defines how the Agent Action Firewall POC will measure performance.

The objective is to determine:

1. Authorization throughput.
2. Authorization latency.
3. Behavior under increasing concurrency.
4. Whether 10,000 requests/sec is achievable for the authorization layer.
5. Whether performance degrades predictably under load.
6. Which component becomes the bottleneck.

The benchmark must produce reproducible measurements.

Never invent, estimate, or manually alter benchmark results.

---

# 2. What We Are Benchmarking

The primary benchmark target is:

> The deterministic authorization gateway.

We are NOT benchmarking:

- LLM generation quality
- LLM token throughput
- model inference speed
- external third-party API latency
- React rendering performance

The core benchmark is:

```text
HTTP Request
    ↓
Authentication
    ↓
Request validation
    ↓
Task/policy lookup
    ↓
Policy evaluation
    ↓
Authorization decision
    ↓
Audit event
    ↓
HTTP Response
````

A separate benchmark may measure tool execution, but it must not be mixed into the core authorization throughput number.

---

# 3. Performance Targets

Initial POC targets:

```text
p50 authorization latency < 20 ms
p95 authorization latency < 100 ms
```

Primary throughput experiment:

```text
100 RPS
1,000 RPS
5,000 RPS
10,000 RPS
```

10,000 RPS is a target for experimentation, NOT a guaranteed requirement.

The final README must report the actual measured result.

---

# 4. Benchmark Environment

Every benchmark report must record the environment.

Minimum information:

```text
CPU:
RAM:
Operating system:
Python version:
Django version:
PostgreSQL version:
Redis version:
Docker version:
Number of Django workers:
Database configuration:
Redis configuration:
Load-generator machine:
Network configuration:
```

Do not compare two benchmark runs without recording environment changes.

---

# 5. Benchmark Deployment Modes

The system should be tested in at least two modes.

## Mode A — Local development

Purpose:

* quick development feedback
* regression detection

Example:

```text
Load Generator
      ↓
Django
      ↓
PostgreSQL
      +
Redis
```

This benchmark is useful for development but should not be presented as a production-scale measurement.

---

## Mode B — Production-like Docker environment

Purpose:

* realistic throughput measurement
* final portfolio benchmark

Example:

```text
Load Generator
      ↓
Reverse Proxy
      ↓
Django Workers
      ↓
PostgreSQL
      +
Redis
```

Use multiple Django workers.

The exact worker count must be recorded.

---

# 6. Benchmark Request

Use a representative authorization request.

Example:

```json
{
  "agent_id": "support-agent-01",
  "user_id": "user-001",
  "task_id": "task-refund-001",
  "tool": "tool-refund-001",
  "action": "refund_order",
  "resource": {
    "type": "order",
    "id": "8291"
  },
  "parameters": {
    "amount": 3000,
    "currency": "INR"
  }
}
```

The request must represent a realistic authorization workload.

Do not benchmark an empty endpoint just to inflate RPS.

---

# 7. Benchmark Dataset

The benchmark should use a sufficiently large synthetic dataset.

Minimum recommended dataset:

```text
100 agents
10,000 users
100,000 tasks
100,000 policies
1,000,000 synthetic resources/orders
```

The POC may start smaller during development.

The final benchmark should avoid a tiny dataset that allows unrealistic database caching behavior.

---

# 8. Workload Types

Run at least four workload types.

## Workload A — ALLOW-heavy

Most requests are authorized.

Example distribution:

```text
ALLOW = 90%
DENY  = 10%
```

Purpose:

Measure normal successful authorization.

---

## Workload B — DENY-heavy

Example:

```text
ALLOW = 10%
DENY  = 90%
```

Purpose:

Measure performance when many requests are rejected.

---

## Workload C — Mixed realistic workload

Example:

```text
ALLOW = 70%
DENY  = 30%
```

Purpose:

Approximate normal production behavior.

---

## Workload D — Security attack workload

Requests intentionally attempt:

* wrong resource
* wrong action
* excessive parameter
* expired task
* revoked task
* unknown tool
* invalid agent

Purpose:

Confirm the security path remains performant under adversarial traffic.

---

# 9. Request Complexity Levels

Run at least three complexity levels.

## Simple

```text
one action
one resource
two parameters
one policy
```

## Medium

```text
one action
one resource
multiple constraints
multiple policy candidates
```

## Complex

```text
one action
resource constraints
multiple parameter constraints
explicit deny
multiple applicable policies
```

The final report should state which workload produced which result.

---

# 10. Throughput Test

Run the authorization endpoint at:

```text
100 RPS
1,000 RPS
5,000 RPS
10,000 RPS
```

For every target:

```text
duration = 2–5 minutes minimum
warm-up period = 30–60 seconds
```

Do not include warm-up traffic in final latency calculations.

---

# 11. Concurrency Test

Measure increasing concurrency.

Suggested levels:

```text
10
50
100
250
500
1,000
2,000
```

Observe:

* throughput
* p50 latency
* p95 latency
* p99 latency
* errors
* CPU
* memory
* database utilization
* Redis utilization

The benchmark should identify the point at which latency begins increasing sharply.

---

# 12. Latency Metrics

Record:

```text
p50
p90
p95
p99
max
```

Definitions:

### p50

Median latency.

### p95

95% of requests finish at or below this latency.

### p99

99% of requests finish at or below this latency.

Do not report only average latency.

Average latency can hide tail latency problems.

---

# 13. Throughput Metrics

Record:

```text
target RPS
actual RPS
successful requests
failed requests
HTTP errors
authorization ALLOW count
authorization DENY count
```

Calculate:

```text
error_rate =
failed_requests / total_requests
```

Report as a percentage.

---

# 14. Authorization Metrics

For each benchmark, record:

```text
authorization requests
ALLOW decisions
DENY decisions
authorization errors
policy evaluation time
database lookup time where measurable
audit write time where measurable
```

This helps identify the actual bottleneck.

---

# 15. Database Metrics

Monitor PostgreSQL during load.

Record:

```text
CPU utilization
memory utilization
active connections
connection pool usage
queries/sec
slow queries
query latency
locks
```

Watch for:

* connection exhaustion
* slow policy queries
* missing indexes
* excessive ORM queries
* N+1 behavior

The benchmark should not hide database bottlenecks.

---

# 16. Redis Metrics

Record where Redis is used:

```text
commands/sec
memory usage
hit rate
miss rate
latency
connection count
```

Determine whether Redis is actually improving authorization latency.

If Redis is not materially useful for the POC, do not force it into every request.

---

# 17. Application Metrics

Record:

```text
Django worker CPU
Django worker memory
request queue time
request processing time
5xx count
4xx count
```

Where possible, separate:

```text
authentication time
validation time
policy lookup time
policy evaluation time
audit time
response time
```

---

# 18. Audit Logging Benchmark

Because every authorization request must be auditable, audit logging must be included in at least one realistic benchmark.

Run two measurements:

### Benchmark A

Authorization without persistence overhead where safely isolated.

### Benchmark B

Full production-like path including audit persistence.

This allows us to quantify audit overhead.

Do NOT disable audit logging in the headline benchmark if the production architecture requires it.

---

# 19. Cache Benchmark

If policy/task caching is implemented, compare:

### Cold cache

Minimal cached state.

### Warm cache

Frequently accessed authorization state already cached.

Record:

```text
cache hit rate
cache miss rate
p50
p95
p99
RPS
```

Do not claim overall system performance based only on warm-cache results.

Report cache conditions clearly.

---

# 20. Scaling Experiment

Increase Django worker count.

Example:

```text
1 worker
2 workers
4 workers
8 workers
```

Measure:

```text
RPS
p95
CPU
memory
database load
```

Plot:

```text
workers → throughput
```

The purpose is to determine whether the application scales approximately linearly.

Do not assume horizontal scaling works simply because multiple processes exist.

---

# 21. Database Index Experiment

Benchmark with proper indexes.

Record the important authorization queries.

For example:

```text
task lookup
policy lookup
agent lookup
tool lookup
audit insert
```

Use database query analysis to detect:

* full table scans
* unnecessary joins
* repeated lookups

Any index added for performance must be justified in documentation.

---

# 22. Load-Test Tool

Use a dedicated load-testing tool.

Preferred options:

```text
Locust
k6
JMeter
```

Recommendation for the POC:

> Use Locust or k6.

The selected tool must support:

* configurable RPS
* concurrency
* latency measurement
* error reporting
* repeatable scenarios

---

# 23. Benchmark Duration

For initial development benchmarks:

```text
30–60 seconds
```

For final benchmarks:

```text
2–5 minutes
```

For stability testing:

```text
15–30 minutes
```

Do not use a 5-second run as evidence of sustained throughput.

---

# 24. Warm-Up

Each benchmark should include a warm-up period.

Example:

```text
warm-up:
60 seconds

measurement:
300 seconds
```

The warm-up period should not be included in final performance statistics.

---

# 25. Benchmark Repetition

Each important benchmark must run at least three times.

Example:

```text
Run 1
Run 2
Run 3
```

Report:

```text
median
range
```

Prefer the median over a single lucky run.

If results vary significantly, investigate why.

---

# 26. Benchmark Reproducibility

Every final performance experiment must include:

```text
load-test configuration
environment configuration
dataset-generation method
worker count
database configuration
Redis configuration
request payload
test duration
```

Store benchmark configuration in Git.

Suggested location:

```text
benchmarks/
├── configs/
├── scenarios/
├── scripts/
└── results/
```

Do not commit huge raw logs unnecessarily.

Store summarized results and reproducible configuration.

---

# 27. Example Benchmark Configuration

Conceptual configuration:

```yaml
name: authorization_10k_rps
target_rps: 10000
duration_seconds: 300
warmup_seconds: 60
concurrency: 2000

workload:
  allow_ratio: 0.70
  deny_ratio: 0.30

request:
  tool: tool-refund-001
  action: refund_order
  resource_type: order
  parameters:
    amount: 3000
    currency: INR
```

The exact load-testing format depends on the selected tool.

---

# 28. Success Criteria

For the final POC benchmark, aim to demonstrate:

```text
p50 < 20 ms
p95 < 100 ms
error rate < 1%
```

at the highest reproducible throughput achieved by the tested environment.

Do not force the benchmark to achieve 10K RPS.

If the system achieves:

```text
4,700 RPS
```

that is the result.

Improve the architecture and rerun the benchmark rather than changing the reported number.

---

# 29. 10K RPS Benchmark

The 10K RPS experiment is a specific stress test.

Test:

```text
target = 10,000 RPS
duration = 300 seconds
```

Record:

```text
actual RPS
p50
p95
p99
error rate
CPU
memory
PostgreSQL utilization
Redis utilization
```

Possible outcomes:

### Outcome A

```text
10K RPS
p95 < 100ms
error rate < 1%
```

Excellent.

### Outcome B

```text
10K RPS
p95 > 100ms
error rate < 1%
```

System is throughput-capable but latency target is not met.

### Outcome C

```text
actual throughput < 10K
```

Document the bottleneck.

Do not call the system "10K RPS capable" unless the measured result supports that statement.

---

# 30. Bottleneck Diagnosis

When performance degrades, identify the limiting resource.

Potential bottlenecks:

```text
CPU
memory
database
Redis
network
Django worker count
connection pool
policy evaluation
audit persistence
```

Use observability rather than guessing.

---

# 31. Performance Regression Test

After significant optimization, rerun the same benchmark.

Example:

```text
Before:
3,800 RPS
p95 = 132 ms

After:
6,400 RPS
p95 = 78 ms
```

Only compare runs with equivalent test configuration.

---

# 32. Security + Performance Combined Test

Run adversarial traffic at scale.

Example workload:

```text
25% valid
25% wrong resource
20% excessive parameter
10% expired task
10% unknown tool
10% malformed/invalid request
```

Measure:

```text
throughput
latency
denies
errors
tool executions
```

The security layer must remain enforced under load.

The system must never sacrifice authorization correctness to maintain throughput.

---

# 33. Tool Execution Isolation

The 10K RPS benchmark should NOT call expensive external systems.

Use deterministic mock tools.

Otherwise the benchmark measures the external dependency rather than the authorization system.

Example:

```text
authorization request
    ↓
policy decision
    ↓
mock tool
    ↓
constant-time response
```

---

# 34. LLM Isolation

LLM inference should be excluded from the core authorization benchmark.

The architecture is intentionally:

```text
LLM
 ↓
proposed action
 ↓
Agent Action Firewall
 ↓
deterministic authorization
```

The LLM is not part of the authorization decision.

Therefore:

```text
10K authorization RPS
```

does NOT mean:

```text
10K LLM inference RPS
```

These are fundamentally different metrics.

---

# 35. Benchmark Report Format

Every final benchmark should be summarized using:

```text
Benchmark:
Environment:
Duration:
Concurrency:
Target RPS:
Actual RPS:

p50:
p95:
p99:

Success rate:
Error rate:

ALLOW:
DENY:

CPU:
Memory:
PostgreSQL:
Redis:

Django workers:

Bottleneck:
Observations:
```

---

# 36. Example Final Report

Example format only.

Do NOT use these numbers as real results.

```text
Benchmark:
Authorization Gateway — Mixed Workload

Environment:
8 CPU
16 GB RAM
4 Django workers
PostgreSQL
Redis

Duration:
300 seconds

Target RPS:
10,000

Actual RPS:
9,420

p50:
11 ms

p95:
47 ms

p99:
83 ms

Error rate:
0.12%

ALLOW:
6,594,000

DENY:
2,826,000

CPU:
71%

PostgreSQL:
54%

Redis:
19%

Bottleneck:
Database policy lookup

Observation:
Authorization remained deterministic under sustained load.
```

---

# 37. What Counts as a Valid Benchmark Claim

Valid:

> "The tested configuration sustained 9,420 RPS for five minutes with 47 ms p95 authorization latency."

Invalid:

> "The system supports unlimited scale."

Invalid:

> "The system is production ready."

Invalid:

> "The system handles 10K RPS" when only a short local test was performed.

All claims must match measured evidence.

---

# 38. Portfolio Metrics

The final portfolio README should prioritize:

```text
peak sustained RPS
p95 authorization latency
p99 latency
security attack cases blocked
authorization error rate
audit coverage
```

Example presentation format:

```text
10K-class authorization benchmark
9,420 sustained RPS
47 ms p95
0 unauthorized tool executions
100% audit coverage
```

Only after actual testing.

---

# 39. Performance Optimization Order

Do not optimize randomly.

Use this order:

```text
1. Correctness
2. Profiling
3. Database queries/indexes
4. Connection pooling
5. Policy evaluation efficiency
6. Redis/cache where justified
7. Django worker configuration
8. Request serialization overhead
9. Network/reverse-proxy tuning
10. Horizontal scaling
```

Do not sacrifice security correctness for benchmark numbers.

---

# 40. Benchmarking Rules for Codex

Codex must:

1. Never invent benchmark results.
2. Never fabricate machine specifications.
3. Never claim 10K RPS without evidence.
4. Store benchmark configurations in the repository.
5. Make benchmark runs reproducible.
6. Clearly distinguish measured numbers from targets.
7. Investigate bottlenecks before optimizing.
8. Preserve security enforcement during optimization.
9. Avoid removing audit/security checks only to improve benchmark performance.
10. Document any benchmark assumptions.

---

# 41. Completion Criteria

The benchmark work is complete when:

```text
[ ] Load-testing tool selected
[ ] Reproducible benchmark scenario exists
[ ] 100 RPS tested
[ ] 1K RPS tested
[ ] 5K RPS tested
[ ] 10K RPS attempted
[ ] p50 recorded
[ ] p95 recorded
[ ] p99 recorded
[ ] Error rate recorded
[ ] CPU recorded
[ ] Memory recorded
[ ] PostgreSQL behavior observed
[ ] Redis behavior observed
[ ] Multiple runs performed
[ ] Security behavior verified under load
[ ] Actual peak throughput documented
[ ] Bottleneck identified
[ ] No unsupported performance claims exist
```

---

# 42. Final Benchmark Principle

The objective is not to make the benchmark number look impressive.

The objective is to answer:

> How many correctly authorized agent actions can this system sustain, at what latency, under what infrastructure, and without weakening the security guarantees?

That answer must come from measurements.

```
```
