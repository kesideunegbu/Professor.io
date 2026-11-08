const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function getToken() { return sessionStorage.getItem('professor_token'); }

export function setToken(token) { 
    if (token) sessionStorage.setItem('professor_token', token); 
    else sessionStorage.removeItem('professor_token'); 
}

export async function api(path, { method='GET', body, form=false }={}) {
  const headers = {};
  if (getToken()) headers.Authorization = `Bearer ${getToken()}`;
  if (body && !form) headers['Content-Type'] = 'application/json';
  const response = await fetch(`${BASE}${path}`, {method, headers, body: body ? (form ? new URLSearchParams(body) : JSON.stringify(body)) : undefined});
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status})`);
  return data;
}