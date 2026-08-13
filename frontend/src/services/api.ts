// Minimal API client for the Agent Action Firewall backend.
// Base URL follows API_SPEC.md §2 ("http://localhost:8000/api" for local dev).

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/health/`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}

export async function getReadiness() {
  const response = await fetch(`${API_BASE_URL}/ready/`);
  return { ok: response.ok, status: response.status, body: await response.json() };
}
