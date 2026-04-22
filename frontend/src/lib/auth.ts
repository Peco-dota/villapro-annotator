export function getToken(): string | null {
  return localStorage.getItem('visionq_token')
}

export function setToken(token: string) {
  localStorage.setItem('visionq_token', token)
}

export function clearToken() {
  localStorage.removeItem('visionq_token')
}

export function isLoggedIn(): boolean {
  return !!getToken()
}
