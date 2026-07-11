# Service boundaries

Virtual Office is incrementally moving business orchestration out of
`app/server.py`. The first accepted boundary is the project execution workspace
validation route:

```text
POST /api/projects/{projectId}/project-execution/workspace/validate
```

## Route responsibilities

`OfficeHandler` owns protocol concerns:

- route and path-parameter parsing;
- bounded, object-only JSON decoding;
- invoking the application service with explicit dependencies;
- mapping `ServiceResult.status` and `ServiceResult.payload` to HTTP;
- request identifiers, response hardening headers, and sanitized unexpected
  error responses.

The handler must not duplicate the service's project mutation or persistence
logic.

## Service responsibilities

`app/services/project_execution.py` owns the workspace-validation application
flow:

- loading and locating the project;
- selecting a submitted workspace path before the stored fallback;
- invoking the existing workspace safety validator;
- applying the existing success or failure state to the project;
- persisting the project exactly once on a completed validation path;
- returning an HTTP-independent `ServiceResult`.

The service receives load, save, validation, and clock dependencies explicitly.
It must not import `server.py`, construct `OfficeHandler`, write an HTTP
response, start a provider, or spawn background work.

## Compatibility guarantees

This pilot preserves the existing route, request fields, status semantics,
response JSON fields, project persistence format, and workspace safety checks.
It does not modify frontend calls, Provider protocols, SSE, or WebSocket
behavior. The change requires no data migration and can be reverted without
data repair.

## Deferred decisions

This boundary is a pilot, not the final project-domain architecture. Later
OpenSpec changes must independently review:

- grouping of project, execution, review, artifact, and scheduling services;
- ownership of project-store concurrency and locking;
- global CORS, bind-address, authentication, CSP, and frame policies;
- broader HTTP route migration and error normalization;
- structured metrics and cross-domain request tracing.

Do not introduce a service base class, dependency-injection container, domain
model rewrite, or repository abstraction solely by copying this pilot. New
abstractions must be justified by the behavior and dependencies of the later
domain change.
