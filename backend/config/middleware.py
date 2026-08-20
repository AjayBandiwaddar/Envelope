"""
Request ID propagation, per API_SPEC.md Section 24: every incoming
request gets a request ID (client-supplied via X-Request-ID, or
generated), which must appear in the response, logs, and audit event.
"""

import uuid

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request.request_id = incoming or f"req-{uuid.uuid4().hex[:12]}"

        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request.request_id
        return response