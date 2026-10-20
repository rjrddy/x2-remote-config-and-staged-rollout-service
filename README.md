1. Serve config to clients with staged rollout, kill switch and rollback; SDK client with offline cache.

2. Result:
   Acceptance: not measured  
   Performance: not measured  
   Correctness: not measured

3. Architecture:
```mermaid
flowchart LR
    Specification --> AwaitingWaveApproval --> Implementation
```

4. Run it:
No runnable implementation yet. This is a planned Wave 2 project.

5. Decisions and limits: Public repository reserved for independent work using public or synthetic data. Implementation has not started. No company affiliation or usage is claimed. Acceptance check: Rollback tested; client correctness under flaky network.

6. Next: Implement after approval for Wave 2, then run and publish the required acceptance commands.
