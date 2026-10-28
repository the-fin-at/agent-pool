# 0001: Real-host validation without credential migration

Status: accepted, 2026-10-28.

The owner authorized unattended setup and three verification loops on SSH alias claw-remote. Use GitHub specs/tickets, retain the existing native SSH trust configuration, deploy a private user worker, and test CLI/RPC and real native GUI boundaries. Existing server services and account data remain in place.

Fault injection and synthetic load use isolated pools/workspaces on the same host, never the owner's production queue. Real subscription inference is bounded and explicitly distinguished from controlled-provider checks. Existing native authentication on the server may be reused on that server without credential copies; any browser consent that cannot be completed from an existing authorized session remains an honest acceptance limit. No new paid infrastructure or transfer of local credentials is required.

The owner explicitly chose no follow-up questions; tracker, seams, ticket granularity and measurable defaults are selected here instead of the skills' interactive confirmation steps.
