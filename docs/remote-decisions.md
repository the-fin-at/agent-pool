# Remote architecture

An SSH client manages one user's Linux pool. The independent server worker executes jobs; RPC only submits, observes and administers permitted queue operations. Disconnecting a client does not abandon the worker or justify replaying a task.

- Stable idempotency keys make identical submissions converge on one job. A changed specification requires a different key.
- Prompts travel as JSON over SSH stdin, never through shell interpolation.
- The client explicitly supplies the configured server pool and a registered server workspace. Client paths are not substituted for server paths.
- The worker owns its execution lease. Native profile locks coordinate tasks, logins and metadata requests in the same pool.
- Monitoring reads cached server metadata. An offline heartbeat is an observation, not proof that a model process stopped.
- Strict host-key checking and no agent forwarding remain enabled. Optional forced-command keys expose only the RPC surface.
- The pool is a single user's trust boundary. Workspace registration prevents accidental path confusion; it is not a multi-user sandbox.

Installation and service commands: [remote setup](remote.md). Controlled and opt-in acceptance: [validation](validation.md).
