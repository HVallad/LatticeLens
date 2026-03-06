# API Gateway Design Document

## Architecture Decision: Caching Strategy

We will use Redis as the caching layer for API responses. All GET endpoints
with stable data should cache responses for 5 minutes. Cache keys are derived
from the full request URL including query parameters. Cache invalidation occurs
on any PUT/POST/DELETE to the same resource path.

This decision was driven by the need to reduce database load during peak traffic
while keeping data freshness acceptable for our use case.

## Risk Assessment: Rate Limiting

Without rate limiting, the API is vulnerable to abuse and denial-of-service.
We will enforce a default rate limit of 100 requests per minute per API key.
Authenticated enterprise clients may request higher limits via support.

Rate limit headers (X-RateLimit-Remaining, X-RateLimit-Reset) must be included
in every response. Exceeding the limit returns HTTP 429 with a Retry-After header.

## API Specification: Health Check Endpoint

The `/health` endpoint returns HTTP 200 with a JSON body containing service
status, version, and dependency health. It does not require authentication.

Response format:
```json
{
  "status": "healthy",
  "version": "1.2.0",
  "dependencies": {
    "database": "connected",
    "cache": "connected"
  }
}
```

This endpoint is used by the load balancer for health checks and by the
monitoring system for availability tracking.
